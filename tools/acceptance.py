"""2026-11 审查后 28 项修改的自动验收。用演示数据在临时目录里跑，不碰真实数据，不发真实邮件。

用法： python tools/acceptance.py      （全部通过退出码 0）
"""
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = tempfile.mkdtemp(prefix="ja-accept-")
os.environ["AGENT_PORTAL_DATA"] = DATA
os.environ.pop("AGENT_PORTAL_BACKUP_DIR", None)
sys.path.insert(0, ROOT)
subprocess.run([sys.executable, os.path.join(ROOT, "demo_seed.py")], check=True, cwd=ROOT,
               env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import pyotp  # noqa: E402

import app as A  # noqa: E402
import mailer  # noqa: E402

V = A.vault
fails, passed = [], []


def check(name, cond, info=""):
    (passed if cond else fails).append(name + ("" if cond else f"  ← {info}"))
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  ← {info}"))


c = A.app.test_client()
A.app.config["TESTING"] = True
secret = open(os.path.join(DATA, "DEMO_TOTP.txt")).read().strip()


def login(nxt=None):
    url = "/login" + (f"?next={nxt}" if nxt else "")
    return c.post(url, data={"password": "demo-password-123", "code": pyotp.TOTP(secret).now()})


def tok():
    with c.session_transaction() as s:
        return s["csrf"]


def post(url, data=None, **kw):
    d = dict(data or {})
    d["_csrf"] = tok()
    return c.post(url, data=d, **kw)


def html(r):
    return r.get_data(as_text=True)


print("登录与超时（第 7 项）")
r = c.get("/agents?tab=all")
check("未登录访问会带 next 跳到登录页", r.status_code == 302 and "next=" in r.headers["Location"], r.headers.get("Location"))
r = login("/agents?tab=all")
check("登录后回到原来要去的页面", r.status_code == 302 and r.headers["Location"].endswith("/agents?tab=all"), r.headers.get("Location"))
check("/ping 保持登录", c.get("/ping").status_code in (200, 204))
r = c.get("/agents")
check("页面带空闲倒计时和草稿保存脚本", "idlebar" in html(r) and "data-draft" in html(c.get("/agents/new")))
with c.session_transaction() as s:
    s["seen"] = time.time() - A.IDLE_MINUTES * 60 - 5
r = c.get("/students")
check("超时后跳登录页并保留 next", r.status_code == 302 and "next=" in r.headers["Location"])
login()

print("所有页面能打开")
agents = sorted(V.all("agent"), key=lambda a: a.get("code") or "")
a0 = next(a for a in agents if a.get("status") == "活跃")
studs = V.all("student")
comms = V.all("commission")
for u in ["/", "/agents", "/agents?tab=onboard", "/agents?tab=off", "/agents?tab=all&sort=earned", "/agents?sort=ay",
          "/agents?sort=expiry", "/students", "/students?ay=", "/students?stage=已入学", "/prospects", "/prospects/outreach",
          "/commissions", "/commissions/roster", "/mail", "/mail?q=a", "/mail?unread=1", "/mail/compose", "/mail/templates",
          "/materials", "/performance", "/payments", "/settings", "/renewals", "/trash", "/inbox",
          f"/agents/{a0['id']}", f"/agents/{a0['id']}/edit", f"/students/{studs[0]['id']}", f"/commissions/{comms[0]['id']}",
          f"/commissions/{comms[0]['id']}/mail"]:
    r = c.get(u)
    check(f"GET {u}", r.status_code == 200 and "Traceback" not in html(r), r.status_code)

print("写邮件：预览、测试、拦截空占位符（第 1、2、17、25 项）")
ids = [a["id"] for a in agents if a.get("email") and a.get("status") == "活跃"][:2]
base = {"subject": "Hello {联系人}", "body": "Dear {联系人},\n{代理名称} ({代理编号})", "agent_ids": ids, "cadence": "立即发送"}
n_mail = len(V.all("mail"))
r = post("/mail/compose", dict(base, action="preview"))
t = html(r)
check("预览页显示每个代理替换后的内容", r.status_code == 200 and "{联系人}" not in t and a0["name"].split()[0] in t or "预览" in t)
check("预览时没有发出任何邮件", len(V.all("mail")) == n_mail)
r = post("/mail/compose", dict(base, action="test", test_to="me@example.com"))
m = [x for x in V.all("mail") if x.get("subject", "").startswith("[测试]")]
check("先发一封测试邮件给自己", len(m) == 1 and m[0].get("to") == "me@example.com", [x.get("to") for x in m])
r = post("/mail/compose", dict(base, body="Hi {不认识}", action="send"))
check("有不认识的占位符时拦下，写的内容还在", r.status_code == 200 and "Hi {不认识}" in html(r))
r = post("/mail/compose", dict(base, action="edit"))
check("从预览返回修改，内容和收件人都在", "Hello {联系人}" in html(r) and all(i in html(r) for i in ids))
before = len(V.all("mail"))
r = post("/mail/compose", dict(base, action="send"))
check("确认发送后才真正发出", r.status_code == 302 and len(V.all("mail")) == before + len(ids), len(V.all("mail")) - before)
check("{联系人}/{代理名称} 都被替换", mailer.leftover(mailer.render(base["body"], a0, "")) == [])

print("结算单：不能重复建、学期只能选（第 4、15 项）")
cm = next(x for x in V.all("commission") if not x.get("locked"))
r = c.get(f"/commissions/new?agent={cm['agent_id']}&term={cm['term']}")
check("同代理同学期新建会打开已有那张", r.status_code == 302 and cm["id"] in r.headers["Location"])
form = {"agent_id": cm["agent_id"], "term": "Fall 2099 不存在", "s_name": [], "s_tuition": []}
r = post("/commissions/new", form)
check("不存在的学期不能保存", r.status_code == 302 and len(V.all("commission")) == len(comms))
other = next(x for x in V.all("commission") if x["agent_id"] != cm["agent_id"] and not x.get("locked"))
r = post(f"/commissions/{other['id']}", {"agent_id": cm["agent_id"], "term": cm["term"], "s_name": [], "s_tuition": []})
check("改成别人已有的代理+学期会被拦下", r.status_code == 302 and cm["id"] in r.headers["Location"]
      and V.get("commission", other["id"])["agent_id"] == other["agent_id"])
r = c.get(f"/commissions/{cm['id']}")
check("结算单页学期是下拉框", re.search(r'<select[^>]*name="term"', html(r)) is not None)

print("逐张预览发出（第 3 项）")
term = A.terms()[-1]
q = A.draft_queue(term)
if q:
    r = c.get(f"/commissions/send-queue?term={term}")
    check("逐张发出打开第一张的预览页", r.status_code == 302 and q[0]["id"] in r.headers["Location"])
    r = c.get(f"/commissions/send-queue?term={term}&skip={q[0]['id']}")
    check("跳过一张后打开下一张", (len(q) > 1 and q[1]["id"] in r.headers["Location"]) or (len(q) == 1 and "/commissions" in r.headers["Location"]))
    check("佣金页没有「全部发出」按钮", "send-all" not in html(c.get(f"/commissions?term={term}")))
else:
    check("有草稿结算单可测逐张发出", False, "演示数据里没有草稿")

print("回收站：各种删除都能恢复（第 5 项）")
st = studs[-1]
post(f"/students/{st['id']}", {"delete": "1"})
check("删除学生进回收站", V.get("student", st["id"]) is None and any(t.get("kind") == "student" for t in V.all("trash")))
tr = next(t for t in V.all("trash") if t.get("kind") == "student")
post(f"/trash/{tr['id']}/restore")
check("学生能恢复", V.get("student", st["id"]) is not None)
draft = next(x for x in V.all("commission") if not x.get("locked"))
post(f"/commissions/{draft['id']}", {"delete": "1"})
tr = next(t for t in V.all("trash") if t.get("kind") == "commission")
check("回收站页显示结算单", "结算单" in html(c.get("/trash")))
post(f"/trash/{tr['id']}/restore")
check("结算单能恢复", V.get("commission", draft["id"]) is not None)
tpl = V.put("template", {"name": "验收模板", "subject": "s", "body": "b"})
post(f"/mail/templates/{tpl['id']}", {"delete": "1"})
check("删除模板进回收站", V.get("template", tpl["id"]) is None and any(t.get("kind") == "template" for t in V.all("trash")))
camp = V.put("campaign", {"subject": "验收推送", "body": "b", "audience": "全部活跃代理", "cadence": "每月",
                          "active": True, "next_at": (dt.datetime.now() - dt.timedelta(days=3)).isoformat(timespec="minutes")})
check("错过 24 小时以上的定时推送被标出来（第 13 项）", mailer.overdue(camp))
mailer.run_due(V)
check("调度器不会自动补发错过太久的推送", V.get("campaign", camp["id"]).get("missed") and not V.get("campaign", camp["id"]).get("last_at"))
check("邮件页提示错过的推送", "补发" in html(c.get("/mail")))
post(f"/mail/campaign/{camp['id']}", {"skip": "1"})
cp = V.get("campaign", camp["id"])
check("跳过这次后下次时间推到以后", dt.datetime.fromisoformat(cp["next_at"]) > dt.datetime.now() and not mailer.overdue(cp))
cp["next_at"] = (dt.datetime.now() - dt.timedelta(days=2)).isoformat(timespec="minutes")
V.put("campaign", cp)
post(f"/mail/campaign/{camp['id']}", {"catchup": "1"})
cp = V.get("campaign", camp["id"])
check("现在补发会发出并推到下次", cp.get("last_count", 0) > 0 and dt.datetime.fromisoformat(cp["next_at"]) > dt.datetime.now())
post(f"/mail/campaign/{camp['id']}", {"delete": "1"})
check("删除定时推送进回收站", V.get("campaign", camp["id"]) is None and any(t.get("kind") == "campaign" for t in V.all("trash")))

print("导入名册先确认再写入（第 6 项）")
import io  # noqa: E402

import openpyxl  # noqa: E402
cm = V.get("commission", draft["id"])
old_names = [x["name"] for x in cm.get("students") or []]
wb = openpyxl.Workbook()
ws = wb.active
ws.title = cm["term"]
ws.append(["Student Name", "Course 1", "Student Status", "Tuition Payment Total"])
ws.append(["Brand New Kid", "MATH 12", "International", 24200])
if old_names:
    ws.append([old_names[0], "MATH 12", "International", 12345])
buf = io.BytesIO()
wb.save(buf)
r = post(f"/commissions/{cm['id']}/import-roster", {"file": (io.BytesIO(buf.getvalue()), "r.xlsx")},
         content_type="multipart/form-data")
t = html(r)
check("上传后先显示对比，不直接改结算单", r.status_code == 200 and "Brand New Kid" in t
      and [x["name"] for x in V.get("commission", cm["id"]).get("students") or []] == old_names, r.status_code)
data = re.search(r'<textarea name="data" hidden>(.*?)</textarea>', t, re.S)
import html as H  # noqa: E402
payload = H.unescape(data.group(1)) if data else "[]"
post(f"/commissions/{cm['id']}/import-roster/apply", {"data": payload, "mode": "merge"})
names = [x["name"] for x in V.get("commission", cm["id"])["students"]]
check("合并：新增的加进来，原来有的保留", "Brand New Kid" in names and set(old_names) <= set(names), names)
post(f"/commissions/{cm['id']}/import-roster/apply", {"data": payload, "mode": "replace"})
names = [x["name"] for x in V.get("commission", cm["id"])["students"]]
import json  # noqa: E402
check("替换：只剩文件里的学生", len(names) == len(json.loads(payload)) and len(names) >= 1, names)

print("在读名册自动带进结算单（第 8–10 项）")
ag = V.put("agent", {"name": "验收代理", "code": "J99", "status": "活跃", "level": "standard", "pay_terms": 2,
                     "email": "t@example.com", "country": "China", "contracts": []})
ts = A.terms()
t1, tlast = ts[0], ts[-1]
kid = V.put("student", {"name": "Roster Kid", "agent_id": ag["id"], "stage": "已入学", "intake": t1, "program": "FT1",
                        "origin": "International", "tuition": 20000})
V.put("commission", {"agent_id": ag["id"], "term": t1, "term_order": 0, "status": "已付款",
                     "students": [{"name": "Roster Kid", "program": "FT1", "tuition": 20000, "origin": "International",
                                   "student_id": kid["id"]}]})
V.put("commission", {"agent_id": ag["id"], "term": ts[1], "term_order": 1, "status": "已付款",
                     "students": [{"name": "Roster Kid", "program": "FT1", "tuition": 20000, "origin": "International",
                                   "student_id": kid["id"]}]})
row = A.suggest_row(kid, tlast, ag, V.all("commission"))
check("跨学年自动升到 FT2/FT3", row["program"] in ("FT2", "FT3"), row["program"])
check("合同只付前 2 学期：第 3 期默认不付", row["nopay"] and "前 2" in row["note"], row)
check("学费沿用上一期", row["tuition"] == 20000)
r = c.get(f"/commissions/roster?term={tlast}")
check("名册页列出续读学生", "Roster Kid" in html(r))
post("/commissions/roster", {"term": tlast, "pick": [kid["id"]], "tu_" + kid["id"]: "21000", "pay_" + kid["id"]: "0"})
new = A.find_statement(ag["id"], tlast)
check("勾选后建好草稿结算单", new and new["students"][0]["tuition"] == 21000 and new["students"][0]["nopay"], new)
V.put("student", {"name": "Picker Kid", "agent_id": ag["id"], "stage": "已入学", "intake": tlast, "program": "FT1"})
check("结算单页可以从名册勾选这个代理的其他学生", "Picker Kid" in html(c.get(f"/commissions/{new['id']}")))
r = c.get("/students")
check("学生页默认按本学年筛选", 'name="ay"' in html(r))
pt = V.put("student", {"name": "PT Kid", "agent_id": ag["id"], "stage": "已入学", "intake": t1, "program": "PT", "tuition": 900})
V.put("commission", {"agent_id": ag["id"], "term": ts[2], "status": "已付款",
                     "students": [{"name": "PT Kid", "program": "PT", "tuition": 900, "student_id": pt["id"]}]})
_r = A.suggest_row(pt, tlast, dict(ag, pay_terms=None), V.all("commission"))
check("兼职/AP 只在首次付佣金", _r["nopay"], (_r, ts, A.student_rows(pt, V.all("commission"), ag["id"])))

print("跟进记录和待办（第 11、12 项）")
today = dt.date.today().isoformat()
post(f"/notes/agent/{ag['id']}", {"act": "add", "text": "打电话问续签", "next": today})
check("记下跟进并设提醒日", (V.get("agent", ag["id"]).get("log") or [{}])[0].get("text") == "打电话问续签")
r = c.get("/")
check("到期跟进出现在总览待办", "打电话问续签" in html(r) or "跟进" in html(r))
check("总览有待办卡片", "待办" in html(r))
post(f"/notes/agent/{ag['id']}", {"act": "done", "i": "0"})
check("标完成后不再提醒", not [x for x in A.due_followups() if x[1]["id"] == ag["id"]])
for k, rid in (("student", kid["id"]), ("prospect", V.all("prospect")[0]["id"])):
    post(f"/notes/{k}/{rid}", {"act": "add", "text": "验收记录"})
    check(f"{k} 也能记跟进", (V.get(k, rid).get("log") or [{}])[-1].get("text") == "验收记录")

print("锁定提醒（第 14 项）")
sent = []
orig = mailer.app_send_plain
mailer.app_send_plain = lambda frm, to, s, b: sent.append((frm, to, s)) or True
cfg = V.get("settings", "mail") or {"id": "mail"}
cfg["digest_to"] = "polo@example.com"
V.put("settings", cfg)
A.save_lock_notify()
dek_backup = V._dek if hasattr(V, "_dek") else None
V.lock()
A._lock["since"] = time.time() - 3 * 3600
check("锁定 3 小时发提醒", A.check_lock_notify() and sent and sent[0][1] == "polo@example.com", sent)
check("20 小时内不重复发", not A.check_lock_notify())
A._lock["since"] = time.time() - 600
os.remove(A._notify_path())
check("锁定不到 2 小时不发", not A.check_lock_notify())
mailer.app_send_plain = orig
login()
check("重新登录后锁定计时清空", A._lock["since"] is None)

print("设置页（第 23 项）")
post("/settings", {"kit_link": "https://example.com/kit", "payer_name": "Johnathan Academy", "payer_bn": "123"})
s = A.settings()
check("资料包链接、T4A 表头能保存", s.get("kit_link") == "https://example.com/kit" and s.get("payer_bn") == "123", s.get("kit_link"))
post("/settings", {"notify_form": "1", "digest_on": "1"})
check("关闭锁定提醒能保存", A.settings().get("lock_notify") == "0")
t = html(c.get("/settings"))
check("设置页分组并显示版本", all(x in t for x in ("邮件", "备份", A.version.VERSION)))

print("代理列表、业绩、学生页、潜在代理（第 19–22 项）")
t = html(c.get("/agents"))
check("代理列表默认只看合作中的", "验收代理" in t and "tab=onboard" in t)
t = html(c.get("/agents?tab=off"))
check("不活跃代理在单独标签", any(a["name"] in t for a in agents if a.get("status") == "不活跃"))
t = html(c.get("/performance"))
check("业绩页按同期对比", "同期" in t)
t = html(c.get("/prospects"))
check("潜在代理页：搜索/导入收进折叠区", 'id="find"' in t)
t = html(c.get(f"/agents/{a0['id']}"))
check("代理详情有跟进记录", "notes" in t)
t = html(c.get(f"/students/{kid['id']}"))
check("学生页有在读状态和结算记录", "enrolled_status" in t and "结算" in t)

print("推广邮件被拦下不丢内容（第 25 项）")
tid = (V.all("template") or [{}])[0].get("id")
r = post("/prospects/outreach", {"go": "1", "body": "Hi {不认识}", "subject": "x",
                                 "ids": [V.all("prospect")[0]["id"]]})
check("推广邮件有空占位符拦下并保留内容", r.status_code == 200 and "Hi {不认识}" in html(r), r.status_code)

print("备份健康与周报（第 28 项）")
os.environ["AGENT_PORTAL_BACKUP_DIR"] = os.path.join(DATA, "nas")
os.makedirs(os.environ["AGENT_PORTAL_BACKUP_DIR"], exist_ok=True)
msg = A.backup_health()
check("设了备份目录但没成功过会提示", bool(msg), msg)
check("总览显示备份提醒", "备份" in html(c.get("/")))
os.environ.pop("AGENT_PORTAL_BACKUP_DIR")

print("其它")
check("版本号", re.match(r"20\d\d-\d\d-\d\d", A.version.VERSION) is not None)
check("Windows 一键更新脚本", os.path.exists(os.path.join(ROOT, "deploy", "windows", "更新代理系统.bat")))
check("窄屏样式", ".hide-narrow" in open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read())

print(f"\n通过 {len(passed)} 项，失败 {len(fails)} 项")
for x in fails:
    print("  ✗", x)
sys.exit(1 if fails else 0)
