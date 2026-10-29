"""生成演示数据（虚构代理、学生和金额），用于预览和试用，不含任何真实信息。

用法： AGENT_PORTAL_DATA=demo-data python demo_seed.py
主密码 demo-password-123；验证器密钥写在 demo-data/DEMO_TOTP.txt
"""
import datetime as dt
import os
import random

import pyotp

import contracts
import mailer
from app import DATA_DIR, agents_by_id, auto_renewals, send_statement, vault

random.seed(7)
TERMS = ["Sep-Dec Fall 24-25", "Jan-June 24-25", "2025 Summer School", "Sep-Dec Fall 25-26",
         "Jan-Apr Winter 25-26", "May-June Spring 25-26", "2026 Summer School", "Sep-Dec Fall 26-27"]
AGENTS = [  # 名称, 国家, 等级或旧比例, 合同到期, 状态
    ("Maple Bridge Education", "China", [25, 25, 25], "2027-08-31", "活跃"),
    ("Pacific Star Consulting (Lily)", "China", [25, 25, 25], "2026-12-31", "活跃"),
    ("North Harbour Study Centre", "Canada", [30, 30, 30], "2028-10-31", "活跃"),
    ("Lotus Path Immigration", "China", "standard", "2028-11-30", "活跃"),
    ("Evergreen Academy Services", "South Korea", "premier", "2029-01-31", "活跃"),
    ("Sunrise Overseas (Kevin)", "Taiwan", [25, 25, 25], "2026-11-30", "活跃"),
    ("BrightPath Edu", "Vietnam", "standard", "2028-10-31", "活跃"),
    ("Golden Gate Study Abroad", "China", [25, 25, 25], "2027-10-31", "活跃"),
    ("Cedar Learning Group", "Canada", [25, 25, 25], "2026-06-30", "活跃"),
    ("Blue Ocean International (Amy)", "Hong Kong", "standard", "2028-09-30", "活跃"),
    ("Summit Scholars Consulting", "China", [25, 10, 5], "2029-01-31", "活跃"),
    ("Aurora Global Education", "Japan", "standard", "2028-12-31", "活跃"),
    ("Jade River Education", "China", [25, 25, 25], "2025-06-30", "不活跃"),
    ("West Coast Elite", "Canada", [25, 25, 25], "2024-08-31", "不活跃"),
    ("Harmony Study Link", "Malaysia", [25, 25, 25], "2025-10-31", "不活跃"),
    ("Polaris Admissions", "China", [30, 30, 30], "2023-03-31", "不活跃"),
]
FIRST = ["Ethan", "Chloe", "Minh", "Yuna", "Leo", "Grace", "Daniel", "Hana", "Kevin", "Sophie", "Ryan", "Mia",
         "Jason", "Linh", "Alex", "Emma", "Tony", "Iris", "Brian", "Cindy", "Oscar", "Wendy", "Hugo", "Nina"]
