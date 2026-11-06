import datetime as dt
import io
import json
import os
import re
import secrets
import tempfile
import time
from functools import wraps
from urllib.parse import urlparse

import openpyxl
import pyotp
from flask import (Flask, abort, flash, redirect, render_template, request, send_file, session, url_for)

import threading

import admissions
import ap_courses
import ai
import portal
import backup
import tax
import version
import local_ai
import contracts
import email_templates as et
import mailer
import importer
import inbox
import outreach_i18n as i18n
import statements
from commission import (LEVELS, PROGRAMS, academic_year, agent_scheme, calculate, parse_scheme, scheme_label,
                        total_fees, y1_rate_used)
from vault import Vault

DATA_DIR = os.environ.get("AGENT_PORTAL_DATA", os.path.join(os.path.dirname(__file__), "data"))
IDLE_MINUTES = 30
STATUSES = ["潜在", "洽谈中", "已签约", "活跃", "不活跃", "终止"]
# 新代理从第一次联系到正式开通的 7 步
ONBOARDING = [
    ("contact", "初次联系", "发出开发邮件（在「开发新代理」里一键发送）"),
    ("meeting", "回复 / 线上会议", "代理回信或约了 30 分钟会议"),
    ("vetting", "申请表 + 背景核实", "收到代理申请表，完成 Agencies Reference Check"),
    ("level", "确定等级", "标准级 20/25% 或 高级 25/30%（第一年，满 6 人起高档）"),
    ("contract", "生成并发送合同", "系统按等级生成合同，连同 Start Letter 一起发出"),
    ("signed", "收回签字合同", "上传代理签回的合同和 Schedule A 银行信息"),
    ("activate", "开通", "确认编号，发欢迎信，加入 News 推送名单"),
]
STAGES = ["草稿", "已发结算单", "代理已确认", "已交会计", "已付"]
STUDENT_STAGES = ["收到申请", "资料齐全", "已发录取信", "已缴学费", "学签获批", "已入学", "未入学"]
STUDENT_HINTS = {
    "收到申请": "代理发来申请表", "资料齐全": "护照、成绩单等材料收齐", "已发录取信": "发出 Letter of Acceptance",
    "已缴学费": "学费到账", "学签获批": "国际生拿到学签（本地生可跳过）", "已入学": "开始上课，可以计入佣金结算单",
    "未入学": "放弃、拒签或转校",
}
PROSPECT_STAGES = ["未联系", "已发邮件", "已跟进", "已回复", "已约会议", "已转为代理", "不合适"]

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)  # 每次重启更换：重启后所有登录失效
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                  SESSION_COOKIE_SECURE=os.environ.get("AGENT_PORTAL_HTTPS") == "1",
                  MAX_CONTENT_LENGTH=400 * 1024 * 1024)  # 首次导入要一次上传全部已签合同
vault = Vault(DATA_DIR)
_failed = []  # 登录失败时间戳，用于限流


# ---------- 登录 ----------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not vault.initialized:
            return redirect(url_for("setup"))
        last = session.get("seen", 0)
        if not session.get("ok") or not vault.unlocked or time.time() - last > IDLE_MINUTES * 60:
            timed_out = bool(session.get("ok"))
            session.clear()
            if timed_out:
                flash(f"超过 {IDLE_MINUTES} 分钟没有操作，已自动退出。没提交成功的邮件和结算单内容暂存在浏览器里，登录后回到原页面可以恢复。")
            nxt = request.full_path if request.method == "GET" else (request.referrer or "")
            nxt = urlparse(nxt)._replace(scheme="", netloc="").geturl() if nxt else ""
            return redirect(url_for("login", next=nxt) if nxt.startswith("/") and not nxt.startswith("//") else url_for("login"))
        session["seen"] = time.time()
        return f(*a, **kw)
    return wrapper


@app.after_request
def headers(resp):
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.before_request
def csrf():
    if request.method == "POST":
        if request.endpoint not in ("login", "setup") and request.form.get("_csrf") != session.get("csrf"):
            abort(400)


@app.context_processor
def ctx():
    session.setdefault("csrf", secrets.token_hex(16))
    n_inbox = sum(b["complete"] for b in inbox.bundles(vault)) if vault.unlocked and session.get("ok") else 0
    return {"csrf": session["csrf"], "scheme_label": scheme_label, "IDLE_MINUTES": IDLE_MINUTES,
            "today_iso": dt.date.today().isoformat(),
            "clear_draft": session.pop("clear_draft", None) if session.get("ok") else None, "unlocked": vault.unlocked, "portal_on": portal.enabled(),
            "inbox_n": n_inbox, "parent_url": parent_url() if session.get("ok") else None,
            "mail_accounts": lambda: mailer.accounts(settings()), "MAIL_KINDS": mailer.MAIL_KINDS,
            "default_sender": lambda kind: (mailer.account_for(settings(), kind) or {}).get("user")}


# 顶部导航里的一级页面不显示「返回」；其余页面的返回默认回到上一页，没有上一页时回到这里
TOP_PAGES = {"dashboard", "agents_list", "students", "prospects", "commissions", "mail", "materials", "performance",
             "payments", "settings_page", "login", "setup", "recovery", "static"}
PARENT = {"commission": "commissions", "agent": "agents_list", "contract": "agents_list", "renew": "renewals",
          "renewals": "agents_list", "prospect": "prospects", "outreach": "prospects", "student": "students",
          "mail": "mail", "compose": "mail", "inbox": "dashboard", "trash": "settings_page"}


def parent_url():
    ep = request.endpoint or ""
    if ep in TOP_PAGES:
        return None
    args = request.view_args or {}
    if ep.startswith("commission") and args.get("cid"):
        c = vault.get("commission", args["cid"])
        return url_for("commissions", term=c["term"]) if c else url_for("commissions")
    if ep.startswith(("contract", "agent_")) and args.get("aid") and ep != "agent_detail":
        return url_for("agent_detail", aid=args["aid"])
    for k, v in PARENT.items():
        if ep.startswith(k):
            return url_for(v)
    return url_for("dashboard")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if vault.initialized:
        return redirect(url_for("login"))
    token = app.config.get("SETUP_TOKEN")  # 生产环境：只有拿到服务器日志里链接的人能做首次设置
    if token and request.values.get("t") != token:
        return "首次设置需要使用部署时显示的完整链接。", 403
    if request.method == "POST":
        pw = request.form["password"]
        if len(pw) < 12 or pw != request.form["password2"]:
            flash("主密码至少 12 位，且两次输入一致")
            return redirect(url_for("setup", t=token))
        secret = request.form["totp_secret"]
        if not pyotp.TOTP(secret).verify(request.form["code"], valid_window=1):
            flash("验证码不对，请在手机验证器里重新查看")
            return redirect(url_for("setup", t=token))
        recovery = vault.initialize(pw, secret)
        vault.unlock(vault.try_unwrap(pw))
        inbox.ensure_key(vault)
        session.update(ok=True, seen=time.time())
        return render_template("recovery.html", recovery=recovery)
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri("owner", issuer_name="Agent Portal")
    return render_template("setup.html", secret=secret, uri=uri)


# ---------- 信任的设备：密码还是每次都要，只是 30 天内不再要验证码 ----------
TRUST_DAYS = 30
TRUST_COOKIE = "ap_trusted"
TRUST_FILE = os.path.join(DATA_DIR, "trusted_devices.json")  # 只存令牌的哈希，没有任何代理数据


def _trusted_load():
    try:
        with open(TRUST_FILE) as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return {}
    now = time.time()
    return {k: v for k, v in rows.items() if v.get("exp", 0) > now}


def _trusted_save(rows):
    tmp = TRUST_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rows, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TRUST_FILE)


def _token_hash(tok):
    import hashlib
    return hashlib.sha256(tok.encode()).hexdigest()


def device_trusted():
    tok = request.cookies.get(TRUST_COOKIE)
    return bool(tok) and _token_hash(tok) in _trusted_load()


@app.route("/login", methods=["GET", "POST"])
def login():
    if not vault.initialized:
        return redirect(url_for("setup"))
    if request.method == "POST":
        now = time.time()
        _failed[:] = [t for t in _failed if now - t < 900]
        if len(_failed) >= 5:
            flash("失败次数过多，请 15 分钟后再试")
            return redirect(url_for("login", next=request.args.get("next")))
        dek = vault.try_unwrap(request.form["password"])
        trusted = device_trusted()
        if not dek or not (trusted or pyotp.TOTP(vault.totp_secret(dek)).verify(request.form.get("code", ""), valid_window=1)):
            _failed.append(now)
            vault.audit("login failed")
            flash("密码或验证码错误")
            return redirect(url_for("login", next=request.args.get("next")))
        if not vault.unlocked:
            vault.unlock(dek)
        inbox.ensure_key(vault)
        _lock["since"] = None
        try:
            save_lock_notify()
        except Exception:  # noqa: BLE001
            app.logger.exception("save_lock_notify")
        vault.audit("login ok")
        try:
            refresh_old_drafts()
        except Exception:  # 清理失败不能挡住登录
            app.logger.exception("refresh_old_drafts")
        session.clear()
        session.update(ok=True, seen=now, csrf=secrets.token_hex(16))
        nxt = request.args.get("next") or ""
        resp = redirect(nxt if nxt.startswith("/") and not nxt.startswith(("//", "/login", "/logout")) else url_for("dashboard"))
        if not trusted and request.form.get("remember"):
            tok = secrets.token_urlsafe(32)
            rows = _trusted_load()
            rows[_token_hash(tok)] = {"exp": now + TRUST_DAYS * 86400, "added": dt.date.today().isoformat(),
                                      "ua": (request.user_agent.string or "")[:120]}
            _trusted_save(rows)
            https = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"
            resp.set_cookie(TRUST_COOKIE, tok, max_age=TRUST_DAYS * 86400, httponly=True, secure=https, samesite="Strict")
            vault.audit("device trusted for 30 days")
        return resp
    return render_template("login.html", trusted=device_trusted(), trust_days=TRUST_DAYS)


@app.route("/ping")
@login_required
def ping():
    """页面上「继续使用」按钮：只是刷新一下登录时间。"""
    return {"ok": True, "idle_minutes": IDLE_MINUTES}


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/lock")
@login_required
def lock():
    vault.lock()
    _lock["since"] = time.time() + 365 * 86400  # 自己点「锁定」的不发提醒
    session.clear()
    flash("保险库已锁定：内存中的密钥已清除，定时邮件暂停，需要重新登录解锁。")
    return redirect(url_for("login"))


# ---------- 工具 ----------
def agents_by_id():
    return {a["id"]: a for a in vault.all("agent")}


def terms():
    """所有学期，按先后排：结算单里出现过的 + 自己新建的（还没有结算单的学期）。"""
    seen = {}
    for c in vault.all("commission"):
        seen[c["term"]] = min(seen.get(c["term"], 999), c.get("term_order", 999))  # 个别结算单缺顺序时不打乱学期先后
    for t in vault.all("term"):
        seen.setdefault(t["name"], t.get("order", 999))
    return [t for t, _ in sorted(seen.items(), key=lambda x: x[1])]


def next_terms(existing):
    """新建学期时的建议名称：本学年和下一学年里还没有的学期，格式和佣金总表的工作表名一致。"""
    today = dt.date.today()
    y = today.year % 100 if today.month >= 9 else today.year % 100 - 1
    out = []
    for a in (y, y + 1):
        ay = f"{a:02d}-{a + 1:02d}"
        out += [f"Sep-Dec Fall {ay}", f"Jan-Apr Winter {ay}", f"May-June Spring {ay}", f"20{a + 1:02d} Summer School"]
    return [t for t in out if t not in existing]


def stage_of(c):
    s = c.get("status") or "草稿"
    return {"待付": "草稿"}.get(s, s)


def ay_group(c, all_comms=None):
    ay = academic_year(c["term"])
    pool = all_comms if all_comms is not None else vault.all("commission")
    return [x for x in pool if x["agent_id"] == c["agent_id"] and academic_year(x["term"]) == ay]


def enrich(c, agents, all_comms=None):
    a = agents.get(c["agent_id"], {})
    scheme = agent_scheme(a) if not c.get("rates") else agent_scheme({"rates": c["rates"]})
    group = ay_group(c, all_comms)
    lines, total = calculate(c, scheme, group)
    c = dict(c, agent=a, lines=lines, calc=total, fees=total_fees(c), scheme=scheme, stage=stage_of(c))
    ex = c.get("excel_commission")
    c["mismatch"] = c.get("imported") and ex is not None and abs(ex - total) >= 1
    c["amount"] = ex if c.get("imported") and ex is not None else total
    c["ft1_ay"] = len({(s.get("name") or "").lower() for x in group for s in x.get("students", []) if s.get("program") == "FT1"})
    return c


def days_left(d):
    if not d:
        return None
    return (dt.date.fromisoformat(d) - dt.date.today()).days


def next_code():
    year = dt.date.today().year
    nums = [int(a["code"][5:]) for a in vault.all("agent")
            if a.get("code") and a["code"].startswith(f"J{year}") and a["code"][5:].isdigit()]
    return f"J{year}{(max(nums) + 1 if nums else 1):02d}"


def fnum(v):
    v = (v or "").replace(",", "").replace("$", "").strip()
    return float(v) if v else None


def money(v):
    if not isinstance(v, (int, float)):
        return ""
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"


def onboarding_step(a):
    done = a.get("onboarding") or {}
    for i, (key, _, _) in enumerate(ONBOARDING):
        if key not in done:
            return i
    return len(ONBOARDING)


def mark_step(a, key):
    a.setdefault("onboarding", {})
    a["onboarding"].setdefault(key, dt.date.today().isoformat())


app.jinja_env.filters["money"] = money
app.jinja_env.globals["campaign_overdue"] = mailer.overdue


def qs(**over):
    """当前页面的查询参数，改掉其中几个（值为 None 的去掉）。"""
    from urllib.parse import urlencode
    args = request.args.to_dict()
    args.update(over)
    return "?" + urlencode({k: v for k, v in args.items() if v not in (None, "")})


app.jinja_env.globals["qs"] = qs
app.jinja_env.globals.update(days_left=days_left, agent_scheme=agent_scheme, STATUSES=STATUSES, STAGES=STAGES, LEVELS=LEVELS, PROGRAMS=PROGRAMS,
                             ONBOARDING=ONBOARDING, onboarding_step=onboarding_step, PROSPECT_STAGES=PROSPECT_STAGES,
                             COUNTRY_ZH=i18n.COUNTRY_ZH, STUDENT_STAGES=STUDENT_STAGES, STUDENT_HINTS=STUDENT_HINTS,
                             LANG_LABELS=i18n.LANG_LABELS, lang_for=i18n.lang_for, ENROLL_STATUSES=["在读", "毕业", "离校", "转校"])


def settings():
    return mailer.settings(vault)


def save_upload(field):
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    return {"name": f.filename, "fid": vault.put_file(f.read()), "uploaded": dt.date.today().isoformat()}


@app.route("/files/<fid>")
@login_required
def file_download(fid):
    if not re.fullmatch(r"[0-9a-f]{32}", fid):
        abort(404)
    vault.audit("file downloaded")
    return send_file(io.BytesIO(vault.get_file(fid)), download_name=request.args.get("name", "file"), as_attachment=True)


# ---------- 总览 ----------
@app.route("/")
@login_required
def dashboard():
    agents = agents_by_id()
    ts = terms()
    cur = ts[-1] if ts else None
    comms = vault.all("commission")
    rows = [enrich(c, agents, comms) for c in comms]
    cur_rows = [r for r in rows if r["term"] == cur]
    ay = current_ay()
    ay_rows = [r for r in rows if academic_year(r["term"]) == ay]
    open_rows = [r for r in rows if r["stage"] in STAGES[:-1] and not r.get("imported")]
    expiring = sorted([a for a in agents.values() if a.get("contract_expiry") and a.get("status") in ("活跃", "已签约")
                       and days_left(a["contract_expiry"]) <= 120], key=lambda a: a["contract_expiry"])
    pipeline = sorted([a for a in agents.values() if a.get("status") in ("潜在", "洽谈中", "已签约")],
                      key=lambda a: -onboarding_step(a))
    by_term = [(t, sum(r["amount"] for r in rows if r["term"] == t)) for t in ts[-8:]]
    prospects = vault.all("prospect")
    studs = vault.all("student")
    t4a_due = None
    today = dt.date.today()
    if today.month <= 2:  # 1–2 月提醒上一年的 T4A
        need = [x for x in tax.summarize(today.year - 1, rows, agents) if x["t4a"]]
        if need:
            t4a_due = {"year": today.year - 1, "n": len(need), "deadline": tax.deadline(today.year - 1)}
    todo = []  # 「今天要做的事」：每类一行，有事才显示
    unassigned = [x for x in studs if (x.get("web_no") or x.get("agent_hint")) and x.get("uses_agent") and not x.get("agent_id")]
    if unassigned:
        todo.append(("🎓", f"{len(unassigned)} 个学生选了代理但还没对上", url_for("students", stage="待分配"), "去分配"))
    no_stmt = [x for x in studs if x.get("stage") == "已入学" and x.get("agent_id") and not x.get("commission_id")
               and academic_year(x.get("intake") or "") == ay]
    if no_stmt:
        todo.append(("💲", f"{len(no_stmt)} 个本学年已入学的学生还没进结算单", url_for("students", stage="已入学"), "去加入"))
    unread = sum(1 for m in vault.all("mail") if m["direction"] == "in" and m.get("status") == "未读")
    if unread:
        todo.append(("✉️", f"{unread} 封未读来信", url_for("mail", unread=1), "去看"))
    for kind, r, i, e in due_followups()[:6]:
        ep, arg = {"agent": ("agent_detail", "aid"), "student": ("student_edit", "sid"), "prospect": ("prospect_detail", "pid")}[kind]
        todo.append(("📞", f"跟进 {r.get('name') or r.get('agency')}：{e['text'][:40]}（{e['next']}）", url_for(ep, **{arg: r["id"]}) + "#notes", "打开"))
    fu = [p for p in prospects if needs_followup(p)]
    if fu:
        todo.append(("🔎", f"{len(fu)} 个潜在代理发信 7 天没回，该跟进了", url_for("outreach", kind="followup", ids=[p["id"] for p in fu]), "发跟进邮件"))
    drafts = [r for r in cur_rows if r["stage"] == "草稿" and not r.get("imported") and r.get("students")]
    if drafts:
        todo.append(("📤", f"{cur} 有 {len(drafts)} 张草稿结算单还没发", url_for("commission_queue", term=cur), "逐张预览发出"))
    conf = [r for r in open_rows if r["stage"] == "代理已确认"]
    if conf:
        todo.append(("🧾", f"{len(conf)} 张结算单代理已确认，还没交会计", url_for("commissions", term=conf[0]["term"]), "去交会计"))
    exp30 = [a for a in expiring if days_left(a["contract_expiry"]) <= 30 and not (a.get("renewal") or {}).get("sent")]
    if exp30:
        todo.append(("📄", f"{len(exp30)} 份合同 30 天内到期（或已过期）还没发续签", url_for("renewals"), "去续签"))
    late = [c for c in vault.all("campaign") if mailer.overdue(c)]
    if late:
        todo.append(("⏰", f"{len(late)} 条定时推送过了时间没发出", url_for("mail"), "补发或跳过"))
    bh = backup_health()
    if bh:
        todo.append(("💾", bh, url_for("settings_page") + "#safe", "去看"))
    return render_template("dashboard.html", agents=agents, cur=cur, cur_rows=cur_rows, t4a_due=t4a_due, todo=todo,
                           open_students=sum(1 for x in studs if x.get("stage") not in ("已入学", "未入学")),
                           enrolled_now=sum(1 for x in studs if x.get("stage") == "已入学" and academic_year(x.get("intake") or "") == ay),
                           ay=ay, ay_total=sum(r["amount"] for r in ay_rows), ay_agents=len({r["agent_id"] for r in ay_rows}),
                           cur_total=sum(r["amount"] for r in cur_rows), open_rows=open_rows,
                           stage_counts={s: [r for r in open_rows if r["stage"] == s] for s in STAGES[:-1]},
                           expiring=expiring, pipeline=pipeline, by_term=by_term,
                           active=sum(1 for a in agents.values() if a.get("status") == "活跃"),
                           prospects=prospects,
                           followups=[p for p in prospects if needs_followup(p)],
                           inbox=sorted([m for m in vault.all("mail") if m["direction"] == "in"],
                                        key=lambda m: m["at"], reverse=True)[:5],
                           campaigns=[c for c in vault.all("campaign") if c.get("active")])


