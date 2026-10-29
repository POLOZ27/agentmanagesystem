"""本地 AI 模式：服务器上的 llama-server（OpenAI 兼容接口）+ 自建 SearXNG 搜索。

流程：SearXNG 搜索 → 抓取机构官网首页和联系页 → 本地模型整理成 lead。
邮箱和电话只采用网页上真实出现过的，模型猜出来的会被丢掉。
全部请求只在服务器和公开网站之间进行，不经过任何第三方 AI 服务。
"""
import html
import json
import re
from urllib.parse import urljoin, urlparse

import httpx

UA = "Mozilla/5.0 (compatible; JA-AgentPortal/1.0; +https://johnathana.ca)"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
CONTACT_WORDS = ("contact", "kontakt", "contacto", "contato", "contatti", "iletisim", "iletişim", "liên hệ", "lien-he",
                 "ติดต่อ", "문의", "연락", "お問い合わせ", "about", "o-nas", "uber-uns", "quienes", "sobre")
SKIP_DOMAINS = ("facebook.", "instagram.", "linkedin.", "youtube.", "twitter.", "x.com", "wikipedia.", "tripadvisor.",
                "canada.ca", "gov.", "studyinternational", "icef.com", "applyboard", "reddit.", "quora.", "google.")
# 用当地语言再搜一遍，找到只做本地网站的中小机构
LOCAL_QUERY = {
    "cs": "studium střední škola Kanada agentura", "sk": "štúdium stredná škola Kanada agentúra",
    "pl": "liceum w Kanadzie agencja edukacyjna", "hu": "kanadai középiskola tanulás ügynökség",
    "de": "Highschool Kanada Auslandsjahr Agentur", "tr": "Kanada lise eğitimi danışmanlık",
    "ka": "კანადა სკოლა სწავლა სააგენტო", "hy": "Կանադա դպրոց ուսում գործակալություն",
    "es": "agencia estudiar preparatoria en Canadá", "pt": "agência intercâmbio high school Canadá",
    "th": "เรียนต่อมัธยม แคนาดา เอเจนซี่", "vi": "du học trung học Canada công ty tư vấn",
    "ko": "캐나다 조기유학 유학원", "ja": "カナダ 高校留学 エージェント", "it": "agenzia anno all'estero Canada liceo",
    "fr": "agence séjour lycée Canada",
}

LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "is_agency": {"type": "boolean"},
        "agency": {"type": "string"}, "city": {"type": "string"}, "contact": {"type": "string"},
        "role": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"},
        "whatsapp": {"type": "string"}, "size_tier": {"type": "string", "enum": ["A", "B", "C"]},
        "size_evidence": {"type": "string"}, "k12_fit": {"type": "string", "enum": ["Yes", "Likely", "Unclear"]},
        "canada_focus": {"type": "string"}, "notes": {"type": "string"},
    },
    "required": ["is_agency", "agency", "city", "contact", "role", "email", "phone", "whatsapp", "size_tier",
                 "size_evidence", "k12_fit", "canada_focus", "notes"],
}

READ_PROMPT = """You review a website to decide whether it is a study-abroad / education agency in {country} that \
could recruit secondary-school (Grades 8-12) students for a private high school in Vancouver, Canada.
{extra}
Answer ONLY with JSON matching the schema. Rules:
- is_agency=false for schools, universities, blogs, directories, government pages, visa-only firms.
- Copy contact details only from the page text. email must be one of: {emails}. Leave empty if none fits.
- size_tier: A = large, several offices or nationally known; B = established mid-size; C = small/boutique.
- size_evidence: one short English sentence with the evidence (offices, years, staff, partners).
- k12_fit: Yes if the site mentions high school / secondary / exchange year programmes abroad.

WEBSITE: {url}
PAGE TEXT:
{text}"""


def _client():
    return httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True)


def _text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _fetch(c, url, limit=400_000):
    try:
        r = c.get(url)
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return ""
        return r.text[:limit]
    except httpx.HTTPError:
        return ""


