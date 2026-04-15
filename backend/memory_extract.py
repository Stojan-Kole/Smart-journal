"""Extract key journal facts via Ollama (structured JSON) — not full-sentence storage."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("smart_journal")

_EXTRACTION_SYSTEM = """You extract only durable, retrievable facts worth remembering from a journal message.
Respond with JSON exactly in this shape: {"facts": [{"category": "...", "label": "...", "value": "..."}]}

Rules:
- category: short English topic for grouping (e.g. cars, food, family, work, health, preferences, places). Use lowercase; one word or hyphenated (e.g. favourite-things).
- label: short tag for the type of fact (e.g. "favourite car", "brother's name"). Use English when possible. Use "" if a single standalone fact with no sub-type.
- value: the concise fact only — no "remember", no narrative wrapping, no repeating the label unnecessarily.
- One object per distinct fact; merge duplicates in your head into one.
- If the message is small talk, only questions, or nothing worth long-term recall, return {"facts": []}.
- Do not invent facts; only what the user clearly stated."""


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
            {"role": "user", "content": text},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 1024},
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
