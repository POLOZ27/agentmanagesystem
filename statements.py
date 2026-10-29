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
