"""List and delete MemPalace drawer records (categorized by wing / room metadata)."""

from __future__ import annotations

from mempalace.palace import get_collection


def list_drawer_items(
    palace_path: str, *, limit: int = 100, offset: int = 0
) -> tuple[list[dict], int]:
    col = get_collection(palace_path, create=True)
    total = col.count()
    cap = min(2000, max(total, 1))
    # Chroma: `ids` is returned by default and must not appear in `include`.
    res = col.get(include=["documents", "metadatas"], limit=cap)
    ids = res.get("ids") or []
    docs = res.get("documents") or []
    metas = res.get("metadatas") or []

    items: list[dict] = []
    for i, did in enumerate(ids):
        doc = docs[i] if i < len(docs) else ""
        meta = metas[i] if i < len(metas) and metas[i] else {}
        raw = doc or ""
        preview = raw[:280].replace("\n", " ").strip()
        if len(raw) > 280:
            preview += "…"
        items.append(
            {
                "drawer_id": did,
                "wing": (meta.get("wing") if meta else None) or "—",
                "room": (meta.get("room") if meta else None) or "—",
                "hall": (meta.get("hall") if meta else None) or None,
                "preview": preview or "(empty)",
                "text": raw,
                "source_file": (meta.get("source_file") if meta else None) or None,
                "filed_at": (meta.get("filed_at") if meta else None) or None,
                "added_by": (meta.get("added_by") if meta else None) or None,
            }
        )

    items.sort(key=lambda x: x.get("filed_at") or "", reverse=True)
    return items[offset : offset + limit], total


def delete_drawer(palace_path: str, drawer_id: str) -> bool:
    if not drawer_id or not drawer_id.strip():
        return False
    col = get_collection(palace_path, create=True)
    existing = col.get(ids=[drawer_id.strip()], include=["metadatas"])
    if not existing.get("ids"):
        return False
    col.delete(ids=[drawer_id.strip()])
    return True
