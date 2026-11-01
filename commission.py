"""佣金规则与计算。

合同规则（Service Contract 2025 版）：
  全日制第一年：1–5 名学生按等级基础比例，同一学年满 6 名起按高档比例
      标准级 Standard：20% / 25%      高级 Premier：25% / 30%
  全日制第二年 10%，第三年 5%
  兼职 / 单科：15%（仅首次缴费）
  AP：10%（仅首次缴费）
老代理（30%、25%、25/10/5 等旧合同）保留各自比例，没有 6 人档。

一个学期一个代理 = 一张结算单，结算单里是逐个学生的明细（和现在的 Student Roster 一样）。
从 Excel 导入的历史记录只有汇总金额，用 fee_* 字段保存，照常参与统计。
"""
import re

LEVELS = {
    "standard": {"label": "标准级 Standard（20/25/10/5）", "y1": 20, "y1_6": 25, "y2": 10, "y3": 5, "pt": 15, "ap": 10},
    "premier": {"label": "高级 Premier（25/30/10/5）", "y1": 25, "y1_6": 30, "y2": 10, "y3": 5, "pt": 15, "ap": 10},
}
PROGRAMS = {"FT1": "全日制 第一年", "FT2": "全日制 第二年", "FT3": "全日制 第三年", "PT": "兼职 / 单科", "AP": "AP 课程"}
PART_TIME_RATE = 15.0
SIX_PLUS = 6


def parse_scheme(text):
    """把 Excel 里的写法解析成 [Y1, Y2, Y3] 百分比；解析不了返回 None（需人工设置）。"""
    if text is None or text == "":
        return None
    if isinstance(text, (int, float)):
        pct = text * 100 if text <= 1 else float(text)
        return [round(pct, 2)] * 3
    s = str(text)
    if re.search(r"[a-zA-Z]", s):  # 例如 "30% Single over 3 20%" 这种特殊条款
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)]
    if len(nums) == 1:
        return nums * 3
    if len(nums) == 3:
        return nums
    return None


def agent_scheme(a):
    """代理的完整比例表 {y1, y1_6, y2, y3, pt, ap}。"""
    if a.get("level") in LEVELS:
        sc = dict(LEVELS[a["level"]])
    else:
        r = a.get("rates") or [0, 0, 0]
        sc = {"label": "自定义（旧合同）", "y1": r[0], "y1_6": r[0], "y2": r[1], "y3": r[2], "pt": PART_TIME_RATE, "ap": 10}
    if isinstance(a.get("ap_rate"), (int, float)):  # 合同里写的 AP 课程佣金比例
        sc["ap"] = a["ap_rate"]
    return sc


def scheme_label(rates_or_agent):
    if isinstance(rates_or_agent, dict):
        a = rates_or_agent
        if a.get("level") in LEVELS:
            s = LEVELS[a["level"]]
            return f"{s['y1']:g}%(6人起{s['y1_6']:g}%) / {s['y2']:g}% / {s['y3']:g}%"
        rates_or_agent = a.get("rates")
    rates = rates_or_agent
    if not rates:
        return "未设置"
    if rates[0] == rates[1] == rates[2]:
        return f"{rates[0]:g}%"
    return " / ".join(f"{r:g}%" for r in rates)


def academic_year(term):
    """'Sep-Dec Fall 25-26' -> '25-26'；'2026 Summer School' -> '25-26'（暑期算入刚结束的学年）。"""
    m = re.search(r"(\d{2})-(\d{2})\b", term or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"20(\d{2})", term or "")
    if m:
        y = int(m.group(1))
        return f"{y - 1:02d}-{y:02d}"
    return term


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def ft1_count(statements):
    """同一学年第一年全日制学生人数（按学生去重：同一个学生两个学期都缴费只算 1 人）。"""
    return len({(st.get("name") or "").strip().lower() for s in statements for st in s.get("students", [])
                if st.get("program") == "FT1"})


def calculate(rec, scheme, ay_statements=()):
    """返回 (明细列表, 合计)。

    scheme: agent_scheme() 的结果，或旧的 [Y1, Y2, Y3] 列表
    ay_statements: 同一代理同一学年的全部结算单（用于判断是否满 6 人）
    """
    if isinstance(scheme, (list, tuple)) or scheme is None:
        r = scheme or [0, 0, 0]
        scheme = {"y1": r[0], "y1_6": r[0], "y2": r[1], "y3": r[2], "pt": PART_TIME_RATE, "ap": 10}
    if rec.get("locked"):
        return rec["locked"]["lines"], rec["locked"]["total"]
    n_ft1 = ft1_count(ay_statements) if ay_statements else ft1_count([rec])
    y1 = scheme["y1_6"] if n_ft1 >= SIX_PLUS else scheme["y1"]
    rate_for = {"FT1": y1, "FT2": scheme["y2"], "FT3": scheme["y3"], "PT": scheme["pt"], "AP": scheme["ap"]}
    lines = []

    def add(label, fee, pct, student=None, kind=None):
        fee = _f(fee)
        if fee:
            lines.append({"label": label, "student": student, "fee": fee, "rate": pct, "kind": kind,
                          "amount": round(fee * pct / 100, 2)})

    for st in rec.get("students", []):
        pct = _f(st["rate"]) if st.get("rate") not in (None, "") else rate_for.get(st.get("program"), 0)
        add(PROGRAMS.get(st.get("program"), st.get("program")), st.get("tuition"), pct, st.get("name"), st.get("program"))
    # 旧数据（Excel 汇总）
    add("学期缴费全日制", rec.get("fee_term"), scheme["y1"])
    add("全日制 Year One", rec.get("fee_y1"), scheme["y1"])
    add("全日制 Year Two", rec.get("fee_y2"), scheme["y2"])
    add("全日制 Year Three", rec.get("fee_y3"), scheme["y3"])
    add("兼职学生", rec.get("fee_pt"), scheme["pt"])
    add("AP 课程", rec.get("fee_ap"), _f(rec.get("ap_rate")) if rec.get("ap_rate") is not None else scheme["ap"])
    # 满 6 人后，给本学年之前已发出、按低档结算的第一年学生补差
    if y1 > scheme["y1"]:
        gap = 0.0
        for s in ay_statements:
            lk = s.get("locked")
            if s is rec or not lk or s.get("topped_up_by") not in (None, rec.get("id")):
                continue
            if lk.get("y1_rate", y1) < y1:
                gap += sum(_f(st.get("tuition")) for st in s.get("students", []) if st.get("program") == "FT1") \
                    * (y1 - lk["y1_rate"]) / 100
        if gap:
            lines.append({"label": f"学年满 {SIX_PLUS} 人补差（第一年改按 {y1:g}%）", "fee": None, "rate": None,
                          "amount": round(gap, 2), "kind": "TOPUP"})
    other = _f(rec.get("other_amount"))
    if other:
        lines.append({"label": rec.get("other_note") or "其它调整", "fee": None, "rate": None, "amount": other})
    return lines, round(sum(l["amount"] for l in lines), 2)


def y1_rate_used(scheme, ay_statements, rec):
    n = ft1_count(ay_statements) if ay_statements else ft1_count([rec])
    return scheme["y1_6"] if n >= SIX_PLUS else scheme["y1"]


def total_fees(rec):
    return sum(_f(rec.get(k)) for k in ("fee_term", "fee_y1", "fee_y2", "fee_y3", "fee_pt", "fee_ap")) + \
        sum(_f(s.get("tuition")) for s in rec.get("students", []))
