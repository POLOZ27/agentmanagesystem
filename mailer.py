"""发信、收信和定时 News 推送。

两种方式：Microsoft 365 登录授权（Graph，推荐；微软已停用 SMTP/IMAP 的密码登录）或 SMTP/IMAP。
授权令牌和邮箱密码都存放在加密保险库的 settings 记录里。
两种都没配置时为"演示模式"：邮件只写入发件箱，不会真正发出。
"""
import base64
import calendar
import datetime as dt
import email
import email.policy
import imaplib
import mimetypes
import os
import smtplib
import ssl
import threading
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from vault import Locked

# ---------- Microsoft 365（Graph）----------
GRAPH = "https://graph.microsoft.com/v1.0"
M365_SCOPE = "offline_access User.Read Mail.Send Mail.Read"  # 只读邮件 + 发信，不能改动或删除邮箱里的邮件
_token = {}  # 内存里的访问令牌，不落盘


def _login_url(cfg, path):
    return f"https://login.microsoftonline.com/{cfg.get('m365_tenant') or 'organizations'}/oauth2/v2.0/{path}"


def m365_start(cfg):
    """设备码登录第一步：返回 {user_code, verification_uri, device_code, interval, message}。"""
    r = httpx.post(_login_url(cfg, "devicecode"), data={"client_id": cfg["m365_client_id"], "scope": M365_SCOPE}, timeout=20)
    r.raise_for_status()
    return r.json()


def m365_poll(vault, device_code):
    """设备码登录第二步：用户在微软页面确认后，拿到刷新令牌加密保存。返回 'ok' / 'pending' / 错误说明。"""
    cfg = settings(vault)
    r = httpx.post(_login_url(cfg, "token"), timeout=20, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": cfg["m365_client_id"],
        "device_code": device_code})
    j = r.json()
    if j.get("error") in ("authorization_pending", "slow_down"):
        return "pending"
    if "access_token" not in j:
        return j.get("error_description", j.get("error", "登录失败")).split("\r\n")[0]
    _token.update(access=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 120)
    me = httpx.get(GRAPH + "/me", headers={"Authorization": "Bearer " + j["access_token"]}, timeout=20).json()
    cfg = vault.get("settings", "mail") or {"id": "mail"}
    cfg.update(m365_refresh=j["refresh_token"], m365_user=me.get("mail") or me.get("userPrincipalName", ""),
               m365_since=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    vault.put("settings", cfg)
    return "ok"


def _graph_token(vault, cfg):
    if _token.get("access") and _token.get("exp", 0) > time.time():
        return _token["access"]
    r = httpx.post(_login_url(cfg, "token"), timeout=20, data={
        "grant_type": "refresh_token", "client_id": cfg["m365_client_id"], "refresh_token": cfg["m365_refresh"],
        "scope": M365_SCOPE})
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError("Microsoft 365 授权已失效，请在设置里重新连接")
    _token.update(access=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 120)
    if j.get("refresh_token") and j["refresh_token"] != cfg["m365_refresh"]:  # 刷新令牌会轮换，保存新的
        rec = vault.get("settings", "mail") or {"id": "mail"}
        rec["m365_refresh"] = j["refresh_token"]
        vault.put("settings", rec)
    return _token["access"]


def _graph(vault, cfg, method, path, **kw):
    h = {"Authorization": "Bearer " + _graph_token(vault, cfg), **kw.pop("headers", {})}
    r = httpx.request(method, GRAPH + path, headers=h, timeout=60, **kw)
    r.raise_for_status()
    return r.json() if r.content else {}


def m365_on(cfg):
    return bool(cfg.get("m365_refresh") and cfg.get("m365_client_id"))


def mail_on(cfg):
    return m365_on(cfg) or bool(cfg.get("smtp_host"))


def settings(vault):
    s = vault.get("settings", "mail") or {"id": "mail"}
    # 服务器部署时由 install.sh 自动找到的本地模型 / 搜索地址，设置页没填时用它们
    for key, env in (("local_llm_url", "AI_LOCAL_LLM_URL"), ("local_api_key", "AI_LOCAL_LLM_KEY"),
                     ("local_model", "AI_LOCAL_MODEL"), ("searxng_url", "AI_SEARXNG_URL")):
        if not s.get(key) and os.environ.get(env):
            s[key] = os.environ[env]
    return s


def render(text, agent):
    return (text.replace("{代理名称}", agent.get("name", ""))
                .replace("{代理编号}", agent.get("code") or "")
                .replace("{联系人}", agent.get("contact") or agent.get("name", "")))


class Outbox:
    """一次连接 SMTP 发多封；没配置 SMTP 时为演示模式，只记录不发出。"""

    def __init__(self, vault):
        self.vault = vault
        self.cfg = settings(vault)
        self.conn = None

    def __enter__(self):
        if m365_on(self.cfg):
            return self
        if self.cfg.get("smtp_host"):
            self.conn = smtplib.SMTP(self.cfg["smtp_host"], int(self.cfg.get("smtp_port") or 587), timeout=30)
            self.conn.starttls(context=ssl.create_default_context())
            self.conn.login(self.cfg["smtp_user"], self.cfg["smtp_password"])
        return self

    def __exit__(self, *exc):
        if self.conn:
            self.conn.quit()

    def send(self, to, subject, body, attachments=(), agent_id=None, cc=None, **meta):
        """attachments: [(文件名, 字节)]。发出的附件也加密存一份，方便以后查。"""
        status = "演示模式（未真正发出）"
        if m365_on(self.cfg):
            rcpt = lambda xs: [{"emailAddress": {"address": x.strip()}} for x in (xs or "").replace(";", ",").split(",") if x.strip()]
            msg = {"subject": subject, "body": {"contentType": "Text", "content": body}, "toRecipients": rcpt(to),
                   "attachments": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": n,
                                    "contentBytes": base64.b64encode(d).decode()} for n, d in attachments]}
            if cc:
                msg["ccRecipients"] = rcpt(cc)
            _graph(self.vault, self.cfg, "POST", "/me/sendMail", json={"message": msg, "saveToSentItems": True})
            status = "已发送"
        elif self.conn:
            msg = EmailMessage()
            msg["From"] = self.cfg.get("from_addr") or self.cfg["smtp_user"]
            msg["To"] = to
            if cc:
                msg["Cc"] = cc
            msg["Subject"] = subject
            msg.set_content(body)
            for name, data in attachments:
                maintype, subtype = (mimetypes.guess_type(name)[0] or "application/octet-stream").split("/")
                msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
            self.conn.send_message(msg)
            status = "已发送"
        files = [{"name": n, "fid": self.vault.put_file(d)} for n, d in attachments]
        return self.vault.put("mail", {
            "direction": "out", "agent_id": agent_id, "to": to, "cc": cc, "subject": subject, "body": body,
            "attachments": files, "at": dt.datetime.now().isoformat(timespec="seconds"), "status": status, **meta})


