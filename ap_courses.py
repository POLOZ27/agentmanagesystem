"""从 AP 学分课程管理系统（同一台服务器上的 ap-courses 容器）读取中介推荐的学生，同步到「学生申请进度」。

只读 /api/agent-feed：学生、课程、实收学费、中介信息，看不到家长、成绩等其他数据。地址和密钥由环境变量 AP_FEED_URL、AP_FEED_TOKEN 提供。
学费已到账的学生进度记为「已入学」，之后和其他学生一样一键加进结算单，佣金比例用 AP 系统按这家代理合同给的比例（10%、15% 或 0）。
"""
import datetime as dt
import os
import re

import httpx

import admissions


def enabled():
    return bool(os.environ.get("AP_FEED_URL") and os.environ.get("AP_FEED_TOKEN"))


def fetch():
    r = httpx.get(os.environ["AP_FEED_URL"], timeout=15, headers={"Authorization": "Bearer " + os.environ["AP_FEED_TOKEN"]})
    r.raise_for_status()
    return r.json()["students"]


def push_agents(agents):
    """把中介名单推给 AP 系统，学生页的下拉框从这里选。只给选择需要的字段。"""
    rows = [{k: a.get(k) or "" for k in ("id", "code", "name", "email", "status")} for a in agents]
    rows.sort(key=lambda a: (a["status"] != "活跃", a["code"] or "J9", a["name"]))
    url = os.environ["AP_FEED_URL"].replace("/agent-feed", "/agent-list")
    httpx.post(url, json={"agents": rows}, timeout=15, headers={"Authorization": "Bearer " + os.environ["AP_FEED_TOKEN"]}).raise_for_status()


def _pick_agent(row, agents):
    """AP 系统里从名单选的中介优先，没选的按邮箱和公司名对。"""
    if any(a["id"] == row.get("agent_id") for a in agents):
        return row["agent_id"], "AP 系统里选的中介"
    return admissions.match_agent(row, agents)


def _intake(row):
    years = re.findall(r"20\d\d", " ".join(c.get("term") or "" for c in row.get("courses", [])))
    return admissions.intake_term(years[0], "Sep") if years else ""


def sync(vault, commissions_locked=None):
    """新学生建记录；已有的只更新学费、课程和中介提示，不覆盖手动改过的代理。还没发出的结算单里的学费跟着更新。"""
    rows = fetch()
    agents = vault.all("agent")
    push_agents(agents)
    known = {s["ap_id"]: s for s in vault.all("student") if s.get("ap_id")}
    new = updated = 0
    for r in rows:
        courses = "、".join(c["course"] for c in r.get("courses", []) if c.get("status") != "withdrawn")
        hint = " · ".join(x for x in (r.get("agent_company"), r.get("agent_name"), r.get("agent_email")) if x)
        paid = r.get("tuition_paid") or 0
        st = known.get(r["ap_student_id"])
        if st is None:
            aid, how = _pick_agent(r, agents)
            stage ="已入学" if paid > 0 else "收到申请"
            vault.put("student", {"ap_id": r["ap_student_id"], "origin": "AP 学分课程", "name": r.get("name") or "",
                                  "grade": re.sub(r"\D", "", str(r.get("grade") or "")), "intake": _intake(r), "program": "AP",
                                  "courses": courses, "tuition": paid, "agent_id": aid or "", "agent_auto": how, "uses_agent": True,
                                  "agent_hint": hint, "stage": stage, "history": {stage: dt.date.today().isoformat()},
                                  "rate": (r.get("commission_rate") or 0) * 100})
            new += 1
            continue
        changed = False
        for k, v in (("tuition", paid), ("courses", courses), ("agent_hint", hint), ("rate", (r.get("commission_rate") or 0) * 100)):
            if st.get(k) != v:
                st[k] = v
                changed = True
        if not st.get("agent_manual"):  # AP 系统里改了选择，这里跟着改；代理系统里手动分配过的不动
            aid, how = _pick_agent(r, agents)
            if aid and aid != st.get("agent_id") and (r.get("agent_id") or not st.get("agent_id")):
                st.update(agent_id=aid, agent_auto=how)
                changed = True
        if paid > 0 and st.get("stage") == "收到申请":
            st["stage"] = "已入学"
            st.setdefault("history", {})["已入学"] = dt.date.today().isoformat()
            changed = True
        if changed:
            vault.put("student", st)
            updated += 1
        c = vault.get("commission", st["commission_id"]) if st.get("commission_id") else None
        if c and not c.get("locked"):
            for row in c.get("students", []):
                if row.get("student_id") == st["id"] and row.get("tuition") != paid:
                    row["tuition"] = paid
                    vault.put("commission", c)
    return {"new": new, "updated": updated}
