"""常用邮件模板（来自 Agent\\Template Docs，可在这里直接改字）。"""
import re

COMMISSION_STATEMENT = {
    "subject": "JA Commission Records for {term}",
    "body": """Dear {agent},

I trust this email finds you well.

As we continue to nurture our fruitful collaboration, I am writing to share with you the commission records for students enrolled at Johnathan Academy through your esteemed agency for the period of {term}.

Commission total: {amount}
(Details are in the attached statement.)

We would greatly appreciate it if you could review and confirm these records at your earliest convenience. Please do not hesitate to reach out if you have any questions or require further clarification on any aspects of the document.

I also want to express our sincere gratitude for your continued cooperation and hard work. The success of our students is a testament to the strong partnership we have formed, and we look forward to many more years of collaborative achievement.

Thank you once again for your valued partnership. We eagerly await your confirmation of the commission records. If everything is correct, please send us the invoice for the corresponding amount.

Best Regards,
Polo Zhang
Johnathan Academy""",
}

# 发 Student Roster（以前所有学期 + 本学期新工作表）时用：Agent\Template Docs\Service Commission Email.docx 原文
COMMISSION_ROSTER = {
    "subject": "JA Commission Records for {term}",
    "body": """Dear {agent},

I trust this email finds you well.

As we continue to nurture our fruitful collaboration, I am writing to share with you the commission records for students enrolled at Johnathan Academy through your esteemed agency for the period of {term}.

We would greatly appreciate it if you could review and confirm these records at your earliest convenience. Please do not hesitate to reach out if you have any questions or require further clarification on any aspects of the document.

I also want to express our sincere gratitude for your continued cooperation and hard work. The success of our students is a testament to the strong partnership we have formed, and we look forward to many more years of collaborative achievement.

Thank you once again for your valued partnership. We eagerly await your confirmation of the commission records. If everything is correct, please send us the invoice for the corresponding amount.

Best Regards,
Polo Zhang
Johnathan Academy""",
}

ACCOUNTANT = {
    "subject": "Commission payment request – {agent} ({code}) – {term} – {amount}",
    "body": """Hi,

Please process the following agent commission payment. The agent has confirmed the statement; their invoice is attached.

Agent: {agent} ({code})
Term: {term}
Amount: {amount}
Payment method: {method}
Payee / cheque title: {payee}
E-Transfer: {etransfer}
Bank details: {bank}

Please reply with the cheque or e-transfer confirmation once paid.

Thank you,
Polo""",
}

PAYMENT_NOTICE = {
    "subject": "Commission paid – {term} – {amount}",
    "body": """Dear {agent},

We are pleased to let you know that the commission for {term} ({amount}) has been paid by {method} on {date}.

Thank you for your continued partnership.

Best Regards,
Polo Zhang
Johnathan Academy""",
}

START_LETTER = {
    "subject": "Excited to Begin Our Collaboration Between Johnathan Academy and {agent}",
    "body": """Dear {contact},

I am writing to express our enthusiasm for initiating a collaboration between Johnathan Academy and {agent}. We believe that by combining our resources and expertise, we can significantly enhance our student recruitment efforts and create a mutually beneficial partnership.

In the meantime, here is a brief overview of Johnathan Academy and our programs for your review: {kit_link} – it should offer you a better understanding of our educational offerings and areas of focus.

You are also welcome to visit our website at www.johnathana.ca or our WeChat Official Account, "JohnathanAcademy", for more information about our institution.

The collaboration agreement has been added to the attachment. Kindly review and confirm that everything is in order, then sign the document and complete Schedule A (banking details). Once you have signed the agreement, please scan the signed document and attach it in reply to this email.

We are excited about the prospect of working together and look forward to establishing a productive and long-lasting partnership with you and your team. Please feel free to reach out if you have any questions or need additional information.

Best Wishes,
Polo Zhang
Johnathan Academy""",
}

RENEW_LETTER = {
    "subject": "RE: Service Contract Renewal with Johnathan Academy",
    "body": """Dear {contact},

Firstly, on behalf of Johnathan Academy staff and management, I wish to thank you for your rigorous efforts in recruiting students and promoting our school. We believe your endeavors have been a resounding success, as the quality and character of our students have been exceptional.

At this juncture, it is our aspiration to offer you a Contract Renewal. Please see the attached document and return it signed to our Office. The new agreement runs from {start} to {end}.

In the meantime, here is a brief overview of Johnathan Academy and our programs for your review: {kit_link} – it should offer you a better understanding of our educational offerings and areas of focus.

You are also welcome to visit our website at www.johnathana.ca or our WeChat Official Account, "Johnathan Academy", for more information about our institution.

Our goal for the future is the continuation and cultivation of an effective rapport between yourself and our school.

Once again, thank you for your diligence, and we look forward to continuing our association.

Sincerely,
Polo Zhang
Johnathan Academy""",
}

ANNUAL_STATEMENT = {
    "subject": "Johnathan Academy – {year} annual commission payment summary – {agent}",
    "body": """Dear {contact},

Please find attached a summary of the commission payments Johnathan Academy made to {agent} in {year}.

Total paid in {year}: {amount}
{t4a_line}
If anything does not match your records, please let us know.

Best Regards,
Polo Zhang
Johnathan Academy""",
}

LOGIN_CODE = {
    "subject": "Johnathan Academy agent portal – your sign-in code",
    "body": """Your sign-in code is {code}

It is valid for 10 minutes. If you did not request it, you can ignore this email.

Johnathan Academy""",
}

WELCOME = {
    "subject": "Welcome to the Johnathan Academy Agent Network – Agent No. {code}",
    "body": """Dear {contact},

Thank you for returning the signed agreement. Welcome to the Johnathan Academy agent network!

Your agent number is {code}. Please include it on every student application and commission request so that each student is credited to your agency.

How to work with us:
1. Send us the student's completed application form and supporting documents (passport / study permit or PR card, previous 2 years' transcripts, MSP card, guardianship declaration if under 19).
2. Help the student complete tuition payment and let us know.
3. At the end of each term we will email you a commission statement. Please review it and reply with your invoice; payment follows once our accountant has processed it.

You will also receive our monthly Johnathan Academy updates with admissions dates, programs and student news.

We look forward to a long and successful partnership.

Best Regards,
Polo Zhang
Johnathan Academy""",
}


def fill(tpl, **kw):
    out = dict(tpl)
    if not kw.get("kit_link"):  # 没有资料链接时，去掉提到链接的那一句
        out["body"] = re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in out["body"].split("\n") if "{kit_link}" not in l))
    for k in ("subject", "body"):
        for key, val in kw.items():
            out[k] = out[k].replace("{" + key + "}", str(val if val is not None else ""))
    return out