def send_to_agents(vault, agents, subject, body, campaign_id=None):
    sent = []
    with Outbox(vault) as box:
        for a in agents:
            if a.get("email") and not a.get("unsubscribed"):
                sent.append(box.send(a["email"], render(subject, a), render(body, a), agent_id=a["id"],
                                     campaign_id=campaign_id))
    return sent


def _save_incoming(vault, sender, subject, body, files, by_email, prospects):
    agent = by_email.get(sender)
    vault.put("mail", {"direction": "in", "agent_id": agent["id"] if agent else None, "from": sender,
                       "attachments": files, "subject": subject, "body": body,
                       "at": dt.datetime.now().isoformat(timespec="minutes"), "status": "未读",
                       "prospect_id": prospects[sender]["id"] if sender in prospects else None})
    if sender in prospects:  # 潜在代理回信：自动推进到「已回复」
        pr = prospects[sender]
        if "unsubscribe" in body.lower()[:200]:
            pr["unsubscribed"] = True
        elif pr.get("stage") in (None, "未联系", "已发邮件", "已跟进"):
            pr["stage"] = "已回复"
        vault.put("prospect", pr)


def _fetch_m365(vault, cfg, by_email, prospects):
    """只收代理和潜在代理发来的新邮件，不改 POLO 邮箱里的已读状态；收过的记下来，不会重复收。"""
    seen_rec = vault.get("settings", "mail_seen") or {"id": "mail_seen", "ids": []}
    seen = set(seen_rec["ids"])
    since = cfg.get("m365_since") or dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    j = _graph(vault, cfg, "GET", "/me/mailFolders/inbox/messages", headers={"Prefer": 'outlook.body-content-type="text"'},
               params={"$filter": f"receivedDateTime ge {since}", "$top": "50", "$orderby": "receivedDateTime desc",
                       "$select": "id,subject,from,body,hasAttachments,receivedDateTime"})
    n = 0
    for m in j.get("value", []):
        sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "").lower()
        if m["id"] in seen or (sender not in by_email and sender not in prospects):
            continue
        files = []
        if m.get("hasAttachments"):
            for a in _graph(vault, cfg, "GET", f"/me/messages/{m['id']}/attachments").get("value", []):
                if a.get("contentBytes") and a.get("name"):
                    files.append({"name": a["name"], "fid": vault.put_file(base64.b64decode(a["contentBytes"]))})
        _save_incoming(vault, sender, m.get("subject") or "", (m.get("body") or {}).get("content", ""), files,
                       by_email, prospects)
        seen.add(m["id"])
        n += 1
    if n:
        seen_rec["ids"] = list(seen)[-2000:]
        vault.put("settings", seen_rec)
    return n