LAST = ["Chen", "Nguyen", "Kim", "Wang", "Tran", "Park", "Li", "Sato", "Liu", "Zhao", "Lee", "Ho"]
COURSES = ["MATH 12", "PHYS 12", "ENGL 12", "CHEM 12", "CALC 12", "BIO 11", "AP Calculus", "EFP 10"]
PROSPECTS = [  # 机构, 国家, 城市, 等级, 联系人, 阶段, 规模依据
    ("Vltava Study Abroad s.r.o.", "Czech Republic", "Prague", "A", "Petra Novotná", "已回复", "布拉格和布尔诺两个办公室，每年送出约 150 名学生"),
    ("Moravia Education Partners", "Czech Republic", "Brno", "B", "Jan Dvořák", "已发邮件", "独立办公室，主做英美加高中"),
    ("Tatra Bridge Agency", "Slovakia", "Bratislava", "B", "Lucia Horváthová", "未联系", "做高中交换和私校申请"),
    ("Vistula Global Schools", "Poland", "Warsaw", "A", "Marta Kowalska", "已约会议", "华沙、克拉科夫 3 家分公司"),
    ("Danube Scholars Kft.", "Hungary", "Budapest", "C", "Bence Tóth", "未联系", "个人顾问工作室"),
    ("Alpine Pathways GmbH", "Austria", "Vienna", "B", "Lena Huber", "已发邮件", "专做加拿大寄宿高中"),
    ("Bosphorus Edu Consulting", "Turkey", "Istanbul", "A", "Elif Yılmaz", "已跟进", "伊斯坦布尔、安卡拉、伊兹密尔办公室"),
    ("Anatolia Future Schools", "Turkey", "Ankara", "B", "Mehmet Kaya", "未联系", "高中和夏校为主"),
    ("Kartli Study Centre", "Georgia", "Tbilisi", "B", "Nino Beridze", "已发邮件", "第比利斯本地知名，做英语国家中学"),
    ("Ararat Education Hub", "Armenia", "Yerevan", "C", "Armen Petrosyan", "未联系", "小型机构，有加拿大签证经验"),
    ("Aztlan Intercambios", "Mexico", "Mexico City", "A", "Sofía Hernández", "已跟进", "墨西哥城、蒙特雷 4 个办公室"),
    ("Monterrey Global Ed", "Mexico", "Monterrey", "B", "Diego Garza", "未联系", "主做加拿大高中和语言学校"),
    ("Ipanema Estudos no Exterior", "Brazil", "Rio de Janeiro", "A", "Camila Souza", "已发邮件", "巴西 5 城有办公室"),
    ("Paulista Edu Advisors", "Brazil", "São Paulo", "B", "Rafael Lima", "不合适", "只做大学，不做高中"),
    ("Chao Phraya Education", "Thailand", "Bangkok", "A", "Nattaya S.", "已回复", "曼谷两家门店，年送生 100+"),
    ("Lanna Study Link", "Thailand", "Chiang Mai", "C", "Somchai P.", "未联系", "清迈小型顾问"),
    ("Saigon Bright Future", "Vietnam", "Ho Chi Minh City", "A", "Nguyễn Thu Hà", "已发邮件", "胡志明市、河内办公室"),
    ("Hanoi Pathway Edu", "Vietnam", "Hanoi", "B", "Trần Minh Đức", "未联系", "做加拿大中学 5 年以上"),
    ("Gangnam Global Academy", "South Korea", "Seoul", "A", "Ji-woo Park", "已发邮件", "首尔江南大型留学机构"),
    ("Busan Edu Partners", "South Korea", "Busan", "C", "Min-seo Choi", "未联系", "釜山本地小型机构"),
    ("Sakura Ryugaku Center", "Japan", "Tokyo", "B", "Yuki Tanaka", "已跟进", "东京、大阪两个窗口"),
    ("Kansai Study Abroad", "Japan", "Osaka", "C", "Kenji Mori", "未联系", "以短期游学为主"),
]
REVIEW = [  # AI 搜索结果示例，等待审核
    ("Bohemia Youth Exchange", "Czech Republic", "Plzeň", "B", "Tereza Malá", "官网列出 12 名顾问，做高中交换"),
    ("Cappadocia Lise Danışmanlık", "Turkey", "Izmir", "C", "Ayşe Demir", "两人工作室，Instagram 活跃"),
    ("Bangkok Prep Abroad", "Thailand", "Bangkok", "B", "Kanya R.", "官网有加拿大私立高中案例"),
    ("Tokyo Canada Juku", "Japan", "Tokyo", "A", "Haruto Ito", "年度加拿大高中说明会，合作 30+ 学校"),
]


def money(lo, hi):
    return float(random.randrange(lo, hi, 100))


def student(program, i):
    name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"
    if program.startswith("FT"):
        return {"name": name, "program": program, "courses": "Full-time", "origin": "International",
                "tuition": money(17000, 22000), "note": "", "rate": None}
    if program == "AP":
        return {"name": name, "program": "AP", "courses": "AP Calculus", "origin": "Local",
                "tuition": 2100.0, "note": "", "rate": None}
    return {"name": name, "program": "PT", "courses": ", ".join(random.sample(COURSES[:6], random.randint(1, 2))),
            "origin": random.choice(["Local", "International"]), "tuition": money(1500, 2600), "note": "", "rate": None}


