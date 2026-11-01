"""从 AP 学分课程管理系统（同一台服务器上的 ap-courses 容器）读取中介推荐的学生，同步到「学生申请进度」。

只读 /api/agent-feed：学生、课程、实收学费、中介信息，看不到家长、成绩等其他数据。地址和密钥由环境变量 AP_FEED_URL、AP_FEED_TOKEN 提供。
学费已到账的学生进度记为「已入学」，之后和其他学生一样一键加进结算单，佣金按代理等级里的 AP 比例（合同 10%）计算。
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


def _intake(row):
    years = re.findall(r"20\d\d", " ".join(c.get("term") or "" for c in row.get("courses", [])))
    return admissions.intake_term(years[0], "Sep") if years else ""


def sync(vault, commissions_locked=None):
    """新学生建记录；已有的只更新学费、课程和中介提示，不覆盖手动改过的代理。还没发出的结算单里的学费跟着更新。"""
    rows = fetch()
    agents = vault.all("agent")
    known = {s["ap_id"]: s for s in vault.all("student") if s.get("ap_id")}
    new = updated = 0
    for r in rows:
        courses = "、".join(c["course"] for c in r.get("courses", []) if c.get("status") != "withdrawn")
        hint = " · ".join(x for x in (r.get("agent_company"), r.get("agent_name"), r.get("agent_email")) if x)
        paid = r.get("tuition_paid") or 0
        st = known.get(r["ap_student_id"])
        if st is None:
            aid, how = admissions.match_agent(r, agents)
            stage = "已入学" if paid > 0 else "收到申请"
            vault.put("student", {"ap_id": r["ap_student_id"], "origin": "AP 学分课程", "name": r.get("name") or "",
                                  "grade": re.sub(r"\D", "", str(r.get("grade") or "")), "intake": _intake(r), "program": "AP",
                                  "courses": courses, "tuition": paid, "agent_id": aid or "", "agent_auto": how, "uses_agent": True,
                                  "agent_hint": hint, "stage": stage, "history": {stage: dt.date.today().isoformat()}})
            new += 1
            continue
        changed = False
        for k, v in (("tuition", paid), ("courses", courses), ("agent_hint", hint)):
            if st.get(k) != v:
                st[k] = v
                changed = True
        if not st.get("agent_id") and not st.get("agent_manual"):
            aid, how = admissions.match_agent(r, agents)
            if aid:
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
