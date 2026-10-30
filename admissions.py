"""从学校官网后台（同一台服务器上的 ja-db）读取入学申请，同步到「学生申请进度」。

只用一个只读数据库账号，只能看 agent_portal.applications 这个视图（申请号、姓名、年级、入学学期、状态、
代理相关字段），看不到官网的付款、家长、成绩等其他数据。连接地址由环境变量 ADMISSIONS_DB_URL 提供。

学生选了代理的：先按代理邮箱、再按代理公司名自动对上系统里的代理；对不上或没选代理的进「待分配」，由 POLO 手动分配。
"""
import datetime as dt
import os
import re

STATUS_STAGE = {  # 官网申请状态 → 学生申请进度
    "SUBMITTED": "收到申请", "DOCUMENTS_MISSING": "收到申请", "DOCUMENTS_OK": "资料齐全",
    "ACCEPTED": "已发录取信", "DECLINED": "未入学", "WITHDRAWN": "未入学", "WITHDRAWN_NO_RESPONSE": "未入学",
}


def enabled():
    return bool(os.environ.get("ADMISSIONS_DB_URL"))


def fetch():
    import psycopg
    with psycopg.connect(os.environ["ADMISSIONS_DB_URL"], connect_timeout=10) as conn:
        cur = conn.execute("SELECT * FROM agent_portal.applications ORDER BY created_at")
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def intake_term(start_year, start_term):
    """官网的入学年份 + 学期 → 系统里的学期名（如 Sep-Dec Fall 26-27），认不出就原样拼起来。"""
    t = (start_term or "").lower()
    try:
        y = int(re.search(r"\d{4}", str(start_year or "") + " " + t).group()) % 100
    except (AttributeError, ValueError):
        return " ".join(x for x in (str(start_year or ""), start_term or "") if x).strip()
    if any(w in t for w in ("sep", "fall", "autumn")):
        return f"Sep-Dec Fall {y:02d}-{y + 1:02d}"
    if any(w in t for w in ("jan", "winter")):
        return f"Jan-Apr Winter {y - 1:02d}-{y:02d}"
    if "summer" in t or "jul" in t:
        return f"20{y:02d} Summer School"
    if any(w in t for w in ("may", "spring", "apr")):
        return f"May-June Spring {y - 1:02d}-{y:02d}"
    return f"{start_term} {start_year}".strip()


def _norm(s):
    s = re.sub(r"\b(ltd|limited|inc|co|corp|company|llc|t/a|education|consulting|consultancy|services?)\b\.?", " ", (s or "").lower())
    return re.sub(r"[^a-z0-9一-鿿]+", "", s)


def match_agent(row, agents):
    """返回 (agent_id 或 None, 说明)。"""
    email = (row.get("agent_email") or "").strip().lower()
    if email:
        for a in agents:
            if email in [(a.get(k) or "").strip().lower() for k in ("email", "email2")]:
                return a["id"], "按代理邮箱自动对上"
        dom = email.split("@")[-1]
        if dom and dom not in ("gmail.com", "qq.com", "163.com", "126.com", "hotmail.com", "outlook.com", "yahoo.com"):
            hits = [a for a in agents if (a.get("email") or "").lower().endswith("@" + dom)]
            if len(hits) == 1:
                return hits[0]["id"], "按代理邮箱域名自动对上"
    company = _norm(row.get("agent_company"))
    if len(company) >= 4:
        hits = [a for a in agents if any(len(_norm(a.get(k))) >= 4 and (_norm(a.get(k)) in company or company in _norm(a.get(k)))
                                         for k in ("name", "legal_name"))]
        if len(hits) == 1:
            return hits[0]["id"], "按代理公司名自动对上"
    return None, ""


def sync(vault, stages):
    """把官网申请同步成学生记录。返回 {"new", "updated", "unassigned"}。只往前推进度，不覆盖手动改过的代理。"""
    rows = fetch()
    agents = [a for a in vault.all("agent")]
    by_no = {s["web_no"]: s for s in vault.all("student") if s.get("web_no")}
    new = updated = 0
    for r in rows:
        no = r["application_no"]
        st = by_no.get(no)
        stage = STATUS_STAGE.get(r.get("status") or "", "收到申请")
        uses = (r.get("uses_agent") or "").lower() in ("yes", "true", "y", "1", "是")
        hint = " · ".join(x for x in (r.get("agent_company"), r.get("agent_name"), r.get("agent_email")) if x)
        if st is None:
            aid, how = match_agent(r, agents) if uses else (None, "")
            day = (r.get("created_at") or dt.datetime.now()).date().isoformat()
            st = {"web_no": no, "origin": "官网申请", "name": f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip(),
                  "grade": re.sub(r"\D", "", str(r.get("grade") or "")) or (r.get("grade") or ""),
                  "intake": intake_term(r.get("start_year"), r.get("start_term")), "program": "FT1",
                  "country": "" if not r.get("is_international") else "国际生", "agent_id": aid or "",
                  "agent_auto": how, "uses_agent": uses, "agent_hint": hint, "stage": stage, "history": {stage: day},
                  "web_status": r.get("status")}
            vault.put("student", st)
            new += 1
            continue
        changed = False
        for k, v in (("uses_agent", uses if not st.get("agent_manual") else st.get("uses_agent")), ("agent_hint", hint),
                     ("web_status", r.get("status"))):
            if st.get(k) != v:
                st[k] = v
                changed = True
        if uses and not st.get("agent_id") and not st.get("agent_manual"):
            aid, how = match_agent(r, agents)
            if aid:
                st.update(agent_id=aid, agent_auto=how)
                changed = True
        cur_i = stages.index(st["stage"]) if st.get("stage") in stages else -1
        if stage in stages and (stages.index(stage) > cur_i or stage == "未入学") and st.get("stage") not in ("已入学",):
            if st.get("stage") != stage:
                st["stage"] = stage
                st.setdefault("history", {})[stage] = dt.date.today().isoformat()
                changed = True
        if changed:
            vault.put("student", st)
            updated += 1
    unassigned = sum(1 for s in vault.all("student") if s.get("web_no") and s.get("uses_agent") and not s.get("agent_id"))
    return {"new": new, "updated": updated, "unassigned": unassigned}
