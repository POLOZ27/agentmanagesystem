"""结算单 Excel（发给代理）和学生名单导入（兼容现在的 Student Roster 格式）。"""
import io
import re

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from commission import PROGRAMS


def statement_xlsx(agent, rec, lines, total):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\\/*?:\[\]]", "-", rec["term"])[:31]
    bold = Font(bold=True)
    ws.append(["Johnathan Academy – Agent Commission Statement"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Agent", f"{agent.get('name', '')} ({agent.get('code', '')})"])
    ws.append(["Term", rec["term"]])
    ws.append([])
    head = ["Student Name", "Program", "Courses", "Local / International", "Tuition Paid", "Rate", "Commission", "Note"]
    ws.append(head)
    for c in ws[5]:
        c.font = bold
        c.fill = PatternFill("solid", fgColor="DCE6F1")
    by_name = iter(rec.get("students", []))
    for l in lines:
        st = next(by_name, {}) if l.get("student") is not None else {}
        ws.append([l.get("student") or "", PROGRAMS.get(l.get("kind"), l["label"]), st.get("courses", ""),
                   st.get("origin", ""), l.get("fee"), f"{l['rate']:g}%" if l.get("rate") is not None else "",
                   l["amount"], st.get("note", "")])
    ws.append([])
    ws.append(["", "", "", "", "", "Total", total])
    ws.cell(ws.max_row, 6).font = bold
    ws.cell(ws.max_row, 7).font = bold
    for row in ws.iter_rows(min_row=6):
        for c in (row[4], row[6]):
            c.number_format = '"$"#,##0.00'
    for col, w in zip("ABCDEFGH", (26, 20, 34, 18, 14, 8, 14, 30)):
        ws.column_dimensions[col].width = w
    ws["A1"].alignment = Alignment(horizontal="left")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _program(courses):
    t = courses.lower()
    if "full-time" in t or "full time" in t:
        if "second" in t:
            return "FT2"
        if "third" in t:
            return "FT3"
        return "FT1"
    if re.search(r"\bap\b", t):
        return "AP"
    return "PT"


def parse_roster(data, sheet=None):
    """读取现在的 Student Roster Excel（每个学期一个工作表），返回 {工作表名: [学生行]}。"""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    out = {}
    for ws in wb.worksheets:
        if sheet and ws.title != sheet:
            continue
        rows = list(ws.iter_rows(values_only=True))
        if not rows or not rows[0] or str(rows[0][0]).strip() != "Student Name":
            continue
        head = [str(h or "").strip() for h in rows[0]]
        idx = {h: i for i, h in enumerate(head)}
        students = []
        for r in rows[1:]:
            name = str(r[0] or "").strip()
            if not name or name.lower().startswith("total"):
                continue
            courses = ", ".join(str(r[idx[c]]).strip() for c in ("Course 1", "Course 2", "Course 3")
                                if c in idx and r[idx[c]] not in (None, ""))
            tuition = r[idx["Tuition Payment Total"]] if "Tuition Payment Total" in idx else None
            if not isinstance(tuition, (int, float)):
                continue
            status = str(r[idx["Student Status"]] or "").strip() if "Student Status" in idx else ""
            students.append({"name": name, "program": _program(courses), "courses": courses, "tuition": float(tuition),
                             "origin": status, "period": str(r[idx["Marks period"]] or "") if "Marks period" in idx else "",
                             "note": str(r[idx["Note"]] or "") if "Note" in idx else ""})
        out[ws.title] = students
    return out


# ---------- 发给代理的 Student Roster：以前所有学期 + 本学期新加一个工作表 ----------
ROSTER_HEAD = ["Student Name", "Course 1", "Course 2", "Course 3", "Tuition Payment Total",
               "Commission                                                     {rule}", "Agent", "Student Status",
               "Marks period", "Note"]
ORDINAL = {"FT1": "First", "FT2": "Second", "FT3": "Third"}
MONEY_FMT = '[$$-1009]#,##0.00'


def sheet_title(term):
    return re.sub(r"[\\/*?:\[\]]", "-", term)[:31]


def roster_rule(scheme):
    """表头里的比例说明，和现在 Roster 的写法一样，例如 Full 20%, 10%, 5% Part 15%。"""
    y = [scheme.get("y1"), scheme.get("y2"), scheme.get("y3")]
    full = f"{y[0]:g}%" if y[0] == y[1] == y[2] else ", ".join(f"{v:g}%" for v in y)
    if scheme.get("y1_6") and scheme["y1_6"] != scheme["y1"]:
        full += f" (6+ students {scheme['y1_6']:g}%)"
    return f"Full {full} Part {scheme.get('pt', 15):g}%"


def _courses(st):
    if st.get("program") in ORDINAL:
        g = str(st.get("grade") or "").strip().upper().lstrip("G")
        return [f"{'G' + g + ' ' if g else ''}Full-time {ORDINAL[st['program']]} year", "", ""]
    parts = [p.strip() for p in (st.get("courses") or "").split(",") if p.strip()]
    if st.get("program") == "AP" and not parts:
        parts = ["AP"]
    parts = parts[:3] if len(parts) <= 3 else parts[:2] + [", ".join(parts[2:])]
    return parts + [""] * (3 - len(parts))


def roster_rows(rec, lines):
    """结算单 → Roster 行：[(学生名, 课程1-3, 学费, 比例%, 佣金, 身份, 期间, 备注)]"""
    by_student = {}
    for l in lines:
        if l.get("student") is not None:
            by_student.setdefault(l["student"], []).append(l)
    rows = []
    for st in rec.get("students", []):
        l = (by_student.get(st.get("name")) or [None]).pop(0)
        if not l:
            continue
        rows.append({"name": st["name"], "courses": _courses(st), "fee": l["fee"], "rate": l["rate"], "amount": l["amount"],
                     "origin": st.get("origin", ""), "period": st.get("period", ""), "note": st.get("note", "")})
    for l in lines:
        if l.get("student") is None and l.get("fee") is None:  # 满 6 人补差、其它调整
            rows.append({"name": "", "courses": ["", "", ""], "fee": None, "rate": None, "amount": l["amount"],
                         "origin": "", "period": "", "note": l["label"]})
    return rows


def _blank_roster(title):
    from openpyxl.styles import Font as F
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(ROSTER_HEAD)
    for c in ws[1]:
        c.font = F(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[1].height = 31.25
    for col, w in zip("ABCDEFGHIJ", (22, 26, 16, 16, 22, 32, 15, 15, 30, 18)):
        ws.column_dimensions[col].width = w
    return wb, ws


def roster_workbook(base, term, rec, lines, scheme, agent_label, today=None):
    """base：代理以前的 Roster（字节，可为 None）。返回加上（或替换）本学期工作表后的 Excel 字节。
    新工作表照最后一个学期的样式复制，所以字体、列宽、金额格式都和以前一样。"""
    import datetime as _dt
    today = today or _dt.date.today()
    title = sheet_title(term)
    wb = openpyxl.load_workbook(io.BytesIO(base)) if base else None
    if wb:
        tpl = next((ws for ws in reversed(wb.worksheets)
                    if ws.title != title and str(ws["A1"].value or "").strip() == "Student Name"), None)
        if title in wb.sheetnames:
            idx = wb.sheetnames.index(title)
            del wb[title]
        else:
            idx = len(wb.sheetnames)
        if tpl is not None:
            ws = wb.copy_worksheet(tpl)
            ws.title = title
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    c.value = None
        else:
            ws = wb.create_sheet(title)
            ws.append(ROSTER_HEAD)
        wb.move_sheet(ws, offset=idx - wb.sheetnames.index(title))
        for i, h in enumerate(ROSTER_HEAD, 1):  # 以前有的学期少一栏或多一栏，新表一律用标准的 10 栏
            ws.cell(1, i).value = h
        for i in range(len(ROSTER_HEAD) + 1, ws.max_column + 1):
            ws.cell(1, i).value = None
        wb.active = wb.sheetnames.index(title)
        for s in wb.worksheets:
            s.sheet_view.tabSelected = s.title == title
    else:
        wb, ws = _blank_roster(title)
    ws.cell(1, 6).value = ROSTER_HEAD[5].format(rule=roster_rule(scheme))
    rows = roster_rows(rec, lines)
    r = 1
    for r, x in enumerate(rows, 2):
        vals = [x["name"], *x["courses"], x["fee"],
                f"=E{r}*{x['rate'] / 100:g}" if x["rate"] is not None and x["fee"] is not None else x["amount"],
                agent_label if x["name"] else "", x["origin"], x["period"], x["note"]]
        for i, v in enumerate(vals, 1):
            ws.cell(r, i).value = v if v != "" else None
        ws.cell(r, 5).number_format = MONEY_FMT
        ws.cell(r, 6).number_format = MONEY_FMT
    total_row = max(13, r + 3)
    ws.cell(total_row, 5).value = f"Total Commission Until {today.strftime('%b')}-{today.day}-{today.year}"
    ws.cell(total_row, 6).value = f"=SUM(F2:F{max(r, 2)})"
    ws.cell(total_row, 5).font = Font(bold=True)
    ws.cell(total_row, 6).font = Font(bold=True)
    ws.cell(total_row, 6).number_format = MONEY_FMT
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def last_agent_label(base):
    """以前 Roster 里 Agent 一栏最后写的称呼（例如 Shanice、Jerry），新工作表沿用。"""
    if not base:
        return ""
    wb = openpyxl.load_workbook(io.BytesIO(base), data_only=True)
    for ws in reversed(wb.worksheets):
        head = [str(c.value or "").strip() for c in ws[1]]
        if "Agent" not in head:
            continue
        col = head.index("Agent")
        vals = [r[col] for r in ws.iter_rows(min_row=2, values_only=True) if len(r) > col and r[col]]
        if vals:
            return str(vals[-1]).strip()
    return ""


_CELL = re.compile(r"^([A-Z]+)(\d+)$")


def _eval(formula, grid):
    """预览用：只算 Roster 里常见的 =E2*0.25、=SUM(F2:F9)、=E2+E3 这几种；算不了就显示公式。"""
    from openpyxl.utils import column_index_from_string as ci

    def val(ref):
        m = _CELL.match(ref)
        v = grid.get((int(m.group(2)), ci(m.group(1)))) if m else None
        return v if isinstance(v, (int, float)) else 0
    f = formula[1:].replace(" ", "")
    m = re.fullmatch(r"SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)", f, re.I)
    if m:
        c1, r1, c2, r2 = ci(m.group(1).upper()), int(m.group(2)), ci(m.group(3).upper()), int(m.group(4))
        return sum(v for (r, c), v in grid.items() if r1 <= r <= r2 and c1 <= c <= c2 and isinstance(v, (int, float)))
    if re.fullmatch(r"[A-Z]+\d+([*+\-/][A-Z0-9.]+)*", f):
        expr = re.sub(r"[A-Z]+\d+", lambda x: repr(val(x.group(0))), f)
        try:
            return eval(expr, {"__builtins__": {}}, {})  # 只剩数字和 + - * /
        except Exception:  # noqa: BLE001
            return formula
    return formula


def preview(data, max_rows=60):
    """把 Excel 变成网页预览：[{title, rows: [[文字…]]}]，公式按上面的规则算出来。"""
    wb = openpyxl.load_workbook(io.BytesIO(data))
    cached = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    out = []
    for ws in wb.worksheets:
        cw = cached[ws.title]
        grid = {}
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    cv = cw.cell(c.row, c.column).value
                    v = cv if cv is not None else None
                grid[(c.row, c.column)] = v
        for row in ws.iter_rows():  # 第二遍：没有缓存值的公式自己算（SUM 用到的先算出来）
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("=") and grid[(c.row, c.column)] is None:
                    grid[(c.row, c.column)] = _eval(c.value, grid)
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("=SUM") and cw.cell(c.row, c.column).value is None:
                    grid[(c.row, c.column)] = _eval(c.value, grid)
        n_rows = max([r for (r, c), v in grid.items() if v not in (None, "")] or [0])
        n_cols = max([c for (r, c), v in grid.items() if v not in (None, "")] or [0])
        rows = []
        for r in range(1, min(n_rows, max_rows) + 1):
            cells = []
            for c in range(1, n_cols + 1):
                v = grid.get((r, c))
                fmt = ws.cell(r, c).number_format or ""
                if isinstance(v, (int, float)) and ("$" in fmt or (r > 1 and c in (5, 6))):
                    v = f"${v:,.2f}"
                elif isinstance(v, float):
                    v = f"{v:g}"
                cells.append("" if v is None else str(v))
            rows.append(cells)
        out.append({"title": ws.title, "rows": rows, "more": n_rows > max_rows})
    return out


# ---------- 佣金总表（POLO 原来的《代理表》：每个结算期一个工作表，发给会计付款） ----------
MASTER_HEAD = ["代理名称", "代理编号", "Commission %", "学期缴费全日制学生", "学期已缴费用", "全日制学生 Year One",
               "全日制学生 Year Two", "全日制学生 Year Three", "全日制学生已缴费用", "兼职学生15%", "兼职学生已缴费用",
               "AP 课程", "AP 返佣比例", "AP 已缴费用", "已缴学费总金额", "其它", "Commission 金额",
               "E-Transfer address", "支票抬头", "Detail"]
_FT = {"FT1": "全日制学生 Year One", "FT2": "全日制学生 Year Two", "FT3": "全日制学生 Year Three"}


def _who(students):
    """几个学生 + 年级，和原来表里的写法一样，例如 2 G10 G11。"""
    if not students:
        return None
    grades = [f"G{str(s.get('grade')).strip().upper().lstrip('G')}" for s in students if s.get("grade")]
    return " ".join([str(len(students))] + grades)


def master_row(agent, c, scheme_text):
    """一个代理在一个结算期的一行。c：enrich 过的结算单，没有就 None（这个结算期没有学生，照样列出来）。"""
    row = {"代理名称": agent.get("name"), "代理编号": agent.get("code"), "Commission %": scheme_text,
           "E-Transfer address": agent.get("etransfer"), "支票抬头": agent.get("payee"), "Detail": agent.get("detail")}
    if not c:
        return row, None
    by = {}
    for st in c.get("students", []):
        by.setdefault(st.get("program"), []).append(st)
    for prog, col in _FT.items():
        row[col] = _who(by.get(prog))
    lines = c["lines"]
    fee = lambda kinds, labels=(): round(sum(l["fee"] or 0 for l in lines
                                             if l.get("kind") in kinds or l["label"] in labels), 2) or None
    row["全日制学生已缴费用"] = fee(("FT1", "FT2", "FT3"), ("全日制 Year One", "全日制 Year Two", "全日制 Year Three"))
    row["学期已缴费用"] = fee((), ("学期缴费全日制",))
    row["兼职学生15%"] = _who(by.get("PT")) or c.get("stu_pt")
    row["兼职学生已缴费用"] = fee(("PT",), ("兼职学生",))
    row["AP 课程"] = _who(by.get("AP")) or c.get("stu_ap")
    ap_rates = sorted({l["rate"] for l in lines if l.get("kind") == "AP" or l["label"] == "AP 课程"})
    row["AP 返佣比例"] = ", ".join(f"{r:g}%" for r in ap_rates) or None
    row["AP 已缴费用"] = fee(("AP",), ("AP 课程",))
    extra = round(sum(l["amount"] for l in lines if l.get("fee") is None), 2)
    if extra:
        row["其它"] = extra
    return row, c["amount"]


def master_workbook(base, term, rows, today=None):
    """base：上一次的总表（字节，可为 None）。rows：[(行 dict, 佣金金额)]。
    照最后一个结算期的工作表复制出新的一页（同名就替换），列按表头名字对上，所以老表多一列少一列都不怕。
    已缴学费总金额和 Commission 金额写成公式，会计可以核对。"""
    title = sheet_title(term)
    wb = openpyxl.load_workbook(io.BytesIO(base)) if base else None
    if wb:
        tpl = next((ws for ws in reversed(wb.worksheets) if ws.title != title
                    and any(str(c.value or "").strip() == "代理名称" for c in ws[1])), None)
        idx = wb.sheetnames.index(title) if title in wb.sheetnames else len(wb.sheetnames)
        if title in wb.sheetnames:
            del wb[title]
        if tpl is not None:
            ws = wb.copy_worksheet(tpl)
            ws.title = title
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    c.value = None
        else:
            ws = wb.create_sheet(title)
            ws.append(MASTER_HEAD)
        wb.move_sheet(ws, offset=idx - wb.sheetnames.index(title))
        wb.active = wb.sheetnames.index(title)
        for s in wb.worksheets:
            s.sheet_view.tabSelected = s.title == title
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title
        ws.append(MASTER_HEAD)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for i, w in enumerate((26, 12, 22, 10, 12, 14, 14, 14, 14, 12, 12, 10, 10, 12, 14, 10, 14, 28, 20, 20), 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    col = {}
    for c in ws[1]:
        name = str(c.value or "").strip()
        if name == "Commission 学费金额":
            name = "Commission 金额"
        if name and name not in col:
            col[name] = c.column
    for h in MASTER_HEAD:  # 老表缺的列补在后面
        if h not in col:
            col[h] = ws.max_column + 1
            ws.cell(1, col[h]).value = h
    L = lambda h: openpyxl.utils.get_column_letter(col[h])
    fee_cols = [h for h in ("学期已缴费用", "全日制学生已缴费用", "兼职学生已缴费用", "AP 已缴费用")]
    for r, (row, amount) in enumerate(rows, 2):
        for h, v in row.items():
            if h in col and v not in (None, ""):
                ws.cell(r, col[h]).value = v
        if amount is None:
            continue
        ws.cell(r, col["已缴学费总金额"]).value = "=" + "+".join(f"N({L(h)}{r})" for h in fee_cols)
        ws.cell(r, col["Commission 金额"]).value = amount
        for h in fee_cols + ["已缴学费总金额", "其它", "Commission 金额"]:
            ws.cell(r, col[h]).number_format = MONEY_FMT
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