def fetch_inbox(vault):
    """收取代理发来的新邮件，按发件人邮箱匹配代理。"""
    cfg = settings(vault)
    by_email = {a["email"].lower(): a for a in vault.all("agent") if a.get("email")}
    prospects = {p["email"].lower(): p for p in vault.all("prospect") if p.get("email")}
    if m365_on(cfg):
        return _fetch_m365(vault, cfg, by_email, prospects)
    if not cfg.get("imap_host"):
        return 0
    n = 0
    with imaplib.IMAP4_SSL(cfg["imap_host"]) as m:
        m.login(cfg["imap_user"] or cfg["smtp_user"], cfg["imap_password"] or cfg["smtp_password"])
        m.select("INBOX")
        _, ids = m.search(None, "UNSEEN")
        for i in ids[0].split():
            _, data = m.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1], policy=email.policy.default)
            sender = parseaddr(msg.get("From"))[1].lower()
            part = msg.get_body(preferencelist=("plain",)) if hasattr(msg, "get_body") else None
            body = part.get_content() if part else ""
            files = [{"name": a.get_filename(), "fid": vault.put_file(a.get_payload(decode=True))}
                     for a in msg.iter_attachments() if a.get_filename()]
            _save_incoming(vault, sender, str(make_header(decode_header(msg.get("Subject", "")))), body, files,
                           by_email, prospects)
            n += 1
    return n


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def next_run(c, after):
    cadence = c.get("cadence")
    if cadence in ("每周", "每两周"):
        return (after + dt.timedelta(days=7 if cadence == "每周" else 14)).isoformat(timespec="minutes")
    if cadence in ("每月", "每季度"):
        return _add_months(after, 1 if cadence == "每月" else 3).isoformat(timespec="minutes")
    return None


def recipients(vault, c):
    agents = [a for a in vault.all("agent") if a.get("email")]
    if c.get("audience") == "活跃代理":
        agents = [a for a in agents if a.get("status") == "活跃"]
    elif c.get("audience") == "选定代理":
        agents = [a for a in agents if a["id"] in set(c.get("agent_ids", []))]
    return agents


def run_due(vault, now=None):
    now = now or dt.datetime.now()
    for c in vault.all("campaign"):
        if c.get("active") and c.get("next_at") and dt.datetime.fromisoformat(c["next_at"]) <= now:
            sent = send_to_agents(vault, recipients(vault, c), c["subject"], c["body"], c["id"])
            c["last_at"] = now.isoformat(timespec="minutes")
            c["last_count"] = len(sent)
            c["next_at"] = next_run(c, dt.datetime.fromisoformat(c["next_at"]))
            c["active"] = bool(c["next_at"])
            vault.put("campaign", c)


def start_scheduler(vault, interval=60):
    def loop():
        while True:
            time.sleep(interval)
            try:
                if vault.unlocked:  # 保险库锁定时，定时任务也读不到任何数据
                    run_due(vault)
                    fetch_inbox(vault)
            except Locked:
                pass
            except Exception as e:  # 网络等错误不影响主程序
                vault.audit(f"scheduler error: {type(e).__name__}")
    threading.Thread(target=loop, daemon=True).start()
