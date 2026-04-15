"""Store extracted facts in MemPalace: one category per room, upsert by category+label."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

from mempalace.miner import detect_hall
from mempalace.palace import NORMALIZE_VERSION, get_collection


def normalize_category(name: str) -> str:
    s = (name or "general").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-") or "general"
    return s[:64]


def format_fact_line(label: str | None, value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    lab = (label or "").strip()
    if lab:
        return f"{lab}: {v}"
    return v


def stable_drawer_id(wing: str, room: str, label_key: str) -> str:
    digest = hashlib.sha256(f"{wing}|{room}|{label_key}".encode()).hexdigest()[:24]
    return f"drawer_{wing}_{room}_{digest}"


def upsert_journal_fact(
    palace_path: str,
    wing: str,
    category: str,
    label: str | None,
    value: str,
    agent: str,
) -> None:
    room = normalize_category(category)
    line = format_fact_line(label, value)
    if not line:
        return
    lab_stripped = (label or "").strip()
    if lab_stripped:
        label_key = lab_stripped.lower()
    else:
        # Avoid collapsing multiple unlabeled facts in the same category.
        label_key = "v-" + hashlib.sha256(value.encode()).hexdigest()[:16]
    drawer_id = stable_drawer_id(wing, room, label_key)
    source_file = str(Path(palace_path).resolve() / "_journal_facts" / f"{room}.md")

    collection = get_collection(palace_path, create=True)
    metadata: dict = {
        "wing": wing,
        "room": room,
        "source_file": source_file,
        "chunk_index": 0,
        "added_by": agent,
        "filed_at": datetime.now().isoformat(),
        "normalize_version": NORMALIZE_VERSION,
        "hall": detect_hall(line),
    }
    try:
        metadata["source_mtime"] = os.path.getmtime(source_file)
    except OSError:
        pass

    collection.upsert(
        documents=[line],
        ids=[drawer_id],
        metadatas=[metadata],
    )


def save_extracted_facts(
    palace_path: str,
    wing: str,
    facts: list[dict],
    agent: str,
) -> None:
    for f in facts:
        upsert_journal_fact(
            palace_path,
            wing,
            f.get("category") or "general",
            f.get("label") or "",
            f.get("value") or "",
            agent,
        )