# ---------- 代理 ----------
AGENT_TABS = [("work", "合作中", ("活跃", "已签约")), ("onboard", "入驻中", ("潜在", "洽谈中")),
              ("off", "不活跃 / 终止", ("不活跃", "终止")), ("all", "全部", None)]


def short_scheme(a):
    """佣金方案统一写法：标准级 20/25%、高级 25/30%、旧合同 25% 或 25/10/5%。"""
    if a.get("level") in LEVELS:
        lv = LEVELS[a["level"]]
        return f"{'标准级' if a['level'] == 'standard' else '高级'} {lv['y1']:g}/{lv['y1_6']:g}%"
    r = a.get("rates")
    if not r:
        return a.get("scheme_text") or "未设置"
    return "旧合同 " + (f"{r[0]:g}%" if r[0] == r[1] == r[2] else "/".join(f"{x:g}" for x in r) + "%")


@app.route("/agents")
@login_required
def agents_list():
    q = request.args.get("q", "").strip().lower()
    st = request.args.get("status", "")
    tab = request.args.get("tab") or ("all" if st or q else "work")
    sort = request.args.get("sort") or "code"
    by_id = agents_by_id()
    comms = vault.all("commission")
    earned = {}
    for c in comms:
        earned[c["agent_id"]] = earned.get(c["agent_id"], 0) + enrich(c, by_id, comms)["amount"]
    ay = current_ay()
    ay_students = {}
    for c in comms:
        if academic_year(c["term"]) == ay:
            for r in c.get("students") or []:
                ay_students.setdefault(c["agent_id"], set()).add(r.get("student_id") or _name_key(r.get("name")))
    for x in vault.all("student"):
        if x.get("agent_id") and x.get("stage") == "已入学" and academic_year(x.get("intake") or "") == ay:
            ay_students.setdefault(x["agent_id"], set()).add(x["id"])
    ay_n = {k: len(v) for k, v in ay_students.items()}
    allg = vault.all("agent")
    counts = {k: sum(1 for a in allg if sts is None or a.get("status") in sts) for k, _, sts in AGENT_TABS}
    agents = allg
    sts = dict((k, v) for k, _, v in AGENT_TABS).get(tab)
    if sts:
        agents = [a for a in agents if a.get("status") in sts]
    if q:
        agents = [a for a in agents if q in " ".join(str(a.get(k, "")) for k in
                                                     ("name", "code", "email", "contact", "country", "payee")).lower()]
    if st:
        agents = [a for a in agents if a.get("status") == st]
    keys = {"code": lambda a: a.get("code") or "J9" + a["name"], "name": lambda a: a.get("name", "").lower(),
            "country": lambda a: (a.get("country") or "~").lower(), "status": lambda a: STATUSES.index(a["status"]) if a.get("status") in STATUSES else 9,
            "expiry": lambda a: a.get("contract_expiry") or "9999", "earned": lambda a: -earned.get(a["id"], 0),
            "ay": lambda a: -ay_n.get(a["id"], 0)}
    agents = sorted(agents, key=keys.get(sort, keys["code"]))
    return render_template("agents.html", agents=agents, earned=earned, q=q, st=st, tab=tab, tabs=AGENT_TABS, counts=counts,
                           sort=sort, ay=ay, ay_n=ay_n, short_scheme=short_scheme)


def agent_from_form(a, f):
    for k in ("name", "legal_name", "code", "contact", "email", "phone", "country", "city", "address", "website",
              "payee", "etransfer", "detail", "notes", "status", "contract_expiry", "source", "level",
              "entity_type", "tax_number"):
        if k in f:
            a[k] = f.get(k, "").strip()
    a["contract_expiry"] = a.get("contract_expiry") or None
    if "pay_terms" in f:
        v = re.sub(r"\D", "", f.get("pay_terms") or "")
        a["pay_terms"] = int(v) if v else None
    if "ap_rate" in f:
        v = (f.get("ap_rate") or "").strip().rstrip("%")
        try:
            a["ap_rate"] = float(v) if v else a.get("ap_rate", "")
        except ValueError:
            pass
    if a.get("level") in LEVELS:
        a["rates"] = [LEVELS[a["level"]]["y1"], LEVELS[a["level"]]["y2"], LEVELS[a["level"]]["y3"]]
    else:
        a["level"] = ""
        rates = [f.get("rate_y1"), f.get("rate_y2"), f.get("rate_y3")]
        if all(rates):
            a["rates"] = [float(r) for r in rates]
    return a


# ---------- 跟进记录（代理、学生、潜在代理都有）：打过电话、见过面、谈了什么，可设下次跟进日 ----------
NOTE_KINDS = {"agent": "agent_detail", "student": "student_edit", "prospect": "prospect_detail"}


@app.post("/notes/<kind>/<rid>")
@login_required
def notes_post(kind, rid):
    if kind not in NOTE_KINDS:
        abort(404)
    r = vault.get(kind, rid) or abort(404)
    log = r.setdefault("log", [])
    act = request.form.get("act") or "add"
    i = request.form.get("i", type=int)
    if act == "add":
        text = (request.form.get("text") or "").strip()
        if text:
            session["clear_draft"] = "note"
            log.append({"at": dt.datetime.now().isoformat(timespec="minutes"), "text": text[:2000],
                        "next": request.form.get("next") or ""})
            flash("已记下" + (f"，{request.form['next']} 会在总览「待办」里提醒你" if request.form.get("next") else ""))
    elif i is not None and 0 <= i < len(log):
        if act == "done":
            log[i]["done"] = dt.date.today().isoformat()
        elif act == "delete":
            log.pop(i)
    vault.put(kind, r)
    arg = {"agent": "aid", "student": "sid", "prospect": "pid"}[kind]
    return redirect(url_for(NOTE_KINDS[kind], **{arg: rid}) + "#notes")


def due_followups():
    """所有到了「下次跟进日」还没标完成的记录：[(类型, 记录, 第几条, 条目)]。"""
    today = dt.date.today().isoformat()
    out = []
    for kind in NOTE_KINDS:
        for r in vault.all(kind):
            for i, e in enumerate(r.get("log") or []):
                if e.get("next") and e["next"] <= today and not e.get("done"):
                    out.append((kind, r, i, e))
    return sorted(out, key=lambda x: x[3]["next"])


@app.route("/agents/new", methods=["GET", "POST"])
@login_required
def agent_new():
    if request.method == "POST":
        a = agent_from_form({"created": dt.date.today().isoformat(), "contracts": [], "onboarding": {}}, request.form)
        a = vault.put("agent", a)
        session["clear_draft"] = "agent"
        flash(f"已新建代理 {a['name']}")
        return redirect(url_for("agent_detail", aid=a["id"]))
    return render_template("agent_form.html", a={"code": next_code(), "status": "洽谈中", "level": "standard"}, new=True)


@app.route("/agents/<aid>", methods=["GET", "POST"])
@login_required
def agent_detail(aid):
    a = vault.get("agent", aid) or abort(404)
    if request.method == "POST":
        agent_from_form(a, request.form)
        vault.put("agent", a)
        session["clear_draft"] = "agent"
        flash("已保存")
        return redirect(url_for("agent_detail", aid=aid))
    comms = vault.all("commission")
    mine = sorted([enrich(c, {aid: a}, comms) for c in comms if c["agent_id"] == aid],
                  key=lambda c: c.get("term_order", 999), reverse=True)
    mails = sorted([m for m in vault.all("mail") if m.get("agent_id") == aid], key=lambda m: m["at"], reverse=True)
    start, end = contracts.default_period()
    studs = sorted([x for x in vault.all("student") if x.get("agent_id") == aid], key=lambda x: x.get("intake") or "", reverse=True)
    return render_template("agent_detail.html", a=a, comms=mine, mails=mails, total=sum(c["amount"] for c in mine), students=studs,
                           step=onboarding_step(a), start=start, end=end)


# ---------- 回收站：删掉的合同和代理先保留 30 天，可以恢复，之后自动清除 ----------
TRASH_DAYS = 30


def _remove_file(fid):
    if fid:
        try:
            os.remove(os.path.join(DATA_DIR, "files", fid))
        except OSError:
            pass


def trash_contract(a, c, why):
    """把一份合同放进回收站（文件留在原地，不删）。"""
    if c.get("fid"):
        vault.put("trash", {"type": "contract", "agent_id": a["id"], "label": f"{a.get('name', '')} · {c.get('name', '')}",
                            "why": why, "c": c, "at": time.time()})


TRASH_KINDS = {"student": "🎓 学生", "commission": "💲 结算单", "prospect": "🔎 潜在代理", "template": "✉️ 邮件模板",
               "asset": "📁 宣传资料", "campaign": "⏰ 定时推送"}


def to_trash(kind, rec, label, why="手动删除"):
    """删除任何记录都先放进回收站（30 天内可以恢复）。文件不删，恢复后还能用。"""
    vault.put("trash", {"type": "record", "kind": kind, "rec": rec, "label": label, "why": why, "fids": [],
                        "at": time.time()})
    vault.delete(kind, rec["id"])
    vault.audit(f"{kind} deleted (to trash)")


app.jinja_env.globals["TRASH_KINDS"] = TRASH_KINDS


def purge_trash():
    """超过 30 天的回收站内容真正删除。"""
    cutoff = time.time() - TRASH_DAYS * 86400
    for t in vault.all("trash"):
        if t.get("at", 0) < cutoff:
            for fid in t.get("fids") or [t.get("c", {}).get("fid")]:
                _remove_file(fid)
            vault.delete("trash", t["id"])


