"""代理自助查询页（/p/…）。默认关闭，环境变量 AGENT_SELF_SERVICE=1 才开放。

代理用自己在系统里登记的邮箱登录：输入邮箱 → 收到 6 位验证码 → 只能看到自己的
学生申请进度、结算单、合同到期日和宣传资料，并可以确认结算单、上传发票。
看不到其它代理的任何信息，也看不到佣金比例以外的内部备注。

保险库锁定时（服务器重启后 POLO 还没登录），自助页显示「暂时不可用」，因为数据是密文。
POLO 在后台的代理页面可以「预览代理看到的页面」，不需要开放。
"""
import datetime as dt
import hashlib
import hmac
import io
import os
import secrets
import time

from flask import abort, flash, redirect, render_template, request, send_file, session, url_for

CODE_MINUTES = 10
SESSION_MINUTES = 30
_codes = {}  # email -> (hash, 过期时间, 剩余次数)；只在内存里


def enabled():
    return os.environ.get("AGENT_SELF_SERVICE") == "1"


def register(app, vault, deps):
    """deps: agents_by_id, enrich, all_assets, statement_file, save_upload, mailer, et, STAGES"""

    def find_agent(email):
        email = (email or "").strip().lower()
        return next((a for a in vault.all("agent") if (a.get("email") or "").strip().lower() == email
                     and a.get("status") in ("活跃", "已签约")), None)

    def current():
        aid = session.get("portal_agent")
        if not aid or time.time() - session.get("portal_seen", 0) > SESSION_MINUTES * 60:
            session.pop("portal_agent", None)
            return None
        session["portal_seen"] = time.time()
        return vault.get("agent", aid)

    def guard():
        if not enabled():
            abort(404)
        if not vault.unlocked:
            return render_template("portal/unavailable.html")
        return None

    def view(a, preview=False):
        agents = deps["agents_by_id"]()
        comms = vault.all("commission")
        mine = sorted([deps["enrich"](c, agents, comms) for c in comms if c["agent_id"] == a["id"]
                       and not c.get("imported") and c.get("status") != "草稿"],
                      key=lambda c: c.get("term_order", 999), reverse=True)
        studs = sorted([s for s in vault.all("student") if s.get("agent_id") == a["id"]],
                       key=lambda s: s.get("intake") or "", reverse=True)
        kit = [x for x in deps["all_assets"]() if x.get("share") and x.get("url")]
        return render_template("portal/home.html", a=a, comms=mine, students=studs, kit=kit, preview=preview,
                               days_left=(dt.date.fromisoformat(a["contract_expiry"]) - dt.date.today()).days
                               if a.get("contract_expiry") else None)

    @app.route("/p/", methods=["GET"])
    def portal_home():
        g = guard()
        if g:
            return g
        a = current()
        if not a:
            return redirect(url_for("portal_login"))
        return view(a)

    @app.route("/p/login", methods=["GET", "POST"])
    def portal_login():
        g = guard()
        if g:
            return g
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            a = find_agent(email)
            if a:  # 不管邮箱在不在系统里，页面显示都一样，避免被用来试探代理名单
                code = f"{secrets.randbelow(10**6):06d}"
                _codes[email] = (hashlib.sha256(code.encode()).hexdigest(), time.time() + CODE_MINUTES * 60, 5)
                tpl = deps["et"].fill(deps["et"].LOGIN_CODE, code=code)
                with deps["mailer"].Outbox(vault) as box:
                    box.send(a["email"], tpl["subject"], tpl["body"], agent_id=a["id"], kind="portal")
                vault.audit("portal code sent")
            session["portal_email"] = email
            return redirect(url_for("portal_verify"))
        return render_template("portal/login.html")

    @app.route("/p/verify", methods=["GET", "POST"])
    def portal_verify():
        g = guard()
        if g:
            return g
        email = session.get("portal_email")
        if not email:
            return redirect(url_for("portal_login"))
        if request.method == "POST":
            h, exp, tries = _codes.get(email, ("", 0, 0))
            code = request.form.get("code", "").strip()
            if tries > 0 and time.time() < exp and hmac.compare_digest(h, hashlib.sha256(code.encode()).hexdigest()):
                _codes.pop(email, None)
                a = find_agent(email)
                if a:
                    session.update(portal_agent=a["id"], portal_seen=time.time())
                    vault.audit("portal login")
                    return redirect(url_for("portal_home"))
            if email in _codes:
                _codes[email] = (h, exp, tries - 1)
            flash("The code is incorrect or has expired.")
        return render_template("portal/verify.html", email=email)

    @app.route("/p/logout")
    def portal_logout():
        session.pop("portal_agent", None)
        return redirect(url_for("portal_login"))

    def own_statement(cid):
        a = current()
        c = vault.get("commission", cid)
        if not a or not c or c["agent_id"] != a["id"] or c.get("status") == "草稿":
            abort(404)
        return a, c

    @app.route("/p/statements/<cid>.xlsx")
    def portal_statement(cid):
        g = guard()
        if g:
            return g
        a, c = own_statement(cid)
        _, name, data = deps["statement_file"](c, deps["agents_by_id"]())
        return send_file(io.BytesIO(data), download_name=name, as_attachment=True)

    @app.post("/p/statements/<cid>/confirm")
    def portal_confirm(cid):
        g = guard()
        if g:
            return g
        a, c = own_statement(cid)
        if c.get("status") != "已发结算单":
            abort(400)
        inv = deps["save_upload"]("invoice")
        if not inv:
            flash("Please attach your invoice.")
            return redirect(url_for("portal_home"))
        c.update(invoice=inv, confirmed_on=dt.date.today().isoformat(), status="代理已确认", confirmed_via="自助页")
        vault.put("commission", c)
        vault.audit("portal statement confirmed")
        flash("Thank you. Your confirmation and invoice have been received.")
        return redirect(url_for("portal_home"))

    return view
