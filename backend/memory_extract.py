"""Extract key journal facts via Ollama (structured JSON) — not full-sentence storage."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("smart_journal")

_EXTRACTION_SYSTEM = """You extract durable personal facts from ONE journal message for long-term memory.
Return JSON only, exactly: {"facts": [{"category": "...", "label": "...", "value": "..."}]}

Priority when several things appear — extract higher-priority facts first and do not drop them in favour of weaker lines:
1) Identity: the user's name as they state it (first name or full name).
2) Origin / location: city, country, or region they say they are from or live in.
3) Family, work, health, stable preferences, important dates, concrete preferences (e.g. favourite X).

Skip (do not put in facts):
- Questions to the assistant (e.g. "what can you do?", "can you help?").
- Pure greetings with no factual content.
- Meta-comments about this chat app, "trying a new diary tool", or "a new way to journal" unless the user clearly states it as a lasting preference worth recalling. Never prefer such meta over name or place when both appear.

If the user gives name AND location in the same message, you MUST output separate fact objects for both.

category: lowercase English slug — identity, location, family, work, health, preferences, places, cars, food, general, etc.
label: short English tag — e.g. "given name", "city of origin", "favourite car". Use "" only for a single standalone value.
value: the fact alone, concise; keep names and place names exactly as stated.

One JSON object per distinct fact. If nothing durable remains after the rules above, return {"facts": []}.
Do not invent or infer facts not clearly stated."""


def _parse_facts_json(raw: str) -> list[dict]:
    raw = raw.strip()
    if not raw:
        return []
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        return []
    facts = data.get("facts")
    if not isinstance(facts, list):
        return []
    out: list[dict] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        cat = item.get("category")
        val = item.get("value")
        if not isinstance(cat, str) or not isinstance(val, str):
            continue
        cat, val = cat.strip(), val.strip()
        if not val:
            continue
        if not cat:
            cat = "general"
        lab = item.get("label")
        label = lab.strip() if isinstance(lab, str) else ""
        out.append({"category": cat, "label": label, "value": val})
    return out


def extract_key_facts(user_text: str, ollama_base: str, model: str) -> list[dict]:
    """
    Returns a list of {"category", "label", "value"} for MemPalace storage.
    On any failure, returns [] (caller should not break the chat flow).
    """
    text = user_text.strip()
    if not text:
        return []

    url = urljoin(ollama_base + "/", "api/chat")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Extract facts from this journal line only "
                    "(apply priority: name and place before app-related meta):\n\n"
                    + text
                ),
            },
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.15, "num_predict": 1536},
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            r = client.post(url, json=payload)
    except httpx.ConnectError:
        logger.warning("Ollama unreachable for fact extraction; skipping MemPalace facts")
        return []

    if r.status_code != 200:
        logger.warning("Ollama fact extraction HTTP %s: %s", r.status_code, r.text[:200])
        return []

    try:
        data = r.json()
    except ValueError:
        return []

    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        return []

    try:
        return _parse_facts_json(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Fact extraction JSON parse failed: %s", e)
        return []
