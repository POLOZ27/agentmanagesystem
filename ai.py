"""AI 功能：联网搜索目标国家的留学代理、翻译邮件。

两种模式（在「设置与安全」里选）：
- local：服务器上的 llama-server + SearXNG（见 local_ai.py），不用任何外部 AI 服务
- claude：Claude API + 联网搜索（需要 API Key，加密保存在保险库）
发出去的只有搜索条件（国家、要求）和要翻译的邮件模板，不会发送任何代理、学生或佣金数据。
"""
import json

import anthropic

import local_ai

MODEL = "claude-opus-5-5"

LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "leads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agency": {"type": "string"},
                    "country": {"type": "string"},
                    "city": {"type": "string"},
                    "contact": {"type": "string", "description": "Named senior person if public, else empty"},
                    "role": {"type": "string"},
                    "email": {"type": "string", "description": "Public email only; empty if none"},
                    "phone": {"type": "string"},
                    "whatsapp": {"type": "string"},
                    "website": {"type": "string"},
                    "size_tier": {"type": "string", "enum": ["A", "B", "C"],
                                  "description": "A = large/multi-office or well-known; B = established mid-size; C = small/boutique"},
                    "size_evidence": {"type": "string", "description": "Why this tier: offices, staff, years, memberships"},
                    "k12_fit": {"type": "string", "enum": ["Yes", "Likely", "Unclear"],
                                "description": "Does the agency send students to Canadian / overseas high schools (Grades 8-12)?"},
                    "canada_focus": {"type": "string"},
                    "source_url": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["agency", "country", "city", "contact", "role", "email", "phone", "whatsapp", "website",
                             "size_tier", "size_evidence", "k12_fit", "canada_focus", "source_url", "notes"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["leads"],
    "additionalProperties": False,
}

SEARCH_PROMPT = """You are researching international student recruitment agencies for Johnathan Academy, \
an independent Grade 8–12 secondary school in Vancouver, Canada (BC curriculum, Dogwood Diploma, AP).

Find up to {n} real, currently operating education / study-abroad agencies in {country} that recruit \
secondary-school (high school, Grades 8–12) students for Canada or other English-speaking countries.
{extra}
Rules:
- Only include agencies you verified on their own website or a reputable directory (ICEF, BELTA, \
national associations, Canadian school agent lists). Put that page in source_url.
- Only copy contact details that are publicly published. Never guess an email address; leave it empty instead.
- Prefer partnership or institutional emails, and a named director/owner where public.
- Grade size_tier: A = large, multi-office or well-known nationally; B = established mid-size; C = small or boutique.
- Skip these agencies, which we already have: {exclude}
"""


def client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def _create(c, **kw):
    return c.beta.messages.create(model=MODEL, betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)


def claude_search(api_key, country, n=10, extra="", exclude=()):
    """返回 lead 字典列表。联网搜索需要几分钟。"""
    c = client(api_key)
    prompt = SEARCH_PROMPT.format(n=n, country=country, extra=extra or "",
                                  exclude=", ".join(sorted(exclude)[:200]) or "none")
    messages = [{"role": "user", "content": prompt}]
    for _ in range(6):  # 服务器端搜索轮次上限后会 pause_turn，接着继续
        resp = _create(c, max_tokens=16000, messages=messages,
                       tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 25}],
                       output_config={"effort": "high", "format": {"type": "json_schema", "schema": LEAD_SCHEMA}})
        if resp.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        if resp.stop_reason == "refusal":
            raise RuntimeError("AI 拒绝了这次搜索请求")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text).get("leads", [])
    raise RuntimeError("搜索没有在规定轮次内完成，请减少数量后重试")


def claude_translate(api_key, subject, body, language):
    """把英文开发邮件翻译成目标语言，保留占位符 {name} 和链接。"""
    c = client(api_key)
    schema = {"type": "object", "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
              "required": ["subject", "body"], "additionalProperties": False}
    resp = _create(c, max_tokens=8000, output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                   messages=[{"role": "user", "content":
                              f"Translate this school partnership email into {language}, for a business audience "
                              f"(education agency owners). Keep it natural and professional. Keep '{{name}}', URLs, "
                              f"numbers and university names unchanged.\n\nSUBJECT: {subject}\n\nBODY:\n{body}"}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("AI 拒绝了这次翻译请求")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def mode(cfg):
    m = cfg.get("ai_mode") or ("claude" if cfg.get("anthropic_key") else "local")
    return m if m in ("local", "hybrid", "claude") else "local"


def available(cfg):
    if mode(cfg) == "claude":
        return bool(cfg.get("anthropic_key"))
    return bool(cfg.get("local_llm_url") and cfg.get("searxng_url"))


def search_agencies(cfg, country, n=10, extra="", exclude=(), lang=None, progress=None):
    if mode(cfg) == "claude":
        return claude_search(cfg["anthropic_key"], country, n, extra, exclude)
    return local_ai.search_agencies(cfg, country, n, extra, exclude, lang, progress)


def translate(cfg, subject, body, language):
    if mode(cfg) == "claude":
        return claude_translate(cfg["anthropic_key"], subject, body, language)
    return local_ai.translate(cfg, subject, body, language)