def _headers(cfg):
    key = cfg.get("local_api_key")
    return {"Authorization": f"Bearer {key}"} if key else {}


def gpt_ready(cfg):
    return bool(cfg.get("openai_key") and cfg.get("openai_model"))


def chat(cfg, prompt, schema=None, max_tokens=1500, provider="local"):
    """provider=local：服务器上的 llama-server；provider=gpt：OpenAI（只用来读公开网站和翻译模板）。"""
    if provider == "gpt":
        url = (cfg.get("openai_url") or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        body = {"model": cfg["openai_model"], "max_completion_tokens": max_tokens * 4,  # 推理模型要留出思考的额度
                "messages": [{"role": "user", "content": prompt}]}
        headers, timeout = {"Authorization": f"Bearer {cfg['openai_key']}"}, 180
    else:
        url = (cfg.get("local_llm_url") or "http://127.0.0.1:8080/v1").rstrip("/") + "/chat/completions"
        body = {"model": cfg.get("local_model") or "local", "temperature": 0.2, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        # 本地 + GPT 模式下，本地模型太忙（超时）就交给 GPT
        headers, timeout = _headers(cfg), (120 if cfg.get("ai_mode") == "hybrid" else 300)
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
    r = httpx.post(url, json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    if not schema:
        return text
    m = re.search(r"\{.*\}", text, re.S)  # 有的模型会在 JSON 外面加说明文字
    return json.loads(m.group(0) if m else text)


def smart_chat(cfg, prompt, schema=None, max_tokens=1500):
    """本地优先；本地出错或超时，且设置了 GPT，就用 GPT 补上。返回 (结果, 用了哪个)。"""
    try:
        return chat(cfg, prompt, schema, max_tokens), "local"
    except (httpx.HTTPError, ValueError, KeyError):
        if cfg.get("ai_mode") == "hybrid" and gpt_ready(cfg):
            return chat(cfg, prompt, schema, max_tokens, provider="gpt"), "gpt"
        raise


def searx(cfg, query, pages=2):
    base = (cfg.get("searxng_url") or "http://127.0.0.1:8888").rstrip("/")
    out = []
    with _client() as c:
        for p in range(1, pages + 1):
            r = c.get(f"{base}/search", params={"q": query, "format": "json", "pageno": p})
            r.raise_for_status()
            out += r.json().get("results", [])
    return out


def _candidates(cfg, country, lang, extra, n, exclude):
    queries = [f"{country} study abroad agency high school Canada",
               f"{country} education consultant secondary school exchange year Canada"]
    if lang in LOCAL_QUERY:
        queries.append(LOCAL_QUERY[lang])
    if extra:
        queries.append(f"{country} study abroad agency {extra}")
    seen, sites = set(), []
    excl = {e.lower() for e in exclude}
    for q in queries:
        for res in searx(cfg, q):
            u = urlparse(res.get("url", ""))
            dom = u.netloc.lower().removeprefix("www.")
            if not dom or dom in seen or any(s in dom for s in SKIP_DOMAINS):
                continue
            if any(e and (e in (res.get("title") or "").lower()) for e in excl):
                continue
            seen.add(dom)
            sites.append(f"{u.scheme}://{u.netloc}/")
            if len(sites) >= n * 3:
                return sites
    return sites


def _read_site(c, url):
    home = _fetch(c, url)
    if not home:
        return "", set(), set()
    pages = [home]
    links = re.findall(r'href=["\']([^"\'#]+)', home)
    contact = [l for l in links if any(w in l.lower() for w in CONTACT_WORDS)]
    for l in contact[:2]:
        full = urljoin(url, l)
        if urlparse(full).netloc == urlparse(url).netloc:
            pages.append(_fetch(c, full))
    raw = " ".join(pages)
    mailto = set(re.findall(r"mailto:([^\"'?\s>]+)", raw))
    text = _text(raw)
    emails = {e.lower() for e in set(EMAIL_RE.findall(text)) | mailto if not e.lower().endswith((".png", ".jpg", ".webp"))}
    phones = {p.strip() for p in PHONE_RE.findall(text)}
    return text[:7000], emails, phones


def search_agencies(cfg, country, n=10, extra="", exclude=(), lang=None, progress=None):
    leads = []
    sites = _candidates(cfg, country, lang, extra, n, exclude)
    with _client() as c:
        for i, url in enumerate(sites):
            if len(leads) >= n:
                break
            if progress:
                progress(f"正在看 {country} 第 {i + 1}/{len(sites)} 个网站，已找到 {len(leads)} 个")
            text, emails, phones = _read_site(c, url)
            if len(text) < 300:
                continue
            prompt = READ_PROMPT.format(country=country, extra=extra or "", url=url, text=text,
                                        emails=", ".join(sorted(emails)) or "(none on page)")
            try:
                d, used = smart_chat(cfg, prompt, LEAD_SCHEMA)
            except (httpx.HTTPError, ValueError, KeyError):
                continue
            if not d.get("is_agency"):
                continue
            checked = "本地模型" if used == "local" else "GPT（本地模型忙，GPT 补上）"
            # 本地 + GPT 模式：本地模型初筛通过的，再让 GPT 复核一遍（等级、是否做高中、备注更准）
            if used == "local" and cfg.get("ai_mode") == "hybrid" and gpt_ready(cfg):
                try:
                    g = chat(cfg, prompt, LEAD_SCHEMA, provider="gpt")
                    if not g.get("is_agency"):
                        continue
                    d, checked = g, "本地模型初筛 + GPT 复核"
                except (httpx.HTTPError, ValueError, KeyError):
                    checked = "本地模型（GPT 复核失败）"
            if (d.get("email") or "").lower() not in emails:  # 只要网页上真实出现的邮箱
                d["email"] = sorted(emails)[0] if len(emails) == 1 else ""
            if d.get("phone") and not any(re.sub(r"\D", "", d["phone"])[-7:] in re.sub(r"\D", "", p) for p in phones):
                d["phone"] = ""
            d.pop("is_agency", None)
            leads.append({**d, "country": country, "website": url, "source_url": url, "ai_checked": checked})
    return leads


def translate(cfg, subject, body, language):
    schema = {"type": "object", "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
              "required": ["subject", "body"]}
    prompt = (f"Translate this school partnership email into {language}, for education agency owners. "
              f"Natural, professional business tone. Keep '{{name}}', URLs, numbers and university names "
              f"unchanged. Answer only with JSON {{\"subject\":…, \"body\":…}}.\n\nSUBJECT: {subject}\n\n"
              f"BODY:\n{body}")
    # 本地 + GPT 模式：翻译小语种交给 GPT，GPT 不可用时再用本地模型
    if cfg.get("ai_mode") == "hybrid" and gpt_ready(cfg):
        try:
            return chat(cfg, prompt, schema, max_tokens=4000, provider="gpt")
        except (httpx.HTTPError, ValueError, KeyError):
            pass
    return chat(cfg, prompt, schema, max_tokens=4000)


def check(cfg):
    """设置页「测试连接」：返回 (模型说明, 搜索结果条数)。"""
    base = (cfg.get("local_llm_url") or "http://127.0.0.1:8080/v1").rstrip("/")
    r = httpx.get(base + "/models", headers=_headers(cfg), timeout=10)
    r.raise_for_status()
    models = r.json().get("data", [])
    hits = len(searx(cfg, "study abroad agency Prague", pages=1))
    if cfg.get("ai_mode") == "hybrid":
        if not gpt_ready(cfg):
            raise ValueError("本地 + GPT 模式需要填 OpenAI API Key 和模型名")
        chat(cfg, "Reply with OK.", max_tokens=20, provider="gpt")
        return (", ".join(m.get("id", "") for m in models) or "本地模型") + f" + GPT {cfg['openai_model']}", hits
    return ", ".join(m.get("id", "") for m in models) or "（未返回模型名）", hits