def main():
    secret = pyotp.random_base32()
    vault.initialize("demo-password-123", secret)
    vault.unlock(vault.try_unwrap("demo-password-123"))
    with open(os.path.join(DATA_DIR, "DEMO_TOTP.txt"), "w") as f:
        f.write(secret)
    vault.put("settings", {"id": "mail", "accountant_email": "accounting@example.com"})

    ids = []
    for i, (name, country, scheme, exp, status) in enumerate(AGENTS):
        code = f"J20{20 + i // 3}{i % 3 + 1:02d}"
        slug = name.split()[0].lower()
        lv = scheme if isinstance(scheme, str) else ""
        rates = {"standard": [20, 10, 5], "premier": [25, 10, 5]}.get(lv, scheme)
        a = vault.put("agent", {
            "name": name, "code": code, "country": country, "rates": rates, "level": lv, "status": status,
            "contact": name.split("(")[-1].rstrip(")") if "(" in name else "",
            "email": f"{slug}@example.com", "etransfer": f"pay@{slug}.example.com",
            "payee": name.split(" (")[0] + " Ltd.", "contract_expiry": exp, "source": "演示数据",
            "onboarding": {k: "2024-01-15" for k in ("contact", "meeting", "vetting", "level", "contract", "signed",
                                                      "activate")},
            "contracts": [{"name": f"Service Contract ({name.split(' (')[0]}) {code} until {exp[:7]}.pdf",
                           "expiry": exp, "fid": None, "kind": "已签"}]})
        ids.append((a, status))

    # 历史学期：Excel 导入的汇总记录（已付）
    for order, term in enumerate(TERMS[:6]):
        for a, status in ids:
            if status != "活跃" and order > 2 or random.random() < 0.45:
                continue
            rec = {"agent_id": a["id"], "term": term, "term_order": order, "status": "已付",
                   "paid_on": "2026-0%d-15" % (1 + order % 9)}
            if random.random() < 0.7:
                n = random.randint(1, 3)
                rec.update(stu_y1=f"{n} Inter", fee_y1=money(9000, 14000) * n)
            if random.random() < 0.6:
                n = random.randint(1, 6)
                rec.update(stu_pt=f"{n} Inter", fee_pt=money(1500, 2500) * n)
            if any(k.startswith("fee_") for k in rec):
                vault.put("commission", rec)

    # 最近两个学期：逐个学生的结算单，分布在流程的各个阶段
    agents = agents_by_id()
    n = 0
    box = mailer.Outbox(vault)
    plan = [  # (代理序号, 学期序号, 阶段, 学生类别)
        (0, 6, "已付", ["PT", "PT", "FT1"]), (3, 6, "已付", ["FT1", "PT"]), (10, 6, "已交会计", ["FT2", "PT", "PT"]),
        (1, 7, "已发结算单", ["PT", "PT"]), (2, 7, "代理已确认", ["FT1", "PT", "AP"]), (4, 7, "草稿", ["FT1", "FT1", "PT"]),
        (5, 7, "草稿", ["PT"]), (7, 7, "已交会计", ["PT", "PT", "PT"]), (9, 7, "草稿", ["FT1", "PT"]),
        (11, 7, "已发结算单", ["FT1"]), (0, 7, "草稿", ["PT", "AP"]),
    ]
    for idx, t, stage, progs in plan:
        a = ids[idx][0]
        studs = []
        for p in progs:
            studs.append(student(p, n))
            n += 1
        c = vault.put("commission", {"agent_id": a["id"], "term": TERMS[t], "term_order": t, "status": "草稿",
                                     "students": studs})
        if stage != "草稿":
            send_statement(c, agents, box)
            c = vault.get("commission", c["id"])
            c["sent_on"] = "2026-10-0%d" % (2 + t % 5)
        if stage in ("代理已确认", "已交会计", "已付"):
            inv = {"name": f"Invoice {a['code']} {TERMS[t]}.pdf", "fid": vault.put_file(b"%PDF-1.4 demo invoice"),
                   "uploaded": "2026-10-10"}
            vault.put("mail", {"direction": "in", "agent_id": a["id"], "from": a["email"],
                               "subject": f"Re: JA Commission Records for {TERMS[t]}", "attachments": [inv],
                               "body": "Dear Polo,\n\nWe have checked the records and confirm. Please find our invoice attached.\n\nBest regards",
                               "at": "2026-10-10T11:20", "status": "已读"})
            c.update(status="代理已确认", confirmed_on="2026-10-10", invoice=inv)
        if stage in ("已交会计", "已付"):
            c.update(status="已交会计", to_accountant_on="2026-10-12",
                     pay_method="E-Transfer" if a.get("etransfer") else "Cheque")
        if stage == "已付":
            c.update(status="已付", paid_on="2026-10-18", pay_ref="ET-2026-1018")
        vault.put("commission", c)
    # 一个代理已经确认、但发票还在收件箱里没登记
    a = ids[1][0]
    vault.put("mail", {"direction": "in", "agent_id": a["id"], "from": a["email"],
                       "subject": "Re: JA Commission Records for Sep-Dec Fall 26-27",
                       "attachments": [{"name": "Invoice PSC-2026-11.pdf", "fid": vault.put_file(b"%PDF-1.4 demo")}],
                       "body": "Hi Polo,\n\nAll correct, invoice attached.\n\nLily", "at": "2026-10-24T15:02",
                       "status": "未读"})

    # 学年满 6 人补差示例：BrightPath（标准级）25-26 学年前两张单按 20% 发出，第三张满 6 人，改按 25% 并补差
    bp = ids[6][0]
    for t, progs, stage in [(3, ["FT1", "FT1", "FT1"], "已付"), (4, ["FT1", "PT"], "已付"), (6, ["FT1", "FT1"], "草稿")]:
        studs = [student(p, n + i) for i, p in enumerate(progs)]
        n += len(progs)
        c = vault.put("commission", {"agent_id": bp["id"], "term": TERMS[t], "term_order": t, "status": "草稿",
                                     "students": studs, "notes": "演示：满 6 人补差"})
        if stage == "已付":
            send_statement(c, agents, box)
            c = vault.get("commission", c["id"])
            c.update(status="已付", sent_on="2026-01-10", confirmed_on="2026-01-15", to_accountant_on="2026-01-16",
                     paid_on="2026-01-30", pay_method="E-Transfer")
            vault.put("commission", c)

    # 新代理入驻：处在不同步骤
    today = dt.date.today()
    rio = vault.put("agent", {"name": "Rio Andes Educação (Mariana)", "code": "", "country": "Brazil",
                              "contact": "Mariana Costa", "status": "洽谈中", "level": "standard", "rates": [20, 10, 5],
                              "email": "mariana@example.com", "source": "开发新代理", "contracts": [],
                              "onboarding": {"contact": "2026-09-28", "meeting": "2026-10-08", "vetting": "2026-10-20"}})
    vault.put("agent", {"name": "Lima Futuro Consultores", "code": "", "country": "Peru", "status": "潜在",
                        "contact": "Carlos Ruiz", "level": "standard", "rates": [20, 10, 5],
                        "email": "info@limafuturo.example.com", "source": "Agent Tracker", "contracts": [],
                        "onboarding": {"contact": "2026-10-15"}})
    praha = {"name": "Praha Bridge Education", "legal_name": "Praha Bridge Education s.r.o.", "code": "J202604",
             "country": "Czech Republic", "city": "Prague", "address": "Vinohradská 12, 120 00 Praha 2, Czech Republic",
             "website": "www.prahabridge.example.com", "contact": "Tomáš Svoboda", "phone": "+420 600 000 000",
             "email": "tomas@prahabridge.example.com", "status": "洽谈中", "level": "premier", "rates": [25, 10, 5],
             "source": "开发新代理", "payee": "Praha Bridge Education s.r.o.", "etransfer": "",
             "onboarding": {"contact": "2026-09-10", "meeting": "2026-09-18", "vetting": "2026-10-02",
                            "level": "2026-10-05", "contract": "2026-10-06"}}
    start, end = contracts.default_period()
    fname, data = contracts.generate(praha, "premier", start, end)
    praha["contracts"] = [{"name": fname, "fid": vault.put_file(data), "expiry": end.isoformat(),
                           "uploaded": "2026-10-06", "kind": "待签（系统生成）"}]
    praha = vault.put("agent", praha)
    box.send(praha["email"], "Welcome to Johnathan Academy – Agency Agreement", "Dear Tomáš,\n\n（演示：Start Letter）",
             [(fname, data)], agent_id=praha["id"])
    vault.put("agent", {"name": "Marmara Study Abroad", "code": "J202605", "country": "Turkey", "city": "Istanbul",
                              "contact": "Can Öztürk", "email": "can@marmara.example.com", "status": "已签约",
                              "level": "standard", "rates": [20, 10, 5], "source": "开发新代理",
                              "contract_expiry": end.isoformat(),
                              "contracts": [{"name": f"Service Contract (Marmara Study Abroad) J202605 until {end:%Y %b} (signed).pdf",
                                             "fid": vault.put_file(b"%PDF-1.4 demo signed"), "expiry": end.isoformat(),
                                             "uploaded": "2026-10-21", "kind": "已签"}],
                              "onboarding": {"contact": "2026-08-20", "meeting": "2026-08-29", "vetting": "2026-09-12",
                                             "level": "2026-09-15", "contract": "2026-09-16", "signed": "2026-10-21"}})

    # 潜在代理（开发中）
    for i, (agency, country, city, tier, contact, stage, ev) in enumerate(PROSPECTS):
        slug = agency.split()[0].lower().replace("ı", "i")
        sent = {"未联系": 0, "已发邮件": 1, "已跟进": 2, "已回复": 1, "已约会议": 2, "不合适": 1}[stage]
        last = (today - dt.timedelta(days=3 + i % 12)).isoformat() if sent else None
        p = vault.put("prospect", {"agency": agency, "country": country, "city": city, "tier": tier, "contact": contact,
                                   "email": f"info@{slug}.example.com", "website": f"https://www.{slug}.example.com",
                                   "stage": stage, "size_evidence": ev, "k12_fit": "做 Grade 8–12 / 高中留学",
                                   "source": "AI 搜索（示例）" if i % 3 == 0 else "Agent Tracker 导入",
                                   "emails_sent": sent, "first_email_on": last, "last_email_on": last})
        if sent:
            vault.put("mail", {"direction": "out", "prospect_id": p["id"], "to": p["email"],
                               "subject": "Vancouver Grade 8–12 School Partnership | 1,900+ University Offers",
                               "body": "Dear …（演示）", "at": f"{last}T09:30", "status": "已发送"})
        if stage == "已回复":
            vault.put("mail", {"direction": "in", "prospect_id": p["id"], "from": p["email"],
                               "subject": "Re: Vancouver Grade 8–12 School Partnership",
                               "body": f"Dear Polo,\n\nThank you for reaching out. We would be interested in learning more. Could you send your agency terms?\n\n{contact}",
                               "at": f"{today.isoformat()}T08:15", "status": "未读"})
    for agency, country, city, tier, contact, ev in REVIEW:
        slug = agency.split()[0].lower()
        vault.put("prospect", {"agency": agency, "country": country, "city": city, "tier": tier, "contact": contact,
                               "email": f"hello@{slug}.example.com", "website": f"https://{slug}.example.com",
                               "size_evidence": ev, "k12_fit": "官网提到高中留学", "stage": "待审核",
                               "source_url": f"https://{slug}.example.com/about", "source": "AI 搜索（示例）"})
    vault.put("ai_job", {"countries": ["Czech Republic", "Turkey", "Thailand", "Japan"], "n": 5, "status": "完成",
                         "progress": "找到 4 个，等待你审核（示例）", "started": f"{today.isoformat()}T09:00"})

    vault.put("campaign", {"subject": "Johnathan Academy 每月动态 | {代理名称}", "body": "…", "audience": "活跃代理",
                           "cadence": "每月", "active": True, "next_at": "2026-11-02T09:00",
                           "last_at": "2026-10-01T09:00", "last_count": 12})
    vault.put("campaign", {"subject": "2027 冬季入学截止提醒", "body": "…", "audience": "全部代理",
                           "cadence": "仅一次（定时）", "active": True, "next_at": "2026-11-15T10:00"})
    vault.put("mail", {"direction": "in", "agent_id": rio["id"], "from": rio["email"], "subject": "Application form + references",
                       "body": "Hi Polo,\n\nAttached is our agency application form.\n\nMariana", "at": "2026-10-19T13:40",
                       "status": "已读"})
    for a, status in ids[:12]:
        vault.put("mail", {"direction": "out", "agent_id": a["id"], "to": a["email"],
                           "subject": f"Johnathan Academy 每月动态 | {a['name']}", "body": "Dear …",
                           "at": "2026-10-01T09:00", "status": "已发送", "campaign_id": None})
    # 加拿大本地代理（T4A 示例）：一个个人有 SIN，一个个人缺 SIN，其余为公司
    for a, _ in ids:
        if a["name"] == "North Harbour Study Centre":
            a.update(entity_type="individual", payee="Daniel Wong", tax_number="000 000 000（演示）",
                     address="100 Example Rd", city="Richmond, BC V6X 0A0", contact="Daniel Wong")
        elif a["name"] == "Cedar Learning Group":
            a.update(entity_type="individual", payee="Grace Liu", contact="Grace Liu", contract_expiry="2026-12-15")
            a["contracts"][0]["expiry"] = "2026-12-15"
        vault.put("agent", a)

    # 学生申请进度
    stages = ["收到申请", "资料齐全", "已发录取信", "已缴学费", "学签获批", "已入学", "未入学"]
    plan = [(0, "FT1", 0), (0, "FT1", 2), (3, "FT1", 3), (4, "FT1", 1), (4, "FT1", 4), (4, "PT", 5), (6, "FT1", 2),
            (6, "FT1", 3), (9, "FT1", 0), (9, "AP", 5), (11, "FT1", 4), (11, "FT1", 1), (2, "PT", 5), (2, "FT1", 6),
            (7, "PT", 2), (1, "FT1", 3), (5, "FT1", 0), (10, "FT2", 5)]
    countries = ["China", "Vietnam", "South Korea", "Japan", "Taiwan", "Hong Kong", "Mexico"]
    for i, (ai, prog, k) in enumerate(plan):
        a = ids[ai][0]
        st = stages[k]
        hist = {stages[j]: (today - dt.timedelta(days=40 - j * 6 - i % 4)).isoformat() for j in range(min(k, 5) + 1)}
        hist[st] = (today - dt.timedelta(days=i % 9)).isoformat()
        enrolled = st == "已入学"
        vault.put("student", {"name": f"{FIRST[(i * 5 + 3) % len(FIRST)]} {LAST[(i * 3 + 1) % len(LAST)]}", "agent_id": a["id"],
                              "program": prog, "grade": str(9 + i % 4), "country": countries[i % len(countries)],
                              "intake": "Sep-Dec Fall 26-27" if enrolled or k == 6 else "Jan-Apr Winter 26-27",
                              "origin": "International", "courses": "Full-time" if prog.startswith("FT") else "MATH 12",
                              "tuition": 19800.0 if prog.startswith("FT") else (2100.0 if prog == "AP" else 1800.0),
                              "stage": st, "history": hist, "notes": "演示数据"})

    # 宣传资料库（演示用虚构链接）
    for title, kind, lang, share in [("合作伙伴资料包（共享文件夹）", "资料包", "中英", True), ("学校 Flyer（英文）", "传单", "英文", True),
                                     ("学校 Flyer（中文）", "传单", "中文", True), ("学校画册（英文）", "宣传册", "英文", True),
                                     ("学校介绍 PPT（中文）", "PPT", "中文", True), ("Admission Application Form", "申请表", "英文", True),
                                     ("校园照片", "照片", "", False)]:
        vault.put("asset", {"title": title, "kind": kind, "lang": lang, "share": share, "updated": today.isoformat(),
                            "url": f"https://example.com/ja-kit/{kind}-{len(title)}", "note": "演示链接"})
    vault.put("asset", {"title": "学校日历 2026-27", "kind": "校历", "lang": "英文", "share": True, "url": "",
                        "note": "演示：还没有共享链接", "updated": today.isoformat()})

    # 到期前 90 天自动准备续签合同
    auto_renewals()
    print("demo ready:", len(vault.all("agent")), "agents,", len(vault.all("commission")), "statements,",
          len(vault.all("prospect")), "prospects")


if __name__ == "__main__":
    main()