@app.route("/trash")
@login_required
def trash_list():
    rows = sorted(vault.all("trash"), key=lambda t: -t.get("at", 0))
    for t in rows:
        t["when"] = dt.datetime.fromtimestamp(t.get("at", 0)).strftime("%Y-%m-%d %H:%M")
        t["left"] = max(0, TRASH_DAYS - int((time.time() - t.get("at", 0)) // 86400))
    return render_template("trash.html", rows=rows, days=TRASH_DAYS)


@app.post("/trash/<tid>/restore")
@login_required
def trash_restore(tid):
    t = vault.get("trash", tid) or abort(404)
    if t["type"] == "contract":
        a = vault.get("agent", t["agent_id"])
        if not a:
            flash("这个代理已经不在了，请先从回收站恢复代理")
            return redirect(url_for("trash_list"))
        c = dict(t["c"], kind="已恢复" if t["c"].get("kind") in ("续签待签", "待签（系统生成）") else t["c"].get("kind"))
        a.setdefault("contracts", []).append(c)
        vault.put("agent", a)
    elif t["type"] == "record":
        vault.put(t["kind"], t["rec"])
    else:
        vault.put("agent", t["agent"])
        for kind, recs in (t.get("records") or {}).items():
            for r in recs:
                vault.put(kind, r)
    vault.delete("trash", tid)
    vault.audit("restored from trash")
    flash(f"已恢复：{t.get('label', '')}")
    return redirect(url_for("trash_list"))


@app.post("/trash/<tid>/purge")
@login_required
def trash_purge(tid):
    t = vault.get("trash", tid) or abort(404)
    for fid in t.get("fids") or [t.get("c", {}).get("fid")]:
        _remove_file(fid)
    vault.delete("trash", tid)
    vault.audit("trash item purged")
    flash("已彻底删除")
    return redirect(url_for("trash_list"))


@app.post("/agents/<aid>/delete")
@login_required
def agent_delete(aid):
    """删除导入错了的代理：连同它的结算单、学生申请和合同文件一起删掉。"""
    a = vault.get("agent", aid) or abort(404)
    records = {}
    for kind in ("commission", "student"):
        for r in vault.all(kind):
            if r.get("agent_id") == aid:
                records.setdefault(kind, []).append(r)
                vault.delete(kind, r["id"])
    vault.put("trash", {"type": "agent", "label": a.get("name", ""), "why": "删除代理", "agent": a, "records": records,
                        "fids": [c["fid"] for c in a.get("contracts") or [] if c.get("fid")], "at": time.time()})
    vault.delete("agent", aid)
    vault.audit("agent deleted (to trash)")
    flash(f"已删除代理 {a.get('name', '')}，连同结算单、学生申请和合同一起放进回收站，{TRASH_DAYS} 天内可以恢复")
    return redirect(url_for("agents_list"))


@app.route("/agents/<aid>/edit")
@login_required
def agent_edit(aid):
    return render_template("agent_form.html", a=vault.get("agent", aid) or abort(404), new=False)


@app.post("/agents/<aid>/onboarding")
@login_required
def agent_onboarding(aid):
    a = vault.get("agent", aid) or abort(404)
    old = a.get("onboarding") or {}
    a["onboarding"] = {k: old.get(k) or dt.date.today().isoformat() for k, _, _ in ONBOARDING if request.form.get(k)}
    lv = request.form.get("level")
    if lv in LEVELS:  # 第 4 步「确定等级」在这里选好，第 5 步生成合同直接用
        a["level"] = lv
        a["rates"] = [LEVELS[lv]["y1"], LEVELS[lv]["y2"], LEVELS[lv]["y3"]]
    if "signed" in a["onboarding"] and a.get("status") in ("潜在", "洽谈中"):
        a["status"] = "已签约"
    vault.put("agent", a)
    return redirect(url_for("agent_detail", aid=aid))


@app.post("/agents/<aid>/contract")
@login_required
def contract_generate(aid):
    """第 5 步：按等级生成合同；可直接连同 Start Letter 发给代理。"""
    a = vault.get("agent", aid) or abort(404)
    level = request.form.get("level") or a.get("level") or "standard"
    start = dt.date.fromisoformat(request.form["start"])
    end = dt.date.fromisoformat(request.form["end"])
    if not a.get("code"):
        a["code"] = next_code()
    a["level"] = level
    a["rates"] = [LEVELS[level]["y1"], LEVELS[level]["y2"], LEVELS[level]["y3"]]
    if "ap_rate" in request.form:  # AP 课程佣金 %，留空 = 合同上留空手填
        ap = request.form["ap_rate"].strip().rstrip("%")
        try:
            a["ap_rate"] = float(ap) if ap else ""
        except ValueError:
            flash("AP 佣金比例要填数字，比如 10")
            return redirect(url_for("agent_detail", aid=aid))
    fname, data = contracts.generate(a, level, start, end)
    a.setdefault("contracts", []).append({"name": fname, "fid": vault.put_file(data), "expiry": end.isoformat(),
                                          "uploaded": dt.date.today().isoformat(), "kind": "待签（系统生成）",
                                          "start": start.isoformat(), "tpl": TEMPLATE_REV})
    mark_step(a, "level")
    if request.form.get("send") and a.get("email"):
        tpl = et.fill(et.START_LETTER, agent=a.get("legal_name") or a["name"], contact=a.get("contact") or a["name"],
                      kit_link=kit_link())
        with mailer.Outbox(vault) as box:
            box.send(a["email"], tpl["subject"], tpl["body"], [(fname, data)], agent_id=aid, kind="onboarding")
        mark_step(a, "contract")
        flash("合同已生成，并连同 Start Letter 发给代理")
    else:
        flash("合同已生成，可在「代理合同」里下载检查")
    vault.put("agent", a)
    vault.audit("contract generated")
    return redirect(url_for("agent_detail", aid=aid))


@app.post("/agents/<aid>/contracts")
@login_required
def contract_upload(aid):
    """第 6 步：上传签回的合同。"""
    a = vault.get("agent", aid) or abort(404)
    f = save_upload("file") or abort(400)
    f.update(expiry=request.form.get("expiry") or None, kind="已签")
    a.setdefault("contracts", []).append(f)
    old_expiry = a.get("contract_expiry") or ""
    expiries = [c["expiry"] for c in a["contracts"] if c.get("expiry") and c.get("kind") in (None, "", "已签")]
    if expiries:
        a["contract_expiry"] = max(expiries)
    mark_step(a, "signed")
    if a.get("renewal") and (f.get("expiry") or "") > old_expiry:  # 签回的是续签合同
        a["renewal"]["signed"] = dt.date.today().isoformat()
        lv = a["renewal"].get("level")
        if lv in LEVELS:  # 签回续签合同后，按新等级计算佣金
            a["level"] = lv
            a["rates"] = [LEVELS[lv]["y1"], LEVELS[lv]["y2"], LEVELS[lv]["y3"]]
        a.setdefault("renewal_history", []).append(a.pop("renewal"))  # 下一次到期时重新开始
    if a.get("status") in ("潜在", "洽谈中"):
        a["status"] = "已签约"
    vault.put("agent", a)
    vault.audit("contract uploaded")
    flash("签回合同已加密保存")
    return redirect(url_for("agent_detail", aid=aid))


@app.post("/agents/<aid>/activate")
@login_required
def agent_activate(aid):
    """第 7 步：开通，发欢迎信，加入 News 名单。"""
    a = vault.get("agent", aid) or abort(404)
    a["code"] = a.get("code") or next_code()
    a["status"] = "活跃"
    if a.get("email") and request.form.get("send"):
        tpl = et.fill(et.WELCOME, contact=a.get("contact") or a["name"], code=a["code"])
        with mailer.Outbox(vault) as box:
            box.send(a["email"], tpl["subject"], tpl["body"], agent_id=aid, kind="onboarding")
    mark_step(a, "activate")
    vault.put("agent", a)
    flash(f"{a['name']} 已开通（{a['code']}），之后会自动收到每月 News")
    return redirect(url_for("agent_detail", aid=aid))


@app.route("/agents/<aid>/contracts/<int:i>")
@login_required
def contract_download(aid, i):
    a = vault.get("agent", aid) or abort(404)
    c = a["contracts"][i]
    if not c.get("fid"):
        abort(404)
    vault.audit("contract downloaded")
    return send_file(io.BytesIO(vault.get_file(c["fid"])), download_name=c["name"], as_attachment=True)


def _contract_data(aid, i):
    a = vault.get("agent", aid) or abort(404)
    if i >= len(a.get("contracts") or []):
        abort(404)
    c = a["contracts"][i]
    if not c.get("fid") or not c["name"].lower().endswith(".docx"):
        abort(404)
    return a, c, vault.get_file(c["fid"])


@app.route("/agents/<aid>/contracts/<int:i>/page/<int:n>.png")
@login_required
def contract_page(aid, i, n):
    """排版预览的第 n 页（图片在内存里生成，不落盘）。"""
    _, _, data = _contract_data(aid, i)
    pdf = contracts.to_pdf(data) or abort(404)
    if n >= contracts.page_count(pdf):
        abort(404)
    return send_file(io.BytesIO(contracts.page_png(pdf, n)), mimetype="image/png")


@app.route("/agents/<aid>/contracts/<int:i>/edit", methods=["GET", "POST"])
@login_required
def contract_edit(aid, i):
    """在线预览 Word 合同，直接改文字后保存（改动只影响改过的段落，其余格式不变）。"""
    a, c, data = _contract_data(aid, i)
    if request.method == "POST":
        try:
            edits = {int(k): str(v) for k, v in json.loads(request.form.get("edits") or "{}").items()}
        except (ValueError, AttributeError):
            abort(400)
        if edits:
            trash_contract(a, dict(c), "在线修改前的版本")
            c["fid"] = vault.put_file(contracts.apply_edits(data, edits))
            c["edited"] = dt.date.today().isoformat()
            vault.put("agent", a)
            vault.audit("contract edited online")
            flash(f"已保存 {len(edits)} 处修改")
        else:
            flash("没有改动")
        return redirect(url_for("contract_edit", aid=aid, i=i, back=safe_back(request.form.get("back")), mode="view"))
    pdf = contracts.to_pdf(data)
    return render_template("contract_edit.html", a=a, c=c, i=i, doc=contracts.outline(data),
                           pages=contracts.page_count(pdf) if pdf else 0, mode=request.args.get("mode") or "view",
                           back=safe_back(request.args.get("back")) or url_for("agent_detail", aid=aid),
                           is_renewal=(a.get("renewal") or {}).get("contract") == i)


# ---------- 佣金结算 ----------
@app.route("/commissions")
@login_required
def commissions():
    ts = terms()
    term = request.args.get("term") or (ts[-1] if ts else "")
    agents = agents_by_id()
    comms = vault.all("commission")
    rows = sorted([enrich(c, agents, comms) for c in comms if c["term"] == term],
                  key=lambda r: (STAGES.index(r["stage"]) if r["stage"] in STAGES else 9, r["agent"].get("code") or ""))
    cfg = settings()
    return render_template("commissions.html", terms=ts, term=term, rows=rows, suggest=next_terms(ts),
                           total=sum(r["amount"] for r in rows), fees=sum(r["fees"] for r in rows),
                           master_name=cfg.get("master_base_name") if cfg.get("master_base") else None,
                           accountant=cfg.get("accountant_email"))


@app.post("/commissions/terms")
@login_required
def term_create():
    name = re.sub(r"\s+", " ", request.form.get("name") or "").strip()[:60]
    if not name:
        flash("请填学期名称")
        return redirect(url_for("commissions"))
    ts = terms()
    if name not in ts:
        orders = [c.get("term_order", 0) for c in vault.all("commission")] + [t.get("order", 0) for t in vault.all("term")]
        vault.put("term", {"name": name, "order": max(orders, default=0) + 1, "created": dt.date.today().isoformat()})
        flash(f"已新建学期「{name}」，可以开始给代理建结算单")
    return redirect(url_for("commissions", term=name))


@app.post("/commissions/terms/delete")
@login_required
def term_delete():
    name = request.form.get("name") or ""
    if any(c["term"] == name for c in vault.all("commission")):
        flash("这个学期已经有结算单，不能删除")
    else:
        for t in vault.all("term"):
            if t["name"] == name:
                vault.delete("term", t["id"])
        flash(f"已删除空学期「{name}」")
    return redirect(url_for("commissions"))


# ---------- 在读学生名册：续读学生每学期自动带进结算单 ----------
ENROLL_STATUSES = ["在读", "毕业", "离校", "转校"]


def term_pos(term, ts=None):
    """学期先后：在学期列表里的按列表；不在列表里的按学年估一个位置。"""
    ts = ts if ts is not None else terms()
    if term in ts:
        return ts.index(term)
    ay = academic_year(term or "")
    same = [i for i, t in enumerate(ts) if academic_year(t) == ay]
    return (same[0] - 0.5) if same else -1


def student_rows(st, comms, agent_id=None):
    """这个学生在以前各张结算单里的行：[(结算单, 行)]（按学生 ID 对，没 ID 的按名字对，只看同一个代理）。"""
    k = _name_key(st.get("name"))
    out = []
    for c in comms:
        if agent_id and c.get("agent_id") != agent_id:
            continue
        for r in c.get("students") or []:
            if r.get("student_id") == st["id"] or (not r.get("student_id") and _name_key(r.get("name")) == k):
                out.append((c, r))
    return out


def suggest_row(st, term, agent, comms):
    """续读学生这个学期在结算单里应该怎么写：第几年、第几个学期、付不付、学费先沿用上一期。"""
    ts = terms()
    here = term_pos(term, ts)
    before = sorted([(c, r) for c, r in student_rows(st, comms, agent.get("id")) if term_pos(c["term"], ts) < here],
                    key=lambda x: term_pos(x[0]["term"], ts))
    program = st.get("program") or "FT1"
    first = before[0][0]["term"] if before else (st.get("intake") or term)
    if program in ("FT1", "FT2", "FT3"):
        try:
            years = int(academic_year(term)[:2]) - int(academic_year(first)[:2])
        except ValueError:
            years = 0
        base = int(program[2]) if not before else int((before[0][1].get("program") or "FT1")[2:] or 1)
        program = f"FT{min(3, max(1, base + max(0, years)))}"
    paid = sum(1 for _, r in before if not r.get("nopay"))
    term_no = len({c["term"] for c, _ in before}) + 1
    nopay, note = False, ""
    limit = agent.get("pay_terms")
    if limit and paid >= int(limit):
        nopay, note = True, f"合同只付前 {limit} 个学期，已付 {paid} 个"
    elif program in ("PT", "AP") and paid >= 1:
        nopay, note = True, "兼职 / AP 只在首次缴费时付佣金"
    tuition = before[-1][1].get("tuition") if before else st.get("tuition")
    return {"name": st.get("name", ""), "program": program, "courses": st.get("courses") or "",
            "origin": st.get("origin") or "International", "tuition": tuition if tuition is not None else 0,
            "note": note or ("学费沿用上一期，请核对" if before else ""), "rate": None, "nopay": nopay,
            "term_no": term_no, "student_id": st["id"]}


def roster_candidates(term):
    """这个学期应该进结算单的在读学生：已入学、还在读、有代理、入学学期不晚于这个学期。"""
    ts = terms()
    here = term_pos(term, ts)
    agents = agents_by_id()
    out = []
    for st in vault.all("student"):
        a = agents.get(st.get("agent_id") or "")
        if not a or a.get("status") == "终止" or st.get("stage") != "已入学":
            continue
        if (st.get("enrolled_status") or "在读") != "在读":
            continue
        if st.get("intake") and term_pos(st["intake"], ts) > here:
            continue
        out.append((st, a))
    return out


def link_statement_students(c):
    """结算单里手打的学生名字，能和学生名册对上的就关联起来（同一个人不同写法也算），统计和满 6 人才不会算错。"""
    pool = vault.all("student")
    mine = [x for x in pool if x.get("agent_id") == c.get("agent_id")]
    changed = False
    for row in c.get("students") or []:
        if row.get("student_id") and vault.get("student", row["student_id"]):
            continue
        hit = _student_match(row.get("name"), mine) or _student_match(row.get("name"), pool)
        if hit:
            row["student_id"] = hit["id"]
            changed = True
            if not hit.get("commission_id"):
                hit["commission_id"] = c["id"]
                vault.put("student", hit)
    if changed:
        vault.put("commission", c)
    return c


def find_statement(agent_id, term, not_id=None):
    return next((x for x in vault.all("commission") if x.get("agent_id") == agent_id and x.get("term") == term
                 and x["id"] != not_id), None)


def statement_form(c, f):
    c["agent_id"], c["term"] = f["agent_id"], f["term"].strip()
    orders = {t: i for i, t in enumerate(terms())}
    c["term_order"] = orders.get(c["term"], len(orders) + 100)
    students = []
    for i, name in enumerate(f.getlist("s_name")):
        tuition = fnum(f.getlist("s_tuition")[i])
        if not name.strip() or tuition is None:
            continue
        students.append({"name": name.strip(), "program": f.getlist("s_program")[i],
                         "courses": f.getlist("s_courses")[i].strip(), "origin": f.getlist("s_origin")[i],
                         "tuition": tuition, "note": f.getlist("s_note")[i].strip(),
                         "rate": fnum(f.getlist("s_rate")[i])})
        sids = f.getlist("s_sid")
        if i < len(sids) and sids[i]:
            students[-1]["student_id"] = sids[i]
        old = next((x for x in c.get("students") or [] if x.get("name") == name.strip()), {})
        for k in ("period", "grade", "term_no"):  # 页面上没有的栏，保存时保留
            if old.get(k) not in (None, ""):
                students[-1][k] = old[k]
        pay = f.getlist("s_pay")
        if i < len(pay) and pay[i] == "0":
            students[-1]["nopay"] = True
    c["students"] = students
    for k in ("other_amount",):
        c[k] = fnum(f.get(k))
    for k in ("other_note", "notes"):
        c[k] = f.get(k, "").strip()
    if c.get("imported") and students:
        c["imported"] = False  # 补录了学生明细后，以系统计算为准
    return c


@app.route("/commissions/new", methods=["GET", "POST"])
@app.route("/commissions/<cid>", methods=["GET", "POST"])
@login_required
def commission_edit(cid=None):
    c = vault.get("commission", cid) if cid else {"term": request.args.get("term") or (terms() or [""])[-1],
                                                   "status": "草稿", "agent_id": request.args.get("agent"),
                                                   "students": []}
    if c is None:
        abort(404)
    agents = sorted(vault.all("agent"), key=lambda a: a.get("code") or "J9")
    if not cid and c.get("agent_id"):  # 这个代理这个学期已经有结算单了：直接打开那张，不再新建第二张
        dup = find_statement(c["agent_id"], c["term"])
        if dup:
            flash("这个代理这个学期已经有一张结算单，已为你打开")
            return redirect(url_for("commission_edit", cid=dup["id"]))
    if request.method == "POST":
        if request.form.get("delete"):
            a = vault.get("agent", c.get("agent_id")) or {}
            to_trash("commission", c, f"{a.get('name', '')} · {c.get('term', '')}")
            flash(f"结算单已放进回收站，{TRASH_DAYS} 天内可以恢复")
            return redirect(url_for("commissions", term=c["term"]))
        if c.get("locked"):
            flash("结算单已发出，金额已锁定。如需修改，请先「退回草稿」。")
            return redirect(url_for("commission_edit", cid=cid))
        term = (request.form.get("term") or "").strip()
        if term not in terms():
            flash(f"学期「{term}」不存在。请从下拉里选；新学期先在佣金结算页点「+ 新建学期」")
            return redirect(request.full_path)
        dup = find_statement(request.form.get("agent_id"), term, not_id=cid)
        if dup:
            flash("这个代理在这个学期已经有一张结算单了（同一学期只能有一张，避免重复付款）。已为你打开那张，请在那张里加学生")
            return redirect(url_for("commission_edit", cid=dup["id"]))
        c = vault.put("commission", statement_form(c, request.form))
        link_statement_students(c)
        flash("已保存，佣金已自动计算")
        session["clear_draft"] = "commission"
        return redirect(url_for("commission_edit", cid=c["id"]))
    view = enrich(c, agents_by_id()) if c.get("agent_id") else dict(c, lines=[], calc=0, stage="草稿", scheme=None)
    inbound = []
    if c.get("agent_id"):
        inbound = [(m, f) for m in vault.all("mail") if m["direction"] == "in" and m.get("agent_id") == c["agent_id"]
                   for f in m.get("attachments", [])]
    roster_pick = []
    if c.get("agent_id") and not c.get("locked"):
        inside = {x.get("student_id") for x in c.get("students") or []} | {_name_key(x.get("name")) for x in c.get("students") or []}
        comms = vault.all("commission")
        a = vault.get("agent", c["agent_id"]) or {}
        for st in sorted([x for x in vault.all("student") if x.get("agent_id") == c["agent_id"]
                          and x["id"] not in inside and _name_key(x.get("name")) not in inside],
                         key=lambda x: (x.get("stage") != "已入学", (x.get("enrolled_status") or "在读") != "在读", x.get("name", ""))):
            row = suggest_row(st, c["term"], a, comms)
            roster_pick.append({"id": st["id"], "name": st.get("name", ""), "program": row["program"], "courses": st.get("courses") or "",
                                "origin": st.get("origin") or "International", "tuition": row["tuition"], "intake": st.get("intake") or "",
                                "enrolled_status": st.get("enrolled_status") or ("在读" if st.get("stage") == "已入学" else st.get("stage") or "")})
    return render_template("commission_form.html", c=view, agents=agents, terms=terms(), inbound=inbound,
                           cfg=settings(), roster_pick=roster_pick)


@app.post("/commissions/<cid>/import-roster")
@login_required
def commission_import_roster(cid):
    """第一步只读 Excel、给你看对比（新增几个、更新几个、原来有但文件里没有的几个），确认后才写进结算单。"""
    c = vault.get("commission", cid) or abort(404)
    if c.get("locked"):
        flash("结算单已发出，金额已锁定。如需修改，请先「退回草稿」。")
        return redirect(url_for("commission_edit", cid=cid))
    f = request.files.get("file") or abort(400)
    sheets = statements.parse_roster(f.read())
    sheet = request.form.get("sheet") or c["term"]
    used = sheet if sheet in sheets else (list(sheets)[-1] if sheets else "")
    pick = sheets.get(used) or []
    if not pick:
        flash("没有在 Excel 里找到 Student Name 开头的学生名单")
        return redirect(url_for("commission_edit", cid=cid))
    have = {_name_key(x.get("name")): x for x in c.get("students") or []}
    new_keys = {_name_key(x.get("name")) for x in pick}
    rows = [dict(x, _st="更新" if _name_key(x.get("name")) in have else "新增") for x in pick]
    gone = [x for k, x in have.items() if k not in new_keys]
    a = vault.get("agent", c["agent_id"]) or {}
    return render_template("roster_confirm.html", c=c, a=a, rows=rows, gone=gone, sheet=used, data=json.dumps(pick))


@app.post("/commissions/<cid>/import-roster/apply")
@login_required
def commission_import_apply(cid):
    c = vault.get("commission", cid) or abort(404)
    if c.get("locked"):
        abort(400)
    try:
        pick = json.loads(request.form.get("data") or "[]")
    except ValueError:
        abort(400)
    if request.form.get("mode") == "replace":
        c["students"] = pick
    else:  # 合并：同名的用文件里的数据，结算单里原有、文件里没有的保留
        keys = {_name_key(x.get("name")): x for x in pick}
        keep = [x for x in c.get("students") or [] if _name_key(x.get("name")) not in keys]
        for x in pick:
            old = next((y for y in c.get("students") or [] if _name_key(y.get("name")) == _name_key(x.get("name"))), {})
            if old.get("student_id"):
                x["student_id"] = old["student_id"]
        c["students"] = keep + pick
    c["imported"] = False
    vault.put("commission", c)
    link_statement_students(c)
    flash(f"已导入 {len(pick)} 名学生（{'替换' if request.form.get('mode') == 'replace' else '合并'}），现在结算单里共 {len(c['students'])} 名")
    return redirect(url_for("commission_edit", cid=cid))


def _statement_file(c, agents):
    e = enrich(c, agents)
    data = statements.statement_xlsx(e["agent"], c, e["lines"], e["calc"])
    name = f"JA Commission Statement {e['agent'].get('code', '')} {c['term']}.xlsx"
    return e, name, data


@app.route("/commissions/<cid>/statement.xlsx")
@login_required
def commission_statement(cid):
    c = vault.get("commission", cid) or abort(404)
    _, name, data = _statement_file(c, agents_by_id())
    return send_file(io.BytesIO(data), download_name=name, as_attachment=True)


def term_phrase(term):
    """'Sep-Dec Fall 26-27' -> '26-27 Sep-Dec Fall School Semester'（和以前发给代理的邮件标题一样）。"""
    m = re.match(r"^(.*?)\s*(\d{2}-\d{2})$", term or "")
    return f"{m.group(2)} {m.group(1)} School Semester" if m and m.group(1) else term


def roster_name(a, today=None):
    """附件名照以前的写法：<代理> Student Roster Update Nov-1-2026.xlsx"""
    today = today or dt.date.today()
    r = a.get("roster") or {}
    prefix = r.get("prefix") or re.sub(r"(\s+(last\s+)?update)?(\s+[A-Za-z]{3,9}-\d{1,2}-\d{2,4})?\.xlsx$", "",
                                        r.get("name") or "", flags=re.I).strip() or f"{a.get('name', '')} Student Roster"
    return f"{prefix} Update {today.strftime('%b')}-{today.day}-{today.year}.xlsx"


def roster_attachment(c, agents):
    """代理以前的 Student Roster + 本学期新工作表。代理还没有 Roster 底稿时，新建一个只有本学期的。"""
    e = enrich(c, agents)
    a = e["agent"]
    r = a.get("roster") or {}
    base = vault.get_file(r["fid"]) if r.get("fid") else None
    label = r.get("agent_label") or statements.last_agent_label(base) or a.get("contact") or a.get("name", "")
    data = statements.roster_workbook(base, c["term"], c, e["lines"], e["scheme"], label)
    return e, roster_name(a), data


def statement_mail(c, a, e):
    """结算邮件草稿：存过的（预览页里改过的）优先，否则按模板生成。"""
    d = c.get("draft_mail") or {}
    tpl = et.fill(et.COMMISSION_ROSTER if (a.get("roster") or c.get("draft_mail")) else et.COMMISSION_STATEMENT,
                  agent=d.get("greet") or a.get("greet") or a.get("name"), term=term_phrase(c["term"]),
                  amount=money(e["calc"]))
    return {"subject": d.get("subject") or tpl["subject"], "body": d.get("body") or tpl["body"],
            "to": d.get("to") or a.get("email") or ""}


def send_statement(c, agents, box, sender=None):
    """第 1 步：锁定金额，发结算邮件给代理。附件是代理的 Student Roster（以前所有学期 + 本学期新工作表）。"""
    e, name, data = roster_attachment(c, agents)
    a = e["agent"]
    m = statement_mail(c, a, e)
    box.send(m["to"], m["subject"], m["body"], [(name, data)], agent_id=a.get("id"), kind="statement",
             sender=sender, commission_id=c["id"])
    c["locked"] = {"lines": e["lines"], "total": e["calc"], "y1_rate": y1_rate_used(e["scheme"], ay_group(c), c)}
    for prior in ay_group(c):  # 本单已包含补差，之前的单子不再重复补
        if prior["id"] != c["id"] and prior.get("locked") and any(l.get("kind") == "TOPUP" for l in e["lines"]):
            prior["topped_up_by"] = c["id"]
            vault.put("commission", prior)
    c["status"] = "已发结算单"
    c["sent_on"] = dt.date.today().isoformat()
    c["sent_file"] = {"name": name, "fid": vault.put_file(data)}
    vault.put("commission", c)
    # 发出去的这份就是代理最新的 Roster，下个学期在它后面再加工作表
    a = vault.get("agent", a["id"])
    old = a.get("roster") or {}
    a["roster"] = dict(old, name=name, fid=c["sent_file"]["fid"], updated=c["sent_on"])
    vault.put("agent", a)


@app.post("/commissions/<cid>/send")
@login_required
def commission_send(cid):
    c = vault.get("commission", cid) or abort(404)
    agents = agents_by_id()
    if c.get("locked"):
        flash("这张结算单已经发出过了")
        return redirect(url_for("commission_edit", cid=cid))
    to = (c.get("draft_mail") or {}).get("to") or agents.get(c["agent_id"], {}).get("email")
    if not to:
        flash("这个代理还没有邮箱，先在预览页填收件人，或到代理资料里补上")
        return redirect(url_for("commission_mail", cid=cid))
    with mailer.Outbox(vault) as box:
        send_statement(c, agents, box, sender=request.form.get("sender") or None)
    flash(f"{agents.get(c['agent_id'], {}).get('name', '')} 的结算邮件和 Student Roster 已发出，等代理确认并回发票")
    if request.form.get("queue"):
        return redirect(url_for("commission_queue", term=request.form["queue"], skip=request.form.get("skip") or None))
    return redirect(url_for("commission_edit", cid=cid))


@app.route("/commissions/<cid>/mail", methods=["GET", "POST"])
@login_required
def commission_mail(cid):
    """发出前预览：邮件正文可以改，附件（Student Roster）每个工作表都能直接看。"""
    c = vault.get("commission", cid) or abort(404)
    agents = agents_by_id()
    a = agents.get(c["agent_id"]) or abort(404)
    if request.method == "POST" and not c.get("locked"):
        if request.form.get("roster_reset"):
            a.pop("roster", None)
            vault.put("agent", a)
            flash("已去掉 Roster 底稿，附件改为只有本学期的新表")
        elif request.files.get("roster") and request.files["roster"].filename:
            f = request.files["roster"]
            if not f.filename.lower().endswith(".xlsx"):
                flash("请上传 .xlsx")
            else:
                data = f.read()
                old = a.get("roster") or {}
                a["roster"] = {"name": os.path.basename(f.filename), "fid": vault.put_file(data),
                               "updated": dt.date.today().isoformat(), "agent_label": old.get("agent_label", "")}
                vault.put("agent", a)
                flash("已换成新的 Roster 底稿，附件已按它重新生成")
        else:
            d = c.get("draft_mail") or {}
            for k in ("to", "subject", "body"):
                d[k] = (request.form.get(k) or "").strip()
            c["draft_mail"] = d
            if request.form.get("agent_label") is not None:
                r = a.get("roster") or {}
                r["agent_label"] = request.form.get("agent_label", "").strip()
                if a.get("roster"):
                    a["roster"] = r
                    vault.put("agent", a)
            vault.put("commission", c)
            flash("邮件草稿已保存")
        return redirect(url_for("commission_mail", cid=cid, queue=request.args.get("queue"), skip=request.args.get("skip")))
    if c.get("locked") and c.get("sent_file"):
        e = enrich(c, agents)
        name, data = c["sent_file"]["name"], vault.get_file(c["sent_file"]["fid"])
    else:
        e, name, data = roster_attachment(c, agents)
    m = statement_mail(c, a, e)
    sheets = statements.preview(data)
    r = a.get("roster") or {}
    queue = request.args.get("queue") or ""
    qinfo = None
    if queue and not c.get("locked"):
        skip = [x for x in (request.args.get("skip") or "").split(",") if x]
        q = draft_queue(queue, skip)
        qinfo = {"term": queue, "left": len(q), "skip": ",".join(skip),
                 "skip_next": ",".join(skip + [cid])}
    return render_template("commission_mail.html", c=e, a=a, m=m, att_name=name, sheets=sheets, qinfo=qinfo,
                           new_sheet=statements.sheet_title(c["term"]), roster=r,
                           agent_label=r.get("agent_label") or statements.last_agent_label(
                               vault.get_file(r["fid"]) if r.get("fid") else None) or a.get("name", ""))


@app.route("/commissions/<cid>/roster.xlsx")
@login_required
def commission_roster(cid):
    c = vault.get("commission", cid) or abort(404)
    if c.get("locked") and c.get("sent_file"):
        name, data = c["sent_file"]["name"], vault.get_file(c["sent_file"]["fid"])
    else:
        _, name, data = roster_attachment(c, agents_by_id())
    return send_file(io.BytesIO(data), download_name=name, as_attachment=True)


def draft_queue(term, skip=()):
    """本学期还没发出的草稿结算单（逐张预览、逐张发出用），顺序和佣金结算页一样按代理编号。"""
    agents = agents_by_id()
    return sorted([c for c in vault.all("commission") if c["term"] == term and stage_of(c) == "草稿"
                   and not c.get("imported") and c.get("students") and c["id"] not in skip],
                  key=lambda c: agents.get(c["agent_id"], {}).get("code") or "J9")


@app.route("/commissions/roster", methods=["GET", "POST"])
@login_required
def commission_roster_fill():
    """按在读学生名册生成这个学期各代理的结算单草稿：续读学生自动带进来，第几年、付不付都先算好，你核对后再加。"""
    term = request.values.get("term") or (terms() or [""])[-1]
    if term not in terms():
        flash("先选一个已有的学期")
        return redirect(url_for("commissions"))
    comms = vault.all("commission")
    plan = []
    for st, a in roster_candidates(term):
        cur = find_statement(a["id"], term)
        if cur and any(r.get("student_id") == st["id"] or _name_key(r.get("name")) == _name_key(st.get("name"))
                       for r in cur.get("students") or []):
            continue
        row = suggest_row(st, term, a, comms)
        plan.append({"st": st, "a": a, "row": row, "cur": cur, "locked": bool(cur and cur.get("locked")),
                     "key": st["id"]})
    plan.sort(key=lambda x: (x["a"].get("code") or "J9", x["st"].get("name", "")))
    if request.method == "POST":
        pick = set(request.form.getlist("pick"))
        orders = {t: i for i, t in enumerate(terms())}
        added, made = 0, 0
        for x in plan:
            if x["key"] not in pick or x["locked"]:
                continue
            c = find_statement(x["a"]["id"], term)
            if not c:
                c = {"agent_id": x["a"]["id"], "term": term, "term_order": orders.get(term, len(orders) + 100),
                     "status": "草稿", "students": []}
                made += 1
            row = dict(x["row"])
            t = request.form.get("tu_" + x["key"])
            if t not in (None, ""):
                row["tuition"] = fnum(t) or 0
            row["nopay"] = request.form.get("pay_" + x["key"]) == "0"
            c["students"] = (c.get("students") or []) + [row]
            vault.put("commission", c)
            added += 1
        flash(f"已把 {added} 名在读学生加进 {term} 的结算单草稿（新建 {made} 张）。都还没发出，请逐张核对学费")
        return redirect(url_for("commissions", term=term))
    return render_template("roster_fill.html", term=term, plan=plan, terms=terms())


@app.route("/commissions/send-queue")
@login_required
def commission_queue():
    """「逐张预览并发出」：不再一键全部发出，而是一张一张打开预览页，看过再发，可以跳过。"""
    term = request.args.get("term") or ""
    skip = [x for x in (request.args.get("skip") or "").split(",") if x]
    q = draft_queue(term, skip)
    if not q:
        flash(f"{term} 的草稿结算单都处理完了" + (f"（跳过了 {len(skip)} 张，还是草稿）" if skip else ""))
        return redirect(url_for("commissions", term=term))
    return redirect(url_for("commission_mail", cid=q[0]["id"], queue=term, skip=",".join(skip) or None))


@app.post("/commissions/<cid>/confirm")
@login_required
def commission_confirm(cid):
    """第 2 步：代理确认，登记发票。"""
    c = vault.get("commission", cid) or abort(404)
    inv = save_upload("invoice")
    if not inv and request.form.get("from_mail"):
        name, fid = request.form["from_mail"].split("|", 1)
        inv = {"name": name, "fid": fid, "uploaded": dt.date.today().isoformat()}
    c["invoice"] = inv
    c["confirmed_on"] = dt.date.today().isoformat()
    c["status"] = "代理已确认"
    vault.put("commission", c)
    flash("已登记代理确认" + ("和发票" if inv else "（未附发票）"))
    return redirect(url_for("commission_edit", cid=cid))


@app.post("/commissions/<cid>/accountant")
@login_required
def commission_accountant(cid):
    """第 3 步：把付款需要的信息（只有这些）发给会计。"""
    c = vault.get("commission", cid) or abort(404)
    cfg = settings()
    if not cfg.get("accountant_email"):
        flash("请先在「设置与安全」里填会计邮箱")
        return redirect(url_for("commission_edit", cid=cid))
    agents = agents_by_id()
    e, name, data = _statement_file(c, agents)
    a = e["agent"]
    method = request.form.get("method") or ("E-Transfer" if a.get("etransfer") else "Cheque")
    tpl = et.fill(et.ACCOUNTANT, agent=a.get("payee") or a.get("name"), code=a.get("code"), term=c["term"],
                  amount=money(e["amount"]), method=method, payee=a.get("payee") or a.get("name"),
                  etransfer=a.get("etransfer") or "-", bank=a.get("detail") or "-")
    files = [(name, data)]
    if c.get("invoice"):
        files.append((c["invoice"]["name"], vault.get_file(c["invoice"]["fid"])))
    with mailer.Outbox(vault) as box:
        box.send(cfg["accountant_email"], tpl["subject"], tpl["body"], files, commission_id=cid, kind="accountant")
    c.update(status="已交会计", to_accountant_on=dt.date.today().isoformat(), pay_method=method)
    vault.put("commission", c)
    flash("已发给会计付款")
    return redirect(url_for("commission_edit", cid=cid))


@app.post("/commissions/<cid>/paid")
@login_required
def commission_paid(cid):
    """第 4 步：登记付款凭证（支票 / E-Transfer 截图），可通知代理。"""
    c = vault.get("commission", cid) or abort(404)
    c["proof"] = save_upload("proof")
    c.update(status="已付", paid_on=request.form.get("paid_on") or dt.date.today().isoformat(),
             pay_method=request.form.get("method") or c.get("pay_method"), pay_ref=request.form.get("ref", ""))
    vault.put("commission", c)
    if request.form.get("notify"):
        e = enrich(c, agents_by_id())
        a = e["agent"]
        if a.get("email"):
            tpl = et.fill(et.PAYMENT_NOTICE, agent=a.get("name"), term=c["term"], amount=money(e["amount"]),
                          method=c["pay_method"], date=c["paid_on"])
            with mailer.Outbox(vault) as box:
                box.send(a["email"], tpl["subject"], tpl["body"], agent_id=a["id"], commission_id=cid, kind="statement")
    flash("已登记付款，本单结算完成")
    return redirect(url_for("commission_edit", cid=cid))


@app.post("/commissions/<cid>/reopen")
@login_required
def commission_reopen(cid):
    c = vault.get("commission", cid) or abort(404)
    c.pop("locked", None)
    c["status"] = "草稿"
    vault.put("commission", c)
    flash("已退回草稿，可以修改后重新发送")
    return redirect(url_for("commission_edit", cid=cid))


@app.route("/commissions/export")
@login_required
def commissions_export():
    term = request.args["term"]
    agents = agents_by_id()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\\/*?:\[\]]", "-", term)[:31]
    ws.append(["代理名称", "代理编号", "佣金方案", "学生数", "已缴学费总额", "Commission 金额", "状态", "发结算单", "代理确认",
               "交会计", "付款日期", "付款方式", "E-Transfer", "支票抬头"])
    comms = vault.all("commission")
    for r in sorted([enrich(c, agents, comms) for c in comms if c["term"] == term],
                    key=lambda r: r["agent"].get("code") or ""):
        a = r["agent"]
        ws.append([a.get("name"), a.get("code"), scheme_label(a), len(r.get("students", [])), r["fees"], r["amount"],
                   r["stage"], r.get("sent_on"), r.get("confirmed_on"), r.get("to_accountant_on"), r.get("paid_on"),
                   r.get("pay_method"), a.get("etransfer"), a.get("payee")])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    vault.audit("commission export")
    return send_file(buf, download_name=f"Commission {ws.title}.xlsx", as_attachment=True)


def _master(term):
    """佣金总表：在上一次的总表（POLO 原来的《代理表》）后面加上这个结算期的一页，所有代理都列上。
    生成后存成新的底表，下一个结算期接着加。返回 (文件名, 字节)。"""
    agents = agents_by_id()
    comms = vault.all("commission")
    mine = {c["agent_id"]: enrich(c, agents, comms) for c in comms if c["term"] == term}
    listed = [a for a in agents.values() if a.get("status") == "活跃" or a["id"] in mine]
    rows = [statements.master_row(a, mine.get(a["id"]), a.get("scheme_text") or scheme_label(a))
            for a in sorted(listed, key=lambda a: (a.get("code") or "J9", a.get("name") or ""))]
    cfg = settings()
    base = vault.get_file(cfg["master_base"]) if cfg.get("master_base") else None
    data = statements.master_workbook(base, term, rows)
    rec = vault.get("settings", "mail") or {"id": "mail"}
    rec["master_base"] = vault.put_file(data)
    vault.put("settings", rec)
    return f"代理表 Commission {statements.sheet_title(term)} {dt.date.today().isoformat()}.xlsx", data


@app.route("/commissions/master.xlsx")
@login_required
def commissions_master():
    fname, data = _master(request.args["term"])
    vault.audit("commission master workbook")
    return send_file(io.BytesIO(data), download_name=fname, as_attachment=True)


@app.post("/commissions/master/base")
@login_required
def commissions_master_base():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".xlsx"):
        flash("请选择《代理表》Excel（.xlsx）")
    else:
        rec = vault.get("settings", "mail") or {"id": "mail"}
        rec["master_base"] = vault.put_file(f.read())
        rec["master_base_name"] = os.path.basename(f.filename)
        vault.put("settings", rec)
        flash(f"已把 {rec['master_base_name']} 设为总表底表，以后每个结算期在它后面加一页")
    return redirect(url_for("commissions", term=request.form.get("term") or None))


@app.post("/commissions/master/send")
@login_required
def commissions_master_send():
    term = request.form["term"]
    cfg = settings()
    if not cfg.get("accountant_email"):
        flash("请先在「设置 → 结算与 AI」里填会计邮箱")
        return redirect(url_for("commissions", term=term))
    fname, data = _master(term)
    with mailer.Outbox(vault) as box:
        box.send(cfg["accountant_email"], f"Johnathan Academy agent commissions – {term}",
                 f"Hi,\n\nAttached is the agent commission summary with the {term} sheet added "
                 "(one row per agent, with payment details).\n\nThank you,\nPolo",
                 [(fname, data)], kind="accountant", sender=request.form.get("sender"))
    flash(f"总表（{term}）已发给会计 {cfg['accountant_email']}")
    return redirect(url_for("commissions", term=term))


# ---------- 开发新代理 ----------
def needs_followup(p):
    if p.get("stage") not in ("已发邮件", "已跟进") or p.get("unsubscribed"):
        return False
    last = p.get("last_email_on")
    return bool(last) and (dt.date.today() - dt.date.fromisoformat(last)).days >= 7


@app.route("/prospects")
@login_required
def prospects():
    f = {k: request.args.get(k, "") for k in ("country", "tier", "stage", "q")}
    rows = vault.all("prospect")
    countries = sorted({p.get("country", "") for p in rows if p.get("country")})
    if f["country"]:
        rows = [p for p in rows if p.get("country") == f["country"]]
    if f["tier"]:
        rows = [p for p in rows if p.get("tier") == f["tier"]]
    if f["stage"]:
        rows = [p for p in rows if (p.get("stage") or "未联系") == f["stage"]]
    if f["q"]:
        q = f["q"].lower()
        rows = [p for p in rows if q in " ".join(str(p.get(k, "")) for k in ("agency", "contact", "city", "email")).lower()]
    rows.sort(key=lambda p: ({"A": 0, "B": 1, "C": 2}.get(p.get("tier"), 3), p.get("country", ""), p.get("agency", "")))
    allp = vault.all("prospect")
    jobs = sorted(vault.all("ai_job"), key=lambda j: j["started"], reverse=True)[:5]
    return render_template("prospects.html", rows=rows, f=f, countries=countries, jobs=jobs,
                           review=[p for p in allp if p.get("stage") == "待审核"],
                           counts={s: sum(1 for p in allp if (p.get("stage") or "未联系") == s) for s in PROSPECT_STAGES},
                           followups=[p for p in allp if needs_followup(p)], regions=i18n.TARGET_REGIONS,
                           has_ai=ai.available(settings()), ai_mode=ai.mode(settings()))


def import_tracker(data: bytes) -> int:
    """Agent Tracker Excel → 潜在代理（已存在的机构跳过）。网页导入和加密收件箱共用。"""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    existing = {(p.get("agency") or "").lower() for p in vault.all("prospect")}
    n = 0

    def val(r, idx, *names):
        for nm in names:
            if nm in idx and r[idx[nm]] not in (None, ""):
                v = str(r[idx[nm]]).strip()
                if not v.lower().startswith(("not publicly", "not separately", "to confirm")):
                    return v
        return ""

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows or "Agency" not in [str(h).strip() for h in rows[0] if h]:
            continue
        idx = {str(h).strip(): i for i, h in enumerate(rows[0]) if h}
        for r in rows[1:]:
            agency = val(r, idx, "Agency")
            if not agency or agency.lower() in existing:
                continue
            existing.add(agency.lower())
            grade = val(r, idx, "Lead Grade", "Research Completeness")[:1]
            vault.put("prospect", {
                "agency": agency, "country": val(r, idx, "Country"),
                "city": val(r, idx, "City / Office", "Office / City", "Office / Address"),
                "contact": val(r, idx, "Contact Person", "Contact Name"), "role": val(r, idx, "Role", "Title / Role"),
                "email": val(r, idx, "Partnership Email", "Direct Email", "Email", "General Email"),
                "phone": val(r, idx, "Phone", "Phone / WhatsApp"), "whatsapp": val(r, idx, "WhatsApp"),
                "website": val(r, idx, "Website"), "tier": grade if grade in "ABC" else "",
                "priority": val(r, idx, "Priority"), "k12_fit": val(r, idx, "G8-12 Fit", "High School / G8-12 Fit",
                                                                      "G8-12 / High School Fit"),
                "notes": val(r, idx, "Notes", "Verification / Notes", "Verification Notes", "Recommended First Contact"),
                "source_url": val(r, idx, "Source URL"), "stage": "未联系", "source": "Agent Tracker 导入"})
            n += 1
    return n


@app.post("/prospects/import")
@login_required
def prospects_import():
    f = request.files.get("file") or abort(400)
    n = import_tracker(f.read())
    flash(f"从 Tracker 导入 {n} 个潜在代理（已存在的自动跳过）")
    return redirect(url_for("prospects"))


def _run_search(job_id, cfg, countries, n, extra):
    job = vault.get("ai_job", job_id)
    exclude = {p.get("agency", "") for p in vault.all("prospect")} | {a.get("name", "") for a in vault.all("agent")}
    found = 0

    def progress(msg):
        job["progress"] = msg
        vault.put("ai_job", job)

    try:
        for country in countries:
            progress(f"正在搜索 {i18n.COUNTRY_ZH.get(country, country)}…")
            for lead in ai.search_agencies(cfg, country, n, extra, exclude, (i18n.lang_for(country) or "").split("-")[0] or None, progress):
                vault.put("prospect", {**lead, "tier": lead.pop("size_tier", ""), "stage": "待审核",
                                       "source": f"AI 搜索（{ {'local': '本地', 'hybrid': '本地 + GPT'}.get(ai.mode(cfg), 'Claude')}）"
                                                 f" {dt.date.today().isoformat()}"})
                exclude.add(lead["agency"])
                found += 1
        job.update(status="完成", progress=f"找到 {found} 个，等待你审核")
    except Exception as e:  # 失败原因显示在页面上
        job.update(status="失败", progress=str(e)[:300])
    vault.put("ai_job", job)


@app.post("/prospects/search")
@login_required
def prospects_search():
    cfg = settings()
    if not ai.available(cfg):
        flash("请先在「设置与安全」里设置 AI：本地模型地址 + 搜索地址，或 Claude API Key")
        return redirect(url_for("prospects"))
    countries = request.form.getlist("countries")
    if not countries:
        flash("请至少选一个国家")
        return redirect(url_for("prospects"))
    n = min(int(request.form.get("n") or 10), 25)
    job = vault.put("ai_job", {"countries": countries, "n": n, "status": "进行中", "progress": "开始搜索…",
                               "started": dt.datetime.now().isoformat(timespec="minutes")})
    threading.Thread(target=_run_search, args=(job["id"], cfg, countries, n, request.form.get("extra", "")),
                     daemon=True).start()
    flash("AI 正在联网搜索，每个国家约需 2–10 分钟，完成后结果会出现在「待审核」里")
    return redirect(url_for("prospects"))


@app.post("/prospects/review")
@login_required
def prospects_review():
    keep = set(request.form.getlist("keep"))
    for p in vault.all("prospect"):
        if p.get("stage") == "待审核" and p["id"] in set(request.form.getlist("ids")):
            if p["id"] in keep:
                p["stage"] = "未联系"
                vault.put("prospect", p)
            else:
                to_trash("prospect", p, p.get("agency") or p.get("email") or "", "AI 搜索结果审核时没保留")
    flash("审核完成")
    return redirect(url_for("prospects"))


@app.route("/prospects/<pid>", methods=["GET", "POST"])
@login_required
def prospect_detail(pid):
    p = vault.get("prospect", pid) or abort(404)
    if request.method == "POST":
        for k in ("agency", "country", "city", "contact", "role", "email", "phone", "whatsapp", "website", "tier",
                  "stage", "notes"):
            if k in request.form:
                p[k] = request.form[k].strip()
        vault.put("prospect", p)
        flash("已保存")
        return redirect(url_for("prospect_detail", pid=pid))
    mails = sorted([m for m in vault.all("mail") if m.get("prospect_id") == pid], key=lambda m: m["at"], reverse=True)
    return render_template("prospect_detail.html", p=p, mails=mails, lang=i18n.lang_for(p.get("country")))


@app.post("/prospects/<pid>/convert")
@login_required
def prospect_convert(pid):
    """潜在代理谈成了：转成代理，入驻流程从第 3 步继续。"""
    p = vault.get("prospect", pid) or abort(404)
    a = vault.put("agent", {"name": p["agency"], "contact": p.get("contact", ""), "email": p.get("email", ""),
                            "phone": p.get("phone", ""), "country": p.get("country", ""), "city": p.get("city", ""),
                            "website": p.get("website", ""), "status": "洽谈中", "level": "standard",
                            "rates": [20, 10, 5], "source": "开发新代理", "contracts": [],
                            "onboarding": {"contact": p.get("first_email_on") or dt.date.today().isoformat(),
                                           "meeting": dt.date.today().isoformat()}})
    p["stage"] = "已转为代理"
    p["agent_id"] = a["id"]
    vault.put("prospect", p)
    for m in vault.all("mail"):
        if m.get("prospect_id") == pid:
            m["agent_id"] = a["id"]
            vault.put("mail", m)
    flash("已转为代理，接下来：申请表与背景核实")
    return redirect(url_for("agent_detail", aid=a["id"]))


@app.route("/prospects/outreach", methods=["GET", "POST"])
@login_required
def outreach():
    ids = dict.fromkeys(request.form.getlist("ids") if request.method == "POST" else request.args.getlist("ids"))
    picked = [p for p in (vault.get("prospect", i) for i in ids) if p]
    if request.method == "POST" and request.form.get("go"):
        english = {"subject": request.form["subject"], "body": request.form["body"]}
        custom = {k[3:]: {"label": i18n.LANG_LABELS.get(k[3:], k[3:]), "subject": "",
                          "body": v} for k, v in request.form.items() if k.startswith("tr_") and v.strip()}
        t = vault.get("template", request.form.get("tpl", ""))
        if t and request.form.get("save_tpl"):
            t.update(subject=english["subject"], body=english["body"])
            t.setdefault("translations", {}).update({k: v["body"] for k, v in custom.items()})
            t["edited"] = True
            vault.put("template", t)
        kit = kit_link()
        left = i18n.unfilled(*(i18n.fill_links(x, kit) for x in
                               [english["subject"], english["body"]] + [v["body"] for v in custom.values()]))
        if left:
            flash("还没发：邮件里还有没填的地方 " + "、".join("{" + x + "}" for x in left) +
                  ("。资料包链接请到 设置 → 合作伙伴资料包链接 填好" if "kit_link" in left else "") + "，改好再发（你改的内容都还在）。")
            keep = {"english": english, "custom": custom}
        else:
            keep = None
    else:
        keep = None
    if request.method == "POST" and request.form.get("go") and keep is None:
        english = {"subject": request.form["subject"], "body": request.form["body"]}
        custom = {k[3:]: {"label": i18n.LANG_LABELS.get(k[3:], k[3:]), "subject": "",
                          "body": v} for k, v in request.form.items() if k.startswith("tr_") and v.strip()}
        sent = skipped = 0
        follow = request.form.get("kind") == "followup"
        kit = kit_link()
        with mailer.Outbox(vault) as box:
            for p in picked:
                if not p.get("email") or p.get("unsubscribed"):
                    skipped += 1
                    continue
                lang = i18n.lang_for(p.get("country"))
                subject, body, _ = i18n.compose(p, english, custom.get(lang, False), kit)
                box.send(p["email"], subject, body, prospect_id=p["id"], kind="outreach")
                today = dt.date.today().isoformat()
                p["first_email_on"] = p.get("first_email_on") or today
                p["last_email_on"] = today
                p["emails_sent"] = p.get("emails_sent", 0) + 1
                p["stage"] = "已跟进" if follow or p.get("stage") in ("已发邮件", "已跟进") else "已发邮件"
                vault.put("prospect", p)
                sent += 1
        flash(f"已发出 {sent} 封{'跟进' if follow else '开发'}邮件" + (f"，{skipped} 个没有邮箱或已退订，已跳过" if skipped else ""))
        return redirect(url_for("prospects"))
    follow = request.values.get("kind") == "followup"
    if keep:  # 被拦下：按刚才勾的收件人和改过的内容重新显示
        picked = [p for p in (vault.get("prospect", i) for i in request.form.getlist("ids")) if p]
    # 收件人按地区选：所有能发的潜在代理都列出来；从列表页勾过的只勾那些，没勾过就默认全选
    pool = [p for p in vault.all("prospect") if p.get("email") and not p.get("unsubscribed")
            and p.get("stage") not in ("待审核", "已转为代理", "不合适")]
    chosen = {p["id"] for p in picked}
    pool_ids = {p["id"] for p in pool}
    pool += [p for p in picked if p["id"] not in pool_ids and p.get("email") and not p.get("unsubscribed")]
    groups = i18n.recipient_groups([{"id": p["id"], "label": p.get("agency") or p.get("contact") or p["email"],
                                     "sub": f"{p['email']} · 已发 {p.get('emails_sent') or 0} 封", "country": p.get("country"),
                                     "checked": p["id"] in chosen if chosen else True} for p in pool])
    langs = sorted({i18n.lang_for(p.get("country")) for p in pool} - {None})
    tpls = all_templates()
    mine = [t for t in tpls if t["kind"] == ("followup" if follow else "outreach")] or tpls
    tpl = next((t for t in tpls if t["id"] == request.values.get("tpl")), None) or \
        next((t for t in mine if t.get("seed", "").startswith("promo-")), None) or \
        next((t for t in mine if "推荐" in t["name"]), mine[0])
    labels = i18n.LANG_LABELS
    trs = {l: {"label": labels.get(l, l), "body": i18n.translation_for(tpl, l)} for l in langs}
    if keep:
        for l in langs:
            trs[l]["body"] = keep["custom"].get(l, {}).get("body", "")
    return render_template("outreach.html", picked=picked, groups=groups, english=keep["english"] if keep else tpl, langs=langs,
                           kind="followup" if follow else "", tpl=tpl, tpls=tpls, translations=trs,
                           has_ai=ai.available(settings()), ai_mode=ai.mode(settings()), has_kit=bool(kit_link()))


def all_templates():
    """邮件模板库；第一次打开时放入默认模板（新版开发邮件、原短版、跟进邮件）。"""
    ts = vault.all("template")
    if not ts:
        for t in i18n.DEFAULT_TEMPLATES:
            vault.put("template", json.loads(json.dumps(t)))
        ts = vault.all("template")
    flags = vault.get("settings", "flags") or {"id": "flags"}
    if flags.get("promo_seeded") != i18n.PROMO_VERSION:
        # 分阶段推广邮件：没有的补上，旧版本（还是系统原文的）更新；POLO 删掉或改过的不动
        have = {t.get("seed"): t for t in ts if t.get("seed")}
        for t in i18n.PROMO_TEMPLATES:
            cur = have.get(t["seed"])
            if cur is None and t["seed"] not in flags.get("promo_seen", []):
                vault.put("template", json.loads(json.dumps(t)))
            elif cur is not None and not cur.get("edited"):
                cur.update(json.loads(json.dumps(t)))
                vault.put("template", cur)
        flags["promo_seen"] = sorted(set(flags.get("promo_seen", [])) | {t["seed"] for t in i18n.PROMO_TEMPLATES})
        flags["promo_seeded"] = i18n.PROMO_VERSION
        vault.put("settings", flags)
        ts = vault.all("template")
    return sorted(ts, key=lambda t: (t.get("kind") != "outreach", t.get("kind", ""), t["name"]))


@app.route("/mail/templates", methods=["GET", "POST"])
@app.route("/mail/templates/<tid>", methods=["GET", "POST"])
@login_required
def mail_templates(tid=None):
    tpls = all_templates()
    t = next((x for x in tpls if x["id"] == tid), None) if tid else None
    if request.method == "POST":
        if request.form.get("delete") and t:
            to_trash("template", t, t.get("name", ""))
            flash(f"模板已放进回收站，{TRASH_DAYS} 天内可以恢复")
            return redirect(url_for("mail_templates"))
        t = t or {"translations": {}}
        for k in ("name", "kind", "subject", "body"):
            t[k] = request.form.get(k, "").strip()
        t["edited"] = True
        t = vault.put("template", t)
        flash("模板已保存")
        return redirect(url_for("mail_templates", tid=t["id"]))
    if t is None and not tid and request.args.get("new") != "1" and tpls:
        t = tpls[0]  # 打开页面时直接显示第一个模板，不是空白的新建表单
    return render_template("templates.html", tpls=tpls, t=t,
                           labels=i18n.LANG_LABELS)


def _docx_template(data, filename):
    """把 Word 文件转成邮件模板：第一行如果是「Subject: …」或「主题：…」就当主题，否则用文件名；其余段落是正文。"""
    import docx as _docx
    d = _docx.Document(io.BytesIO(data))
    paras = [p.text.rstrip() for p in d.paragraphs]
    for tb in d.tables:  # 表格里的字也收进来（每行一段）
        for row in tb.rows:
            paras.append("  ".join(c.text.strip() for c in row.cells if c.text.strip()))
    while paras and not paras[0].strip():
        paras.pop(0)
    base = os.path.splitext(os.path.basename(filename or "Word 模板"))[0]
    subject = base
    if paras:
        m = re.match(r"^\s*(subject|主题|標題|标题)\s*[:：]\s*(.+)$", paras[0], re.I)
        if m:
            subject = m.group(2).strip()
            paras.pop(0)
            while paras and not paras[0].strip():
                paras.pop(0)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()
    return {"name": base, "subject": subject, "body": body, "translations": {}, "edited": True,
            "source": filename}


@app.post("/mail/templates/upload")
@login_required
def mail_templates_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".docx"):
        flash("请选一个 Word 文件（.docx）。旧的 .doc 请先在 Word 里「另存为」.docx")
        return redirect(url_for("mail_templates"))
    try:
        t = _docx_template(f.read(), f.filename)
    except Exception as e:
        flash(f"读不了这个 Word 文件：{e}")
        return redirect(url_for("mail_templates"))
    if not t["body"]:
        flash("这个 Word 文件里没有文字")
        return redirect(url_for("mail_templates"))
    t["kind"] = request.form.get("kind") or "outreach"
    t = vault.put("template", t)
    flash("已从 Word 生成模板，请核对主题和正文，有需要直接改了保存")
    return redirect(url_for("mail_templates", tid=t["id"]))


@app.post("/prospects/translate")
@login_required
def prospects_translate():
    cfg = settings()
    if not ai.available(cfg):
        return {"error": "请先在设置里设置 AI（本地模型或 Claude API Key）"}, 400
    lang = request.form["lang"]
    try:
        out = ai.translate(cfg, request.form["subject"], request.form["body"],
                           i18n.LANG_LABELS.get(lang, lang))
    except Exception as e:
        return {"error": str(e)[:300]}, 500
    return out


# ---------- 邮件 ----------
@app.route("/mail")
@login_required
def mail():
    box = request.args.get("box", "in")
    f = {k: request.args.get(k, "") for k in ("q", "who", "unread")}
    agents = agents_by_id()
    prospects_ = {p["id"]: p for p in vault.all("prospect")}
    msgs = sorted([m for m in vault.all("mail") if m["direction"] == box], key=lambda m: m["at"], reverse=True)
    if f["who"] == "agent":
        msgs = [m for m in msgs if m.get("agent_id")]
    elif f["who"] == "prospect":
        msgs = [m for m in msgs if m.get("prospect_id") and not m.get("agent_id")]
    elif f["who"] == "other":
        msgs = [m for m in msgs if not m.get("agent_id") and not m.get("prospect_id")]
    elif f["who"]:
        msgs = [m for m in msgs if m.get("agent_id") == f["who"]]
    if f["unread"]:
        msgs = [m for m in msgs if m.get("status") == "未读"]
    if f["q"]:
        q = f["q"].lower()
        msgs = [m for m in msgs if q in " ".join([m.get("subject") or "", m.get("from") or "", m.get("to") or "",
                                                  (agents.get(m.get("agent_id")) or {}).get("name", ""),
                                                  (prospects_.get(m.get("prospect_id")) or {}).get("agency", ""),
                                                  (m.get("body") or "")[:2000]]).lower()]
    per, page = 50, max(1, int(request.args.get("page") or 1))
    pages = max(1, (len(msgs) + per - 1) // per)
    page = min(page, pages)
    camps = sorted(vault.all("campaign"), key=lambda c: c.get("next_at") or "9")
    return render_template("mail.html", box=box, msgs=msgs[(page - 1) * per:page * per], n=len(msgs), page=page, pages=pages,
                           f=f, agents=agents, prospects=prospects_, campaigns=camps,
                           unread_n=sum(1 for m in vault.all("mail") if m["direction"] == "in" and m.get("status") == "未读"),
                           agent_opts=sorted([a for a in agents.values() if a.get("status") in ("活跃", "已签约", "洽谈中")],
                                             key=lambda a: a.get("name", "").lower()),
                           live=mailer.mail_on(settings()))


def _blank_hint(left):
    return ("还没发：邮件里还有没替换的地方 " + "、".join(left) +
            ("。资料包链接请到 设置 → 合作伙伴资料包链接 填好" if "{kit_link}" in left or "{资料包链接}" in left else "") +
            "。改好再发（你写的内容都还在）。")


def _compose_page(c=None):
    """写邮件页。c = 已经写好的内容（预览后返回修改、被拦下时都不丢）。"""
    agents = sorted([a for a in vault.all("agent") if a.get("email")], key=lambda a: a.get("code") or "J9")
    pre = request.args.get("agent")
    chosen = set(c["agent_ids"]) if c else None
    groups = i18n.recipient_groups([{"id": a["id"], "label": f"{a.get('code') or ''} {a['name']}".strip(),
                                     "sub": a["email"] + ("" if a.get("status") == "活跃" else f" · {a.get('status') or '未激活'}"),
                                     "country": a.get("country"),
                                     "checked": (a["id"] in chosen) if chosen is not None else
                                     (a["id"] == pre if pre else a.get("status") == "活跃")}
                                    for a in agents if not a.get("unsubscribed")])
    return render_template("compose.html", agents=agents, pre=pre, groups=groups, tpls=all_templates(), c=c or {},
                           placeholders=mailer.PLACEHOLDERS,
                           kit=[x for x in all_assets() if x.get("url") and x.get("share")])


@app.route("/mail/compose", methods=["GET", "POST"])
@login_required
def compose():
    """写邮件：写内容 → 选收件人 → 预览（可先发一封给自己）→ 确认发送。不会一点就群发。"""
    if request.method == "GET":
        return _compose_page()
    f = request.form
    c = {"subject": f.get("subject", ""), "body": f.get("body", ""), "audience": "选定代理",
         "agent_ids": f.getlist("agent_ids"), "cadence": f.get("cadence") or "立即发送", "sender": f.get("sender") or None,
         "send_at": f.get("send_at") or ""}
    action = f.get("action") or "preview"
    if action == "edit":
        return _compose_page(c)
    recips = [a for a in mailer.recipients(vault, c) if not a.get("unsubscribed")]
    kit = kit_link()
    left = mailer.leftover(*(mailer.render(x, recips[0] if recips else {"name": "X"}, kit) for x in (c["subject"], c["body"])))
    if left:
        flash(_blank_hint(left))
        return _compose_page(c)
    if not recips:
        flash("还没选收件人：在下面按地区勾选代理")
        return _compose_page(c)
    if c["cadence"] != "立即发送" and not c["send_at"] and c["cadence"] == "仅一次（定时）":
        flash("定时发送请填「首次发送时间」")
        return _compose_page(c)
    sender = c["sender"] or (mailer.account_for(settings(), "news") or {}).get("user") or ""
    if action == "test":
        to = (f.get("test_to") or "").strip()
        if "@" not in to:
            flash("请填测试邮件发到哪个邮箱")
        else:
            with mailer.Outbox(vault) as box:
                a0 = recips[0]
                box.send(to, "[测试] " + mailer.render(c["subject"], a0, kit), mailer.render(c["body"], a0, kit),
                         kind="news", sender=c["sender"])
            flash(f"测试邮件已发到 {to}（按 {recips[0]['name']} 的称呼替换），请查收后再确认群发")
        action = "preview"
    if action == "preview":
        samples = [{"a": a, "subject": mailer.render(c["subject"], a, kit), "body": mailer.render(c["body"], a, kit)}
                   for a in recips]
        return render_template("compose_preview.html", c=c, samples=samples, sender=sender,
                               test_to=f.get("test_to") or settings().get("digest_to") or sender)
    if action != "send":
        abort(400)
    if c["cadence"] == "立即发送" and not c["send_at"]:
        sent = mailer.send_to_agents(vault, recips, c["subject"], c["body"], sender=c["sender"], kit_link=kit)
        flash(f"已发出 {len(sent)} 封邮件")
        session["clear_draft"] = "compose"
        return redirect(url_for("mail", box="out"))
    c.update(active=True, next_at=c.pop("send_at") or dt.datetime.now().isoformat(timespec="minutes"),
             created=dt.date.today().isoformat())
    vault.put("campaign", c)
    flash(f"定时推送已创建，首次 {c['next_at'].replace('T', ' ')}，发给 {len(recips)} 个代理")
    session["clear_draft"] = "compose"
    return redirect(url_for("mail"))


@app.post("/mail/campaign/<cid>")
@login_required
def campaign_toggle(cid):
    c = vault.get("campaign", cid) or abort(404)
    if request.form.get("delete"):
        to_trash("campaign", c, c.get("subject", ""))
        flash(f"定时推送已放进回收站，{TRASH_DAYS} 天内可以恢复")
    elif request.form.get("catchup"):
        sent = mailer.send_campaign(vault, c)
        flash(f"已补发「{c['subject']}」{len(sent)} 封" + (f"，下次 {c['next_at'].replace('T', ' ')}" if c.get("next_at") else ""))
    elif request.form.get("skip"):
        mailer.advance(c, dt.datetime.now())
        vault.put("campaign", c)
        flash("这次已跳过" + (f"，下次 {c['next_at'].replace('T', ' ')}" if c.get("next_at") else "，这条一次性推送已结束"))
    else:
        c["active"] = not c.get("active")
        vault.put("campaign", c)
    return redirect(url_for("mail"))


@app.post("/mail/fetch")
@login_required
def mail_fetch():
    try:
        flash(f"收到 {mailer.fetch_inbox(vault)} 封新邮件")
    except Exception as e:
        flash(f"收信失败：{e}")
    return redirect(url_for("mail"))


@app.route("/mail/msg/<mid>")
@login_required
def mail_msg(mid):
    m = vault.get("mail", mid) or abort(404)
    if m.get("status") == "未读":
        m["status"] = "已读"
        vault.put("mail", m)
    return render_template("mail_msg.html", m=m, a=vault.get("agent", m.get("agent_id")) if m.get("agent_id") else None,
                           p=vault.get("prospect", m.get("prospect_id")) if m.get("prospect_id") else None)


# ---------- 学生申请进度 ----------


def student_from_form(st, f):
    for k in ("name", "agent_id", "program", "grade", "intake", "country", "courses", "notes", "origin", "enrolled_status"):
        if k in f:
            st[k] = f.get(k, "").strip()
    st["tuition"] = fnum(f.get("tuition"))
    new = f.get("stage")
    if new in STUDENT_STAGES and new != st.get("stage"):
        st["stage"] = new
        st.setdefault("history", {})[new] = f.get("stage_date") or dt.date.today().isoformat()
    return st


_adm_last = {"at": 0, "result": None, "error": None}


def sync_admissions(force=False):
    """同步官网入学申请（最多每 10 分钟一次，除非手动点「立即同步」）。"""
    if not (admissions.enabled() or ap_courses.enabled()) or (not force and time.time() - _adm_last["at"] < 600):
        return _adm_last
    _adm_last["at"] = time.time()
    if admissions.enabled():
        try:
            _adm_last.update(result=admissions.sync(vault, STUDENT_STAGES), error=None)
            if _adm_last["result"]["new"]:
                vault.audit(f"admissions sync: {_adm_last['result']['new']} new")
        except Exception as e:  # noqa: BLE001  官网数据库连不上不影响代理系统
            _adm_last["error"] = f"{type(e).__name__}: {e}"[:200]
    if ap_courses.enabled():
        try:
            r = ap_courses.sync(vault)
            if r["new"]:
                vault.audit(f"AP courses sync: {r['new']} new")
        except Exception as e:  # noqa: BLE001  AP 系统连不上不影响代理系统
            app.logger.warning("AP courses sync failed: %s", e)
    return _adm_last


@app.post("/students/sync")
@login_required
def students_sync():
    r = sync_admissions(force=True)
    if r["error"]:
        flash(f"同步官网申请失败：{r['error']}")
    elif r["result"]:
        x = r["result"]
        flash(f"已同步官网申请：新增 {x['new']} 份，更新 {x['updated']} 份；待分配代理 {x['unassigned']} 份")
    return redirect(url_for("students", **({"stage": "待分配"} if r.get("result") and r["result"]["unassigned"] else {})))


@app.post("/students/<sid>/assign")
@login_required
def student_assign(sid):
    st = vault.get("student", sid) or abort(404)
    aid = request.form.get("agent_id", "")
    if aid == "self":
        aid = ""
    if aid and not vault.get("agent", aid):
        abort(400)
    st.update(agent_id=aid, agent_manual=True, agent_auto="")
    if not aid:
        st["uses_agent"] = False  # 选「学生自己申请」= 确认没有代理，不再出现在待分配里
    vault.put("student", st)
    flash(f"{st.get('name', '')}：已分配给 {vault.get('agent', aid)['name']}" if aid else f"{st.get('name', '')}：标为学生自己申请")
    back = request.form.get("back") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//") else url_for("students"))


@app.route("/students")
@login_required
def students():
    sync_admissions()
    f = {k: request.args.get(k, "") for k in ("stage", "agent", "intake", "q")}
    cay = current_ay()
    f["ay"] = request.args.get("ay", cay)  # 默认只看本学年：本学年入学的 + 还在读的；选「全部学年」看历届
    agents = agents_by_id()
    rows = vault.all("student")
    ays = sorted({academic_year(s.get("intake") or "") for s in rows if s.get("intake")} | {cay}, reverse=True)
    unassigned = [s for s in rows if (s.get("web_no") or s.get("agent_hint")) and s.get("uses_agent") and not s.get("agent_id")]
    if f["ay"] and not f["q"] and f["stage"] != "待分配":  # 搜名字、看待分配时不限学年
        rows = [s for s in rows if academic_year(s.get("intake") or "") == f["ay"]
                or (f["ay"] == cay and s.get("stage") == "已入学" and (s.get("enrolled_status") or "在读") == "在读")
                or (f["ay"] == cay and not s.get("intake") and s.get("stage") not in ("已入学", "未入学"))]
    intakes = sorted({s.get("intake") for s in rows if s.get("intake")})
    counts = {g: sum(1 for s in rows if s.get("stage") == g) for g in STUDENT_STAGES}
    if f["stage"] == "待分配":
        rows = unassigned
    elif f["stage"] in ENROLL_STATUSES:
        rows = [s for s in rows if s.get("stage") == "已入学" and (s.get("enrolled_status") or "在读") == f["stage"]]
    elif f["stage"]:
        rows = [s for s in rows if s.get("stage") == f["stage"]]
    if f["agent"]:
        rows = [s for s in rows if s.get("agent_id") == f["agent"]]
    if f["intake"]:
        rows = [s for s in rows if s.get("intake") == f["intake"]]
    if f["q"]:
        q = f["q"].lower()
        rows = [s for s in rows if q in (s.get("name", "") + " " + agents.get(s.get("agent_id"), {}).get("name", "")).lower()]
    rows.sort(key=lambda s: (STUDENT_STAGES.index(s["stage"]) if s.get("stage") in STUDENT_STAGES else 9,
                             max((s.get("history") or {"": ""}).values())), reverse=False)
    return render_template("students.html", rows=rows, agents=agents, counts=counts, f=f, intakes=intakes, ays=ays, cay=cay,
                           unassigned=len(unassigned), adm_on=admissions.enabled(), adm=_adm_last,
                           agent_list=sorted(agents.values(), key=lambda a: a.get("name", "")))


@app.route("/students/new", methods=["GET", "POST"])
@app.route("/students/<sid>", methods=["GET", "POST"])
@login_required
def student_edit(sid=None):
    st = vault.get("student", sid) if sid else {"stage": "", "agent_id": request.args.get("agent", ""),
                                                 "program": "FT1", "intake": (terms() or [""])[-1], "history": {}}
    if st is None:
        abort(404)
    if request.method == "POST":
        if request.form.get("delete"):
            to_trash("student", st, st.get("name", ""))
            flash(f"学生已放进回收站，{TRASH_DAYS} 天内可以恢复")
            return redirect(url_for("students"))
        if not st.get("stage") and not request.form.get("stage"):
            st["stage"] = "收到申请"
            st.setdefault("history", {})["收到申请"] = dt.date.today().isoformat()
        before = st.get("agent_id")
        st = student_from_form(st, request.form)
        if st.get("web_no") and st.get("agent_id") != before:
            st.update(agent_manual=True, agent_auto="")
        doc = save_upload("doc")
        if doc:
            st.setdefault("docs", []).append(doc)
        st = vault.put("student", st)
        flash("已保存")
        session["clear_draft"] = "student"
        return redirect(url_for("student_edit", sid=st["id"]))
    agents = sorted(vault.all("agent"), key=lambda a: a.get("name", ""))
    paid_rows = sorted(student_rows(st, vault.all("commission")), key=lambda x: term_pos(x[0]["term"])) if st.get("id") else []
    return render_template("student_form.html", st=st, agents=agents, terms=terms(), agent=agents_by_id().get(st.get("agent_id")),
                           paid_rows=paid_rows, agents_map=agents_by_id())


@app.post("/students/<sid>/stage")
@login_required
def student_stage(sid):
    st = vault.get("student", sid) or abort(404)
    new = request.form.get("stage")
    if new in STUDENT_STAGES:
        st["stage"] = new
        st.setdefault("history", {})[new] = dt.date.today().isoformat()
        vault.put("student", st)
        flash(f"{st['name']}：{new}")
    back = request.form.get("back") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//") else url_for("student_edit", sid=sid))


@app.post("/students/<sid>/to-statement")
@login_required
def student_to_statement(sid):
    """已入学的学生一键加进该代理这个学期的结算单（没有就新建草稿）。"""
    st = vault.get("student", sid) or abort(404)
    if not st.get("agent_id") or not st.get("intake"):
        flash("先填写代理和入学学期")
        return redirect(url_for("student_edit", sid=sid))
    c = next((c for c in vault.all("commission") if c["agent_id"] == st["agent_id"] and c["term"] == st["intake"]), None)
    if c and c.get("locked"):
        flash("这个学期的结算单已经发出，金额已锁定。请先在结算单里「退回草稿」再加。")
        return redirect(url_for("commission_edit", cid=c["id"]))
    if not c:
        orders = {t: i for i, t in enumerate(terms())}
        c = {"agent_id": st["agent_id"], "term": st["intake"], "term_order": orders.get(st["intake"], len(orders) + 100),
             "status": "草稿", "students": []}
    row = {"name": st["name"], "program": st.get("program") or "FT1", "courses": st.get("courses") or "",
           "origin": st.get("origin") or "International", "tuition": st.get("tuition") or 0, "note": "", "rate": st.get("rate"),
           "student_id": st["id"]}
    c["students"] = [r for r in c.get("students", []) if r.get("student_id") != st["id"]] + [row]
    c = vault.put("commission", c)
    st["commission_id"] = c["id"]
    vault.put("student", st)
    flash(f"已加入 {st['intake']} 结算单，佣金已自动计算")
    return redirect(url_for("commission_edit", cid=c["id"]))


# ---------- 合同续签 ----------
RENEW_DAYS = 120   # 到期前多少天开始出现在续签列表
AUTO_DRAFT_DAYS = 90  # 到期前多少天系统自动生成续签合同（只生成，不发送）


def current_ay(today=None):
    """现在所在的学年：9 月起算新学年，例如 2026-10 → 26-27。"""
    today = today or dt.date.today()
    y = today.year % 100 if today.month >= 9 else today.year % 100 - 1
    return f"{y:02d}-{y + 1:02d}"


def last_ay(today=None):
    today = today or dt.date.today()
    y = today.year % 100 if today.month >= 9 else today.year % 100 - 1
    return f"{y - 1:02d}-{y:02d}"


def agent_ay_stats(aid, ay, comms=None, agents=None):
    comms = comms if comms is not None else vault.all("commission")
    agents = agents or agents_by_id()
    mine = [c for c in comms if c["agent_id"] == aid and academic_year(c["term"]) == ay]
    names = {(s.get("name") or "").lower() for c in mine for s in c.get("students", [])}
    ft1 = {(s.get("name") or "").lower() for c in mine for s in c.get("students", []) if s.get("program") == "FT1"}
    return {"ft1": len(ft1), "students": len(names), "commission": sum(enrich(c, agents, comms)["amount"] for c in mine),
            "fees": sum(total_fees(c) for c in mine), "terms": len(mine)}


def suggest_level(a, stats):
    """上一学年第一年学生满 6 人建议高级；旧合同第一年 25% 以上的，建议高级，避免续签后比例变低。"""
    if stats["ft1"] >= 6:
        return "premier"
    if a.get("level") in LEVELS:
        return a["level"]
    return "premier" if (a.get("rates") or [0])[0] >= LEVELS["premier"]["y1"] else "standard"


def renewal_period(a):
    old = a.get("contract_expiry")
    start = dt.date.fromisoformat(old) + dt.timedelta(days=1) if old and days_left(old) >= 0 else dt.date.today()
    return contracts.default_period(start)


def draft_renewal(a, level, start, end):
    fname, data = contracts.generate(a, level, start, end, renew=True)
    a.setdefault("contracts", []).append({"name": fname, "fid": vault.put_file(data), "expiry": end.isoformat(),
                                          "uploaded": dt.date.today().isoformat(), "kind": "续签待签",
                                          "tpl": TEMPLATE_REV})
    a["renewal"] = {"drafted": dt.date.today().isoformat(), "tpl": TEMPLATE_REV, "level": level, "start": start.isoformat(),
                    "end": end.isoformat(), "contract": len(a["contracts"]) - 1}
    return fname, data


def renewal_candidates():
    return sorted([a for a in vault.all("agent") if a.get("contract_expiry") and a.get("status") in ("活跃", "已签约")
                   and days_left(a["contract_expiry"]) <= RENEW_DAYS and not (a.get("renewal") or {}).get("signed")],
                  key=lambda a: a["contract_expiry"])


TEMPLATE_REV = 4  # 2：乙方信息按甲方的字体字号填写；3：签名行每页底部 + 页码，乙方地址电话等留空给代理填；4：AP 课程佣金单列一项


def refresh_old_drafts():
    """清理旧模板生成的合同（POLO 2026-10-27：不要留有错误的旧版）：
    - 续签草稿：只留当前这一份，按新模板重新生成；被替换掉的、续签已签回后剩下的草稿都删掉。
    - 新签合同草稿（待签（系统生成））：每个代理只留最新一份，按新模板重新生成。
    代理签回上传的合同（已签）和导入的旧合同一律不动。邮件还没真正发出过（演示模式），所以重做不影响代理。"""
    for a in vault.all("agent"):
        cs = a.get("contracts") or []
        r = a.get("renewal") or {}
        cur = r.get("contract") if r and not r.get("signed") else None
        latest_new = max((i for i, c in enumerate(cs) if c.get("kind") == "待签（系统生成）"), default=None)
        keep, drop = [], []
        for i, c in enumerate(cs):
            k = c.get("kind")
            if (k == "续签待签" and i != cur) or (k == "待签（系统生成）" and i != latest_new):
                drop.append(c)
            else:
                keep.append(c)
        changed = bool(drop)
        if cur is not None and cur < len(cs):
            r["contract"] = keep.index(cs[cur])
        a["contracts"] = keep
        for c in keep:
            if c.get("tpl") == TEMPLATE_REV or c.get("kind") not in ("续签待签", "待签（系统生成）"):
                continue
            if c.get("kind") == "续签待签":
                if not r or keep.index(c) != r.get("contract"):
                    continue
                level, start, end, renew = r["level"], dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"]), True
                r["tpl"] = TEMPLATE_REV
                r.pop("sent", None)
            else:
                if not c.get("expiry"):
                    continue
                end = dt.date.fromisoformat(c["expiry"])
                nxt = end + dt.timedelta(days=1)  # 旧草稿没存开始日：按默认 3 年合同期倒推
                start = dt.date.fromisoformat(c["start"]) if c.get("start") else nxt.replace(year=nxt.year - 3)
                level, renew = a.get("level") if a.get("level") in LEVELS else "standard", False
            fname, data = contracts.generate(a, level, start, end, renew=renew)
            drop.append(dict(c))
            c.update(fid=vault.put_file(data), name=fname, tpl=TEMPLATE_REV)
            c.pop("edited", None)
            changed = True
        if not changed:
            continue
        vault.put("agent", a)
        for c in drop:
            trash_contract(a, c, "旧模板草稿，已换成新模板")
        vault.audit(f"old-template contracts cleaned ({len(drop)})")


def auto_renewals():
    """到期前 90 天自动把续签合同准备好，等 POLO 检查后一键发出。"""
    refresh_old_drafts()
    for a in renewal_candidates():
        if days_left(a["contract_expiry"]) <= AUTO_DRAFT_DAYS and not a.get("renewal"):
            stats = agent_ay_stats(a["id"], last_ay())
            start, end = renewal_period(a)
            draft_renewal(a, suggest_level(a, stats), start, end)
            a["renewal"]["auto"] = True
            vault.put("agent", a)
            vault.audit("renewal auto-drafted")


@app.route("/renewals")
@login_required
def renewals():
    refresh_old_drafts()
    ay, cay = last_ay(), current_ay()
    comms, agents = vault.all("commission"), agents_by_id()
    rows = []
    for a in renewal_candidates():
        stats = agent_ay_stats(a["id"], ay, comms, agents)
        cur = agent_ay_stats(a["id"], cay, comms, agents)
        start, end = renewal_period(a)
        # 等级按上一个完整学年；本学年第一年学生已经满 6 人的也建议高级
        basis = cur if cur["ft1"] >= 6 else stats
        rows.append({"a": a, "stats": stats, "cur": cur, "level": suggest_level(a, basis), "start": start, "end": end,
                     "r": a.get("renewal") or {}})
    counts = {}
    for x in rows:
        lv = x["r"].get("level") or x["level"]
        counts[lv] = counts.get(lv, 0) + 1
    return render_template("renewals.html", rows=rows, ay=ay, cay=cay, counts=counts, auto_days=AUTO_DRAFT_DAYS, renew_days=RENEW_DAYS)


@app.post("/agents/<aid>/renew")
@login_required
def agent_renew(aid):
    a = vault.get("agent", aid) or abort(404)
    level = request.form.get("level") or a.get("level") or "standard"
    r = a.get("renewal") or {}
    if request.form.get("regenerate") or not r or r.get("level") != level:
        start = dt.date.fromisoformat(request.form.get("start") or renewal_period(a)[0].isoformat())
        end = dt.date.fromisoformat(request.form.get("end") or renewal_period(a)[1].isoformat())
        fname, data = draft_renewal(a, level, start, end)
    else:
        c = a["contracts"][r["contract"]]
        fname, data = c["name"], vault.get_file(c["fid"])
    vault.put("agent", a)
    if request.form.get("send"):  # 先到邮件页面预览、翻译、修改，再发
        return redirect(url_for("renew_mail", aid=aid))
    if request.form.get("edit"):
        return redirect(url_for("contract_edit", aid=aid, i=a["renewal"]["contract"], back=url_for("renewals")))
    flash("续签合同已生成，可在线预览检查")
    return redirect(safe_back(request.form.get("back")) or url_for("renewals"))


# 代理邮件可选的翻译语言：开发邮件的 14 种 + 老代理常见的几种
AGENT_LANGS = dict(i18n.LANG_LABELS)
AGENT_LANGS.update({"zh": "简体中文", "zh-TW": "繁體中文", "es": AGENT_LANGS.get("es", "Spanish"), "fr": "French",
                    "it": "Italian", "ru": "Russian", "ar": "Arabic", "id": "Indonesian", "mn": "Mongolian",
                    "kk": "Kazakh", "uk": "Ukrainian"})
EXTRA_COUNTRY_LANG = {"china": "zh", "中国": "zh", "taiwan": "zh-TW", "台湾": "zh-TW", "hong kong": "zh-TW", "香港": "zh-TW",
                      "macau": "zh-TW", "spain": "es", "argentina": "es", "ecuador": "es", "venezuela": "es",
                      "france": "fr", "italy": "it", "russia": "ru", "kazakhstan": "kk", "ukraine": "uk",
                      "mongolia": "mn", "indonesia": "id", "saudi arabia": "ar", "uae": "ar", "egypt": "ar",
                      "switzerland": "de", "korea": "ko", "韩国": "ko", "日本": "ja", "越南": "vi", "泰国": "th",
                      "墨西哥": "es", "巴西": "pt", "土耳其": "tr", "俄罗斯": "ru"}


def agent_lang(a):
    """代理用什么语言：先看上次选过的，再按国家猜；英语国家或猜不到就返回空。"""
    if a.get("mail_lang") in AGENT_LANGS:
        return a["mail_lang"]
    country = (a.get("country") or "").strip()
    return i18n.lang_for(country) or EXTRA_COUNTRY_LANG.get(country.lower(), "")


def safe_back(url):
    return url if url and url.startswith("/") and not url.startswith("//") else ""


@app.route("/agents/<aid>/renew/mail", methods=["GET", "POST"])
@login_required
def renew_mail(aid):
    a = vault.get("agent", aid) or abort(404)
    r = a.get("renewal") or {}
    if not r:
        flash("先生成续签合同")
        return redirect(url_for("renewals"))
    c = a["contracts"][r["contract"]]
    if request.method == "POST":
        to = (request.form.get("to") or "").strip()
        if not to:
            flash("请填收件人邮箱")
            return redirect(url_for("renew_mail", aid=aid))
        if request.form.get("lang") in AGENT_LANGS or request.form.get("lang") == "":
            a["mail_lang"] = request.form.get("lang")
        with mailer.Outbox(vault) as box:
            box.send(to, request.form["subject"], request.form["body"], [(c["name"], vault.get_file(c["fid"]))],
                     agent_id=aid, kind="renewal", sender=request.form.get("sender"))
        a["renewal"]["sent"] = dt.date.today().isoformat()
        vault.put("agent", a)
        flash(f"续签合同和续签信已发给 {a['name']}，签回后在代理页面上传即可")
        return redirect(url_for("renewals"))
    tpl = et.fill(et.RENEW_LETTER, contact=a.get("contact") or a["name"], start=r["start"], end=r["end"],
                  kit_link=kit_link())
    return render_template("renew_mail.html", a=a, r=r, c=c, tpl=tpl, langs=AGENT_LANGS, lang=agent_lang(a))


@app.post("/mail/translate")
@login_required
def mail_translate():
    cfg = settings()
    if not ai.available(cfg):
        return {"error": "请先在设置里设置 AI（本地模型）"}, 400
    lang = request.form.get("lang", "")
    if lang not in AGENT_LANGS:
        return {"error": "不支持的语言"}, 400
    try:
        return ai.translate(cfg, request.form["subject"], request.form["body"], AGENT_LANGS[lang])
    except Exception as e:
        return {"error": str(e)[:300]}, 500


# ---------- 代理业绩 ----------
@app.route("/performance")
@login_required
def performance():
    comms, agents = vault.all("commission"), agents_by_id()
    ays = sorted({academic_year(c["term"]) for c in comms} | {current_ay()}, reverse=True)
    ay = request.args.get("ay") or current_ay()
    prev = f"{int(ay[:2]) - 1:02d}-{ay[:2]}" if re.fullmatch(r"\d\d-\d\d", ay) else ""
    studs = vault.all("student")
    today = dt.date.today()
    rows = []
    season = lambda t: re.sub(r"^\s*20\d\d\s*|\s*\d\d-\d\d\s*$", "", t or "").strip().lower()
    have = {season(c["term"]) for c in comms if academic_year(c["term"]) == ay}
    partial = ay == current_ay() and bool(have)
    # 本学年还没过完：上一学年只拿同样几个学期来比（同期对比），不拿全年比
    prev_comms = [c for c in comms if not partial or season(c["term"]) in have]
    for a in agents.values():
        if a.get("status") in ("潜在", "洽谈中"):
            continue
        s = agent_ay_stats(a["id"], ay, comms, agents)
        p = agent_ay_stats(a["id"], prev, prev_comms, agents) if prev else {"commission": 0}
        apps = [x for x in studs if x.get("agent_id") == a["id"] and academic_year(x.get("intake") or "") == ay]
        enrolled = sum(1 for x in apps if x.get("stage") == "已入学")
        last = max((c.get("paid_on") or c.get("sent_on") or "" for c in comms if c["agent_id"] == a["id"]), default="")
        last_term = max((c for c in comms if c["agent_id"] == a["id"]), key=lambda c: c.get("term_order", -1), default=None)
        rows.append({"a": a, **s, "prev": p["commission"], "apps": len(apps), "enrolled": enrolled,
                     "last_term": last_term["term"] if last_term else "",
                     "idle": not last or (today - dt.date.fromisoformat(last[:10])).days > 365})
    rows.sort(key=lambda r: (-r["commission"], -r["students"]))
    active = [r for r in rows if r["students"] or r["commission"]]
    same_terms = sorted({c["term"] for c in comms if academic_year(c["term"]) == ay}, key=lambda t: term_pos(t))
    return render_template("performance.html", rows=rows, ay=ay, ays=ays, prev=prev, active=active, partial=partial, same_terms=same_terms,
                           idle=[r for r in rows if r["idle"] and r["a"].get("status") == "活跃"],
                           total=sum(r["commission"] for r in rows), fees=sum(r["fees"] for r in rows))


# ---------- 宣传资料库 ----------
ASSET_KINDS = ["资料包", "宣传册", "传单", "PPT", "申请表", "文字介绍", "校历", "视频", "照片", "Logo", "其它"]
PARTNER_KIT = ("https://johnathanacademy-my.sharepoint.com/:f:/g/personal/admissionsja_cseec_ca/"
               "EtK0pf0Saj9Dv_j83LS5ELIB7eB9mA0ur8CqfItIUf3c_A")
# 来自学校 OneDrive「宣传」文件夹和招生处共享的 Business partner 文件夹；链接请在 OneDrive 里「共享 → 复制链接」后贴进来
DEFAULT_ASSETS = [
    ("合作伙伴资料包（Business partner 共享文件夹）", "资料包", "中英", PARTNER_KIT,
     "招生处 OneDrive：Important documents for Business partner（申请表、单科申请表、中英文 Flyer、学校介绍 PPT）。Start Letter 和续签信里的资料链接就是它", True),
    ("JA Flyer（英文）", "传单", "英文", "", "宣传 / 宣传册 / JA Flyer E Share.pdf", True),
    ("JA Flyer（中文）", "传单", "中文", "", "宣传 / 宣传册 / JA Flyer 中 Share.pdf", True),
    ("学校画册 2023 英文版（印刷版）", "宣传册", "英文", "", "宣传 / 宣传册 / 画册英文版2023-印刷版.pdf", True),
    ("乔纳森学院画册 中文版", "宣传册", "中文", "", "宣传 / 宣传册 / 乔纳森学院(中文版) Last edit.pdf", True),
    ("学校介绍 PPT 英文 1.3", "PPT", "英文", "", "宣传 / PPT / JA 宣传 Eng1.3 Mar-14-24.pdf", True),
    ("学校介绍 PPT 中文 1.3", "PPT", "中文", "", "宣传 / PPT / JA 宣传 1.3 Mar-14-24.pdf", True),
    ("Admission Application Form", "申请表", "英文", "", "Business partner 文件夹", True),
    ("Single Course Application Form", "申请表", "英文", "", "Business partner 文件夹", True),
    ("学校介绍文字 JA PUBLICITY", "文字介绍", "英文", "", "Agent / Template Docs / JA PUBLICITY.docx（2023 版，数字需要更新）", False),
    ("招生时家长常问的问题汇总", "文字介绍", "中文", "", "宣传 / 在招生时遇到家长问到的问题汇总.docx", False),
    ("学校日历", "校历", "英文", "", "招生处 OneDrive 里是 2024-2025 版，需要换成 2026-27", True),
    ("校长视频 / 宣传视频", "视频", "", "", "宣传 / Principal video、宣传 / Video", False),
    ("校园照片", "照片", "", "", "宣传 / Photoes / Campus、25-26", False),
    ("Logo", "Logo", "", "", "宣传 / LOGO", False),
]


def all_assets():
    rows = vault.all("asset")
    if not rows and not (vault.get("settings", "flags") or {}).get("assets_seeded"):
        for title, kind, lang, url, note, share in DEFAULT_ASSETS:
            vault.put("asset", {"title": title, "kind": kind, "lang": lang, "url": url, "note": note, "share": share,
                                "updated": dt.date.today().isoformat()})
        vault.put("settings", {**(vault.get("settings", "flags") or {"id": "flags"}), "assets_seeded": True})
        rows = vault.all("asset")
    return sorted(rows, key=lambda x: (ASSET_KINDS.index(x["kind"]) if x.get("kind") in ASSET_KINDS else 99, x["title"]))


def kit_link():
    return settings().get("kit_link") or next((x["url"] for x in all_assets() if x.get("kind") == "资料包" and x.get("url")), "")


@app.route("/materials", methods=["GET", "POST"])
@app.route("/materials/<mid>", methods=["GET", "POST"])
@login_required
def materials(mid=None):
    m = vault.get("asset", mid) if mid else None
    if mid and not m:
        abort(404)
    if request.method == "POST":
        if request.form.get("delete") and m:
            to_trash("asset", m, m.get("title", ""))
            flash(f"已放进回收站，{TRASH_DAYS} 天内可以恢复")
            return redirect(url_for("materials"))
        m = m or {}
        for k in ("title", "kind", "lang", "url", "note"):
            m[k] = request.form.get(k, "").strip()
        m["share"] = bool(request.form.get("share"))
        m["updated"] = dt.date.today().isoformat()
        up = save_upload("file")
        if up:
            m["file"] = up
        vault.put("asset", m)
        flash("已保存")
        return redirect(url_for("materials"))
    rows = all_assets()
    return render_template("materials.html", rows=rows, m=m, kinds=ASSET_KINDS, kit=kit_link(),
                           missing=[x for x in rows if not x.get("url") and not x.get("file")])


# ---------- 年度付款汇总 / T4A ----------
@app.route("/payments")
@login_required
def payments():
    agents = agents_by_id()
    comms = vault.all("commission")
    rows = [enrich(c, agents, comms) for c in comms]
    years = tax.years(rows)
    year = int(request.args.get("year") or (years[1] if len(years) > 1 and dt.date.today().month <= 3 else years[0]))
    summary = tax.summarize(year, rows, agents)
    return render_template("payments.html", summary=summary, year=year, years=years, deadline=tax.deadline(year),
                           total=sum(s["total"] for s in summary), t4a=[s for s in summary if s["t4a"]],
                           ENTITY_TYPES=tax.ENTITY_TYPES, cfg=settings())


@app.route("/payments/<int:year>.xlsx")
@login_required
def payments_export(year):
    agents = agents_by_id()
    comms = vault.all("commission")
    summary = tax.summarize(year, [enrich(c, agents, comms) for c in comms], agents)
    cfg = settings()
    vault.audit("payments export")
    return send_file(io.BytesIO(tax.workbook(year, summary, {"name": cfg.get("payer_name") or "Johnathan Academy",
                                                             "bn": cfg.get("payer_bn") or ""})),
                     download_name=f"JA Agent Payments {year} + T4A.xlsx", as_attachment=True)


@app.post("/payments/<int:year>/send")
@login_required
def payments_send(year):
    """给代理发年度付款明细（选中的代理，或全部当年有付款的代理）。"""
    agents = agents_by_id()
    comms = vault.all("commission")
    summary = tax.summarize(year, [enrich(c, agents, comms) for c in comms], agents)
    pick = set(request.form.getlist("aid"))
    sent = 0
    with mailer.Outbox(vault) as box:
        for s in summary:
            a = s["agent"]
            if (pick and a["id"] not in pick) or not a.get("email"):
                continue
            line = (f"A T4A slip (Box 020, self-employed commissions) for {year} will be issued to you by "
                    f"{tax.deadline(year):%B %d, %Y}." if s["t4a"] else "")
            tpl = et.fill(et.ANNUAL_STATEMENT, contact=a.get("contact") or a["name"], agent=a["name"], year=year,
                          amount=money(s["total"]), t4a_line=line)
            box.send(a["email"], tpl["subject"], tpl["body"],
                     [(f"JA {year} Commission Payments {a.get('code', '')}.xlsx", tax.agent_statement(year, s))],
                     agent_id=a["id"], kind="statement")
            sent += 1
    flash(f"已给 {sent} 个代理发出 {year} 年度付款明细")
    return redirect(url_for("payments", year=year))


# ---------- 设置与安全 ----------
@app.post("/settings/ai-test")
@login_required
def settings_ai_test():
    cfg = dict(settings())
    for k in ("ai_mode", "local_llm_url", "local_model", "local_api_key", "searxng_url", "openai_key", "openai_model", "kit_link", "payer_name", "payer_bn"):  # 用页面上刚填的值测试，不必先保存
        if request.form.get(k):
            cfg[k] = request.form[k].strip()
    try:
        if ai.mode(cfg) == "claude":
            ai.claude_translate(cfg.get("anthropic_key", ""), "Hello", "Hello {name}", "Spanish")
            flash("Claude API 连接正常")
        else:
            models, hits = local_ai.check(cfg)
            flash(f"本地模型连接正常（{models}），搜索返回 {hits} 条结果")
    except Exception as e:
        flash(f"连接失败：{str(e)[:200]}")
    return redirect(url_for("settings_page"))



@app.route("/settings/import", methods=["POST"])
@login_required
def settings_import():
    """首次导入：佣金总表 Excel（代理 + 历史佣金）+ 已签合同文件（加密保存，按文件名里的代理编号和到期年月归档）。"""
    if vault.all("agent") and request.form.get("confirm") != "1":
        flash("系统里已经有代理了，再导入会重复。确实要导入请勾选「我确认要再次导入」")
        return redirect(url_for("settings_page"))
    wb = request.files.get("workbook")
    if not wb or not wb.filename.lower().endswith(".xlsx"):
        flash("请选择佣金总表 Excel（.xlsx）")
        return redirect(url_for("settings_page"))
    fids, skipped = {}, 0
    for f in request.files.getlist("contracts"):
        if f and f.filename:
            name = os.path.basename(f.filename)
            if importer.parse_contract_name(name)[0]:
                fids[name] = vault.put_file(f.read())
            else:
                skipped += 1
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        wb.save(tmp.name)
        try:
            n_agents, n_rows = importer.import_into(vault, tmp.name, contract_fids=fids)
            rec = vault.get("settings", "mail") or {"id": "mail"}
            with open(tmp.name, "rb") as fh:  # 原表留作佣金总表的底表，以后每个结算期在后面加一页
                rec["master_base"] = vault.put_file(fh.read())
            rec["master_base_name"] = os.path.basename(wb.filename)
            vault.put("settings", rec)
        except Exception as e:
            flash(f"导入失败：{e}")
            return redirect(url_for("settings_page"))
    tracker = request.files.get("tracker")
    n_prospects = import_tracker(tracker.read()) if tracker and tracker.filename else 0
    flash(f"已导入 {n_agents} 个代理、{n_rows} 条历史佣金；{len(fids)} 份合同已归档"
          + (f"；{n_prospects} 个潜在代理" if n_prospects else "")
          + (f"，{skipped} 个文件名里没有代理编号（如 J202103），没有导入，可以到代理页面单独上传" if skipped else ""))
    return redirect(url_for("agents_list"))


def _contract_files(z):
    """包里的合同：[(文件名, 代理编号或 None, 到期日, zip 内路径)]"""
    out = []
    for n in z.namelist():
        base = os.path.basename(n)
        if n.startswith("contracts/") and base:
            code, exp = importer.parse_contract_name(base)
            out.append((base, code, exp, n))
    return out


def _name_key(n):
    """同一个学生不同写法算一个：'Li, jiaheng' = 'Jiaheng Li'；括号里的英文名不算。"""
    n = re.sub(r"\(.*?\)", " ", n or "").replace(",", " ").lower()
    return " ".join(sorted(w for w in re.split(r"\s+", n) if w))


def _student_match(name, pool):
    k = _name_key(name)
    hit = next((s for s in pool if _name_key(s.get("name")) == k), None)
    if hit:
        return hit
    ws = set(k.split())  # 系统里少写了英文名（Mai Bo / Mai Bo Jason）也算同一个人
    return next((s for s in pool if len(ws & set(_name_key(s.get("name")).split())) >= 2
                 and (ws <= set(_name_key(s.get("name")).split()) or set(_name_key(s.get("name")).split()) <= ws)), None)


def _students_pack(z, choice=None, pays=None):
    """choice：预览页里每个学生选的代理 {行号: 代理id / "self" / ""（待分配）}，没选的用包里的建议。
    pays：每个学生本学期付不付佣金 {行号: "1" / "0"}，没选的用包里的建议（包里写了 nopay 的默认不付）。
    结算单按最后选定的代理重新分组：包里本学期要结算的学生，换了代理就跟着进新代理的草稿。"""
    pack = json.loads(z.read("students.json").decode("utf-8"))
    agents = agents_by_id()
    codes = {a.get("code"): a for a in agents.values() if a.get("code")}
    have = vault.all("student")
    comms = vault.all("commission")
    choice, pays = choice or {}, pays or {}
    plan = {}  # 学生名 -> 包里的结算单
    for st in pack.get("statements", []):
        for n in st.get("students", []):
            plan[n] = st
    term0 = pack.get("term") or next((st["term"] for st in pack.get("statements", []) if st.get("term")), "")
    rows = []
    for i, x in enumerate(pack.get("students", [])):
        a, self_ = codes.get(x.get("agent_code")), bool(x.get("self"))
        pick = choice.get(i)
        if pick is not None:
            a, self_ = (agents.get(pick), False) if pick not in ("", "self") else (None, pick == "self")
        old = _student_match(x["name"], have)
        pay0 = x["name"] in plan and not x.get("nopay")
        pay = pays[i] == "1" if pays.get(i) in ("0", "1") else pay0
        rows.append(dict(x, i=i, agent=a, self=self_, exists=old, changed=pick is not None and (
            (a or {}).get("code") != x.get("agent_code") or self_ != bool(x.get("self"))),
            agent_missing=not a and not self_, pay=pay, pay0=pay0, pay_changed=pay != pay0))
    groups = {}
    for x in rows:
        if not x["pay"] or x["self"]:
            continue
        st = plan.get(x["name"]) or {"term": term0, "agent_code": x.get("agent_code"), "agent_hint": x.get("agent_hint")}
        if not st.get("term"):
            continue
        key = x["agent"]["id"] if x["agent"] else ("?" + (st.get("agent_hint") or st.get("agent_code") or "") if not x["self"] else None)
        if key is None:
            continue
        g = groups.setdefault(key, {"term": st["term"], "students": [], "agent": x["agent"]})
        g["students"].append(x["name"])
        if not x["agent"]:
            g["agent_hint"] = x.get("agent_hint") or st.get("agent_hint")
    by_code = {st.get("agent_code"): st for st in pack.get("statements", []) if st.get("agent_code")}
    stmts = []
    for key, g in groups.items():
        a = g["agent"]
        meta = by_code.get(a.get("code")) if a else None
        meta = meta or {}
        cur = next((c for c in comms if a and c["agent_id"] == a["id"] and c["term"] == g["term"]), None)
        r = (pack.get("rosters") or {}).get(a.get("code")) if a else None
        rows_g = [x for x in rows if x["name"] in g["students"]]
        prev = {"students": [{"name": x["name"], "program": x.get("program") or "FT1", "tuition": x.get("tuition") or 0,
                              "rate": None} for x in rows_g]}
        lines, total = calculate(prev, agent_scheme(a)) if a else ([], 0)
        stmts.append(dict(meta, key=str(key), lines=lines, total=total,
                          term=g["term"], students=g["students"], agent=a, agent_code=a.get("code") if a else None,
                          agent_hint=g.get("agent_hint"), existing=cur, locked=bool(cur and cur.get("locked")),
                          roster=(r or {}).get("name") or ((a or {}).get("roster") or {}).get("name"), n=len(g["students"])))
    stmts.sort(key=lambda x: (x["agent"] is None, (x["agent"] or {}).get("code") or ""))
    return pack, rows, stmts


def _students_import(z, choice=None, pays=None, skip=None):
    """导入学生（按名字合并，不重复）、归到代理、建本学期结算单草稿和邮件草稿、存各代理的 Roster 底稿。都不会发信。
    本学期不付佣金的学生只导入学生资料，不进结算单（已有的未发出草稿里有他，会拿掉）。"""
    pack, rows, stmts = _students_pack(z, choice, pays)
    today = dt.date.today().isoformat()
    by_name = {}
    n_new = n_upd = 0
    for x in rows:
        st = x["exists"] or {"history": {}, "docs": []}
        if not x["exists"]:
            n_new += 1
        else:
            n_upd += 1
        for k in ("name", "grade", "program", "origin", "intake", "courses", "period", "folder"):
            if x.get(k) not in (None, ""):
                st[k] = x[k] if k != "name" or not x["exists"] else st.get("name") or x[k]
        if x.get("tuition") is not None:
            st["tuition"] = x["tuition"]
        if x.get("note"):
            st["notes"] = x["note"]
        st["roster_note"] = x.get("roster_note") or ""
        st["commission_note"] = "" if x["pay"] else (x.get("pay_note") or "本学期不付佣金")
        if x.get("changed"):
            st["agent_manual"] = True  # 在导入预览里改过的，算你手动分配
        if x.get("changed") or not st.get("agent_manual"):  # 你以前手动分配过的不改
            if x["agent"]:
                st.update(agent_id=x["agent"]["id"], uses_agent=True)
            elif x.get("self"):
                st.update(agent_id="", uses_agent=False)
            else:
                st.update(agent_id="", uses_agent=True, agent_hint=x.get("agent_hint") or x.get("agent_code") or "")
        if x.get("stage") in STUDENT_STAGES and st.get("stage") != x["stage"]:
            st["stage"] = x["stage"]
            st.setdefault("history", {})[x["stage"]] = today
        st["imported_from"] = pack.get("source", "")
        st = vault.put("student", st)
        by_name[x["name"]] = st
    unpaid = {_name_key(x["name"]) for x in rows if not x["pay"]}
    if unpaid:  # 以前导入时进了草稿、现在定为不付的，从没发出的草稿里拿掉
        for c in vault.all("commission"):
            if c.get("locked") or c.get("status") != "草稿":
                continue
            keep = [s2 for s2 in c.get("students", []) if _name_key(s2.get("name")) not in unpaid]
            if len(keep) != len(c.get("students", [])):
                c["students"] = keep
                vault.put("commission", c)
    rosters = pack.get("rosters") or {}
    n_stmt, skipped = 0, []
    orders = {t: i for i, t in enumerate(terms())}
    for x in stmts:
        a = x["agent"]
        if x["key"] in (skip or ()):
            skipped.append(f"{(a or {}).get('name') or x.get('agent_hint') or x.get('agent_code')}（你选了不建）")
            continue
        if not a:
            skipped.append(f"{x.get('agent_hint') or x.get('agent_code')}（系统里没有这个代理）")
            continue
        r = rosters.get(x["agent_code"])
        if r and r.get("file") in z.namelist():
            a = vault.get("agent", a["id"])
            a["roster"] = {"name": r.get("name") or os.path.basename(r["file"]), "fid": vault.put_file(z.read(r["file"])),
                           "updated": today, "agent_label": x.get("agent_label", "")}
            vault.put("agent", a)
        elif x.get("agent_label"):
            a = vault.get("agent", a["id"])
            a["roster"] = dict(a.get("roster") or {}, agent_label=x["agent_label"])
            vault.put("agent", a)
        if x["locked"]:
            skipped.append(f"{a['name']}（{x['term']} 结算单已经发出，没有改）")
            continue
        c = x["existing"] or {"agent_id": a["id"], "term": x["term"], "status": "草稿", "students": [],
                              "term_order": orders.get(x["term"], len(orders) + 100)}
        if x["term"] not in orders:
            vault.put("term", {"name": x["term"], "order": max([0] + [t.get("order", 0) for t in vault.all("term")]
                                                                + [k.get("term_order", 0) for k in vault.all("commission")]) + 1,
                               "created": today})
            orders = {t: i for i, t in enumerate(terms())}
        keep = [s2 for s2 in c.get("students", []) if all(_name_key(s2.get("name")) != _name_key(n) for n in x["students"])]
        add = []
        for n in x["students"]:
            st = by_name.get(n) or {}
            add.append({"name": st.get("name") or n, "program": st.get("program") or "FT1", "courses": st.get("courses") or "",
                        "origin": st.get("origin") or "International", "tuition": st.get("tuition") or 0,
                        "note": "", "period": st.get("roster_note") or st.get("period") or "", "rate": None,
                        "grade": st.get("grade") or "", "student_id": st.get("id")})
        c["students"] = keep + add
        c["imported"] = False
        c["draft_mail"] = {k: v for k, v in {"greet": x.get("greet"), "to": x.get("to")}.items() if v}
        c = vault.put("commission", c)
        for n in x["students"]:
            if by_name.get(n):
                by_name[n]["commission_id"] = c["id"]
                vault.put("student", by_name[n])
        n_stmt += 1
    return n_new, n_upd, n_stmt, skipped


def _inbox_choices(form):
    """预览页表单里的选择：每个学生的代理、付不付，以及不要建的草稿。"""
    choice = {int(k[6:]): v for k, v in form.items() if k.startswith("agent_") and k[6:].isdigit()}
    pays = {int(k[4:]): v for k, v in form.items() if k.startswith("pay_") and k[4:].isdigit()}
    skip = set(form.getlist("skip"))
    return choice, pays, skip


@app.route("/inbox")
@login_required
def inbox_page():
    """加密收件箱：先预览包里的内容（特别是收款信息），确认后才导入。"""
    return _inbox_render(request.args.get("b"))


@app.post("/inbox/<name>/refresh")
@login_required
def inbox_refresh(name):
    """按预览页里当前的选择重新算结算单草稿（不导入）。"""
    return _inbox_render(name, *_inbox_choices(request.form), refreshed=True)


def _inbox_render(sel, choice=None, pays=None, skip=None, refreshed=False):
    bs = inbox.bundles(vault)
    sel = sel or next((b["name"] for b in bs if b["complete"]), None)
    pv, err = None, None
    if sel and any(b["name"] == sel and b["complete"] for b in bs):
        try:
            with inbox.open_bundle(vault, sel) as z:
                names = z.namelist()
                agents, records = [], []
                if "workbook.xlsx" in names:
                    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
                        tmp.write(z.read("workbook.xlsx"))
                        tmp.flush()
                        ag, records = importer.read_workbook(tmp.name)
                    have = {a.get("code"): a for a in vault.all("agent") if a.get("code")}
                    for a in ag.values():
                        old = have.get(a.get("code"))
                        a["exists"] = bool(old)
                        a["pay_changed"] = bool(old) and any(
                            (old.get(k) or "") != (a.get(k) or "") for k in ("etransfer", "payee", "detail"))
                        agents.append(a)
                    agents.sort(key=lambda a: a.get("code") or "~" + a["name"])
                tracker_n = 0
                if "tracker.xlsx" in names:
                    wb = openpyxl.load_workbook(io.BytesIO(z.read("tracker.xlsx")), read_only=True)
                    tracker_n = sum(max(ws.max_row - 1, 0) for ws in wb.worksheets)
                cf = _contract_files(z)
                if "students.json" in names:
                    spack, srows, sstmts = _students_pack(z, choice, pays)
                    spv = {"pack": spack, "rows": srows, "stmts": sstmts, "skip": skip or set(), "refreshed": refreshed,
                           "agent_list": sorted(vault.all("agent"), key=lambda a: a.get("name", "").lower())}
                else:
                    spv = None
                pv = {"agents": agents, "rows": len(records), "contracts": cf, "students": spv,
                      "matched": sum(1 for c in cf if c[1]), "tracker_n": tracker_n,
                      "terms": sorted({r["term"] for r in records}, key=lambda t: next(
                          (r["term_order"] for r in records if r["term"] == t), 0))}
        except Exception as e:
            err = str(e)
    return render_template("inbox.html", bundles=bs, sel=sel, pv=pv, err=err)


@app.post("/inbox/<name>/import")
@login_required
def inbox_import(name):
    with inbox.open_bundle(vault, name) as z:
        has_workbook = "workbook.xlsx" in z.namelist()
    if has_workbook and vault.all("agent") and request.form.get("confirm") != "1":
        flash("系统里已经有代理了，再导入会重复。确实要导入请勾选「我确认要再次导入」")
        return redirect(url_for("inbox_page", b=name))
    try:
        with inbox.open_bundle(vault, name) as z:
            fids = {base: vault.put_file(z.read(path)) for base, code, _, path in _contract_files(z) if code}
            msg = []
            if "workbook.xlsx" in z.namelist():
                with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
                    tmp.write(z.read("workbook.xlsx"))
                    tmp.flush()
                    n_agents, n_rows = importer.import_into(vault, tmp.name, contract_fids=fids)
                msg.append(f"{n_agents} 个代理、{n_rows} 条历史佣金、{len(fids)} 份已签合同")
            if "tracker.xlsx" in z.namelist():
                msg.append(f"{import_tracker(z.read('tracker.xlsx'))} 个潜在代理")
            if "students.json" in z.namelist():
                choice, pays, skip = _inbox_choices(request.form)
                n_new, n_upd, n_stmt, skipped = _students_import(z, choice, pays, skip)
                msg.append(f"学生新增 {n_new} 名、更新 {n_upd} 名，{n_stmt} 张结算单草稿（含邮件和附件草稿，都没有发出）"
                           + ("；没建结算单：" + "、".join(skipped) if skipped else ""))
    except Exception as e:
        flash(f"导入失败：{e}")
        return redirect(url_for("inbox_page", b=name))
    inbox.remove(vault, name)
    vault.audit("inbox bundle imported")
    flash("已导入：" + "，".join(msg) + "。收件箱里的加密包已删除。请检查，不对的可以直接改。")
    return redirect(url_for("agents_list") if has_workbook else url_for("students"))


@app.post("/inbox/<name>/delete")
@login_required
def inbox_delete(name):
    try:
        inbox.remove(vault, name)
    except (ValueError, OSError):
        abort(404)
    vault.audit("inbox bundle discarded")
    flash("已删除这个包，没有导入任何内容")
    return redirect(url_for("inbox_page"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    cfg = settings()
    if request.method == "POST":
        f = request.form
        if f.get("new_password"):
            if len(f["new_password"]) < 12 or not vault.try_unwrap(f.get("old_password", "")):
                flash("原密码错误或新密码少于 12 位")
            else:
                vault.change_password(f["new_password"])
                _trusted_save({})  # 换密码时，所有记住的设备都要重新输验证码
                flash("主密码已更换；所有记住的设备下次登录要重新输验证码")
        else:
            if f.get("notify_form"):
                cfg["digest_on"] = "1" if f.get("digest_on") else "0"
                cfg["lock_notify"] = "1" if f.get("lock_notify") else "0"
            if f.get("m365_form"):
                if (f.get("m365_client_id", "").strip() != cfg.get("m365_client_id", "")
                        or f.get("m365_tenant", "").strip() != cfg.get("m365_tenant", "")):
                    cfg.pop("m365_accounts", None)  # 换了应用或租户，所有邮箱都要重新授权
                    cfg.pop("mail_route", None)
            if f.get("route_form"):
                users = {x["user"] for x in mailer.accounts(cfg)}
                cfg["mail_route"] = {k: f.get("route_" + k) for k, _ in mailer.MAIL_KINDS if f.get("route_" + k) in users}
            for k in ("app_senders", "m365_tenant", "m365_client_id", "digest_to",
                      "smtp_host", "smtp_port", "smtp_user", "from_addr", "imap_host", "imap_user", "accountant_email",
                      "ai_mode", "local_llm_url", "local_model", "searxng_url", "openai_model",
                      "kit_link", "payer_name", "payer_bn"):  # 资料包链接、T4A 表头以前没存进去（2026-11-06 修好）
                if k in f:
                    cfg[k] = f.get(k, "").strip()
            for k in ("smtp_password", "imap_password", "anthropic_key", "local_api_key", "openai_key"):
                if f.get(k):
                    cfg[k] = f[k].strip()
            vault.put("settings", cfg)
            save_lock_notify()
            flash("设置已加密保存")
        return redirect(url_for("settings_page"))
    log = [(dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M"), e) for t, e in vault.audit_log()]
    return render_template("settings.html", cfg=cfg, version=version.VERSION, changes=version.CHANGES, app_on=mailer.app_on(), log=log, trusted_n=len(_trusted_load()), this_trusted=device_trusted(), portal_on=portal.enabled(), bk=backup.status(DATA_DIR), bk_dir=backup.backup_dir(),
                           bk_files=backup.listing()[:5])


@app.post("/settings/m365/start")
@login_required
def m365_start():
    cfg = settings()
    if not cfg.get("m365_client_id"):
        return {"error": "请先填应用程序 ID 并保存"}
    try:
        r = mailer.m365_start(cfg)
    except Exception as e:  # noqa: BLE001
        return {"error": f"连不上微软登录服务：{type(e).__name__}"}
    return {k: r.get(k) for k in ("user_code", "verification_uri", "device_code", "interval")}


@app.post("/settings/m365/poll")
@login_required
def m365_poll_route():
    try:
        state = mailer.m365_poll(vault, request.form.get("device_code", ""))
    except Exception as e:  # noqa: BLE001
        state = f"{type(e).__name__}"
    if state == "ok":
        vault.audit("Microsoft 365 mail connected")
    return {"state": state}


@app.post("/settings/m365/disconnect")
@login_required
def m365_disconnect():
    user = request.form.get("user", "")
    mailer.m365_remove(vault, user)
    vault.audit("Microsoft 365 mailbox disconnected")
    left = mailer.accounts(settings())
    flash(f"已断开 {user}" + ("" if left else "，回到演示模式") + ("；原来分给它的邮件改用默认邮箱发" if left else ""))
    return redirect(url_for("settings_page"))


@app.post("/settings/m365/test")
@login_required
def m365_test():
    user = request.form.get("user") or settings().get("m365_user")
    try:
        with mailer.Outbox(vault) as box:
            box.send(user, "代理管理系统 · 测试邮件", f"这是一封测试邮件，说明系统已经可以用 {user} 发信了。", sender=user)
        flash(f"测试邮件已从 {user} 发给它自己，请查收")
    except Exception as e:  # noqa: BLE001
        flash(f"发送失败：{e}")
    return redirect(url_for("settings_page"))


@app.post("/settings/trusted/clear")
@login_required
def trusted_clear():
    _trusted_save({})
    vault.audit("trusted devices cleared")
    flash("已取消所有记住的设备，下次登录都要输验证码")
    resp = redirect(url_for("settings_page"))
    resp.delete_cookie(TRUST_COOKIE)
    return resp


@app.post("/settings/backup/verify")
@login_required
def settings_backup_verify():
    try:
        r = backup.verify(vault)
        msg = f"恢复演练：{r['file']} 里 {r['records']} 条记录、{r['files']} 个文件都能用现在的密钥解开"
        flash(msg + ("。" if not r["bad"] else f"，但有 {r['bad']} 项解不开，请告诉 Claude"))
        vault.audit(f"backup verify: {r['records']} records, {r['files']} files, {r['bad']} bad")
        _save_verify(not r["bad"], f"{r['records']} 条记录、{r['files']} 个文件" + (f"，{r['bad']} 项解不开" if r["bad"] else ""))
    except Exception as e:  # noqa: BLE001
        flash(f"恢复演练失败：{e}")
        _save_verify(False, str(e)[:200])
    return redirect(url_for("settings_page"))


def _save_verify(ok, msg):
    rec = vault.get("settings", "mail") or {"id": "mail"}
    rec["last_verify"] = {"at": dt.datetime.now().isoformat(timespec="minutes").replace("T", " "), "ok": ok, "msg": msg}
    vault.put("settings", rec)


def backup_health():
    """备份是否正常：设了备份目录但超过 2 天没成功、或上次出错、或恢复演练失败，返回一句提示；正常返回空。"""
    if not backup.backup_dir():
        return ""
    st = backup.status(DATA_DIR)
    last = (st.get("last_ok") or "")[:10]
    if st.get("last_error"):
        return f"NAS 备份上次出错：{st['last_error']}"
    if not last or (dt.date.today() - dt.date.fromisoformat(last)).days > 2:
        return f"NAS 备份已经 {'很久' if not last else (dt.date.today() - dt.date.fromisoformat(last)).days} 天没有成功了"
    v = settings().get("last_verify") or {}
    if v and not v.get("ok"):
        return f"上次恢复演练失败：{v.get('msg', '')}"
    return ""


@app.post("/settings/backup")
@login_required
def settings_backup():
    try:
        path = backup.run(DATA_DIR)
        flash(f"备份完成：{os.path.basename(path)}（全部是密文）")
    except Exception as e:
        flash(f"备份失败：{e}")
    return redirect(url_for("settings_page"))


def weekly_digest(force=False):
    """每周一早上给 POLO 发一封汇总：快到期的合同、没走完的结算单、要跟进的潜在代理、新收到的代理邮件。"""
    cfg = settings()
    today = dt.date.today()
    if not force and (today.weekday() != 0 or dt.datetime.now().hour < 8 or cfg.get("digest_on", "1") == "0"
                      or cfg.get("digest_last") == today.isoformat()):
        return False
    to = cfg.get("digest_to") or cfg.get("m365_user") or cfg.get("smtp_user")
    if not mailer.mail_on(cfg) or not to:
        return False
    agents = agents_by_id()
    comms = vault.all("commission")
    rows = [enrich(c, agents, comms) for c in comms if not c.get("imported")]
    lines = [f"代理管理系统 · 每周汇总（{today.isoformat()}）", ""]
    exp = sorted([a for a in agents.values() if a.get("contract_expiry") and a.get("status") in ("活跃", "已签约")
                  and days_left(a["contract_expiry"]) <= 90], key=lambda a: a["contract_expiry"])
    lines.append(f"一、90 天内到期的合同：{len(exp)} 个")
    for a in exp[:15]:
        r = a.get("renewal") or {}
        st = "已签回" if r.get("signed") else "续签已发出" if r.get("sent") else "续签草稿待检查" if r else "还没准备续签"
        lines.append(f"   • {a.get('name')} {a.get('code') or ''} — {a['contract_expiry']}（{st}）")
    lines += ["", "二、还没走完的结算单"]
    for stage, label in (("已发结算单", "已发出、等代理确认"), ("代理已确认", "代理已确认、还没交给会计"),
                         ("已交会计", "已交会计、还没付款")):
        xs = [r for r in rows if r["stage"] == stage]
        if xs:
            lines.append(f"  {label}：{len(xs)} 张，共 ${sum(r['amount'] for r in xs):,.2f}")
            for r in xs[:10]:
                lines.append(f"   • {r.get('agent_name') or agents.get(r['agent_id'], {}).get('name', '')} · {r['term']} · ${r['amount']:,.2f}")
    fu = [p for p in vault.all("prospect") if needs_followup(p)]
    lines += ["", f"三、需要跟进的潜在代理：{len(fu)} 个"]
    week_ago = (dt.datetime.now() - dt.timedelta(days=7)).isoformat()
    inbox_n = sum(1 for m in vault.all("mail") if m["direction"] == "in" and m.get("at", "") >= week_ago)
    lines += [f"四、过去 7 天收到的代理邮件：{inbox_n} 封"]
    bst = backup.status(DATA_DIR)
    v = cfg.get("last_verify") or {}
    lines += ["", "五、备份", f"   • 最近一次备份成功：{(bst.get('last_ok') or '还没有').replace('T', ' ')}"
              + (f"；出错：{bst['last_error']}" if bst.get("last_error") else ""),
              f"   • 上次恢复演练：{v.get('at', '还没做过')}" + ("" if not v else ("（通过）" if v.get("ok") else f"（失败：{v.get('msg')}）"))]
    due = due_followups()
    if due:
        lines += ["", f"六、到期的跟进记录：{len(due)} 条"] + [f"   • {e['next']} {r.get('name') or r.get('agency')}：{e['text'][:60]}" for _, r, _, e in due[:10]]
    lines += ["", "详情请在学校网络里打开 https://192.168.1.75:8443 查看。"]
    with mailer.Outbox(vault) as box:
        box.send(to, f"代理管理 · 每周汇总 {today.isoformat()}", "\n".join(lines), kind="digest")
    rec = vault.get("settings", "mail") or {"id": "mail"}
    rec["digest_last"] = today.isoformat()
    vault.put("settings", rec)
    vault.audit("weekly digest sent")
    return True


# ---------- 系统锁定提醒：服务器重启后系统是锁着的，定时邮件、每周提醒、官网同步都停了，发邮件提醒 POLO 登录 ----------
LOCK_NOTIFY_HOURS = 2
_lock = {"since": time.time()}  # 启动时就是锁定的


def _notify_path():
    return os.path.join(DATA_DIR, "lock-notify.json")


def save_lock_notify():
    """登录（解锁）时记下：锁定后提醒发给谁、用哪个应用发件地址。只存两个邮箱地址，不含任何代理数据，所以不加密。"""
    cfg = settings()
    to = cfg.get("digest_to") or cfg.get("m365_user") or ""
    acct = mailer.account_for(cfg, "digest") or {}
    sender = acct["user"] if acct.get("app") else next((x["user"] for x in mailer.accounts(cfg) if x.get("app")), "")
    old = _read_lock_notify()
    rec = {"to": to, "sender": sender, "last": old.get("last", 0), "off": cfg.get("lock_notify") == "0"}
    try:
        with open(_notify_path(), "w") as fh:
            json.dump(rec, fh)
    except OSError:
        pass


def _read_lock_notify():
    try:
        with open(_notify_path()) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def check_lock_notify(now=None):
    """系统锁定超过 2 小时就发一封提醒（一天最多一封）。返回是否发了。"""
    now = now or time.time()
    if vault.unlocked or not vault.initialized or _lock["since"] is None or now - _lock["since"] < LOCK_NOTIFY_HOURS * 3600:
        return False
    rec = _read_lock_notify()
    if rec.get("off") or not rec.get("to") or now - rec.get("last", 0) < 20 * 3600:
        return False
    hours = int((now - _lock["since"]) // 3600)
    ok = mailer.app_send_plain(rec.get("sender"), rec["to"], "代理管理系统已锁定，请登录解锁",
                               f"代理管理系统已经锁定约 {hours} 小时（通常是服务器重启了）。\n\n"
                               "锁定期间定时邮件、每周一提醒和官网申请同步都暂停。请在学校网络里打开 "
                               "https://192.168.1.75:8443 用主密码登录一次，就会恢复。\n\n"
                               "（这封提醒不含任何代理数据，由系统自动发出。）")
    if ok:
        rec["last"] = now
        with open(_notify_path(), "w") as fh:
            json.dump(rec, fh)
    return ok


def start_jobs():
    mailer.start_scheduler(vault)
    backup.start(DATA_DIR)

    def lock_watch():
        while True:
            try:
                check_lock_notify()
            except Exception as e:  # noqa: BLE001  网络问题不影响系统
                app.logger.warning("lock notify failed: %s", e)
            time.sleep(600)
    threading.Thread(target=lock_watch, daemon=True).start()

    def daily():
        while True:
            try:
                if vault.unlocked:
                    auto_renewals()
                    purge_trash()
                    weekly_digest()
                    sync_admissions()
            except Exception as e:
                vault.audit(f"renewal job error: {type(e).__name__}")
            time.sleep(3600)
    threading.Thread(target=daily, daemon=True).start()


# ---------- 代理自助查询页（默认关闭）----------
portal_view = portal.register(app, vault, {"agents_by_id": agents_by_id, "enrich": enrich, "all_assets": all_assets,
                                           "statement_file": _statement_file, "save_upload": save_upload,
                                           "mailer": mailer, "et": et})


@app.route("/agents/<aid>/portal-preview")
@login_required
def portal_preview(aid):
    """POLO 预览某个代理在自助页上看到的内容（自助页未开放时也能看）。"""
    return portal_view(vault.get("agent", aid) or abort(404), preview=True)


if __name__ == "__main__":
    start_jobs()
    # 只监听本机；对外请用 Nginx/Caddy + HTTPS 反向代理
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8800)))
