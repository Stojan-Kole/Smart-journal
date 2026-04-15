# MemPalace — findings from Smart Journal (business & technical)

This document summarizes what we learned while integrating **[MemPalace](https://pypi.org/project/mempalace/)** (Chroma-backed memory) into Smart Journal: product choices, pitfalls, and how this repo implements them.

---

## Business / product

### Why MemPalace here

- **Local-first memory** — Data lives under `backend/data/palace/` (Chroma). Together with **Ollama**, the stack avoids paid cloud APIs for both chat and memory.
- **Structured “filing” metaphor** — MemPalace uses **wing → room → hall** metadata. That maps well to user mental models: one wing for the app, **room = topic category** (e.g. `cars`, `identity`, `location`), **hall** adds a secondary tag (often keyword-derived) for richer retrieval and browsing.

### What we store (and what we stopped storing)

- **We do not store full journal lines verbatim** in MemPalace anymore. That produced noisy retrieval and poor signal-to-noise.
- **We store short, extracted facts** — One line per fact, e.g. `given name: Stojan`, `city of origin: Belgrade`, `favourite car: Mercedes Benz W 123`.
- **Extraction is LLM-based** (second Ollama call per user message) with **priority rules**: identity and location before vague meta (“trying a new diary app”). Questions to the assistant are skipped.
- **Trade-off**: Two Ollama calls per message (reply + extraction) → higher latency and CPU use; extraction failures are logged and **do not** break chat.

### User control

- **Opt-in retrieval** — `use_memory` defaults to `false`. MemPalace search runs only when the user enables “Use past memories” for that turn.
- **Memory library UI** — List stored items with wing / room / hall, preview, delete. Lets users audit and remove bad extractions.
- **Journal vs memory** — SQLite holds full chat history per session; MemPalace holds **curated** facts for RAG. Deleting a chat session does **not** automatically delete MemPalace rows (by design: facts may still be wanted).

### Categories for retrieval

- **Room = category slug** from the extractor (English, lowercase, hyphenated), e.g. `identity`, `location`, `cars`.
- **Stable labels** (e.g. `given name`, `favourite car`) allow **upsert**: updating the same fact replaces the old drawer instead of duplicating.

---

## Technical

### Storage layout

- **`MEMPALACE_PATH`** — Points to the palace directory (default: `backend/data/palace/`). Chroma SQLite and related files live there; should stay out of git for real user data (see `.gitignore`).

### Official API surface we use

| Piece | Role |
|--------|------|
| `mempalace.palace.get_collection` | Open/create the drawers collection. |
| `mempalace.searcher.search_memories` | Hybrid retrieval (vector + BM25-style rerank) for `/chat` when `use_memory` is true. |
| `mempalace.miner.detect_hall` | Assigns `hall` from content keywords (used when we upsert facts). |

We **bypass** `mempalace.miner.add_drawer` for journal facts because it hashes **`(source_file, chunk_index)`** into drawer IDs. We need **deterministic IDs** per `(wing, room, label)` to **upsert** updates. Instead we call **`collection.upsert`** directly with IDs from `memory_facts.stable_drawer_id`.

### Wing / room / search filters

- **`search_memories(..., wing=WING, room=ROOM)`** restricts results to one room. After we started filing facts into **dynamic rooms** (categories), that hid most facts.
- **Fix**: call **`room=None`** (only **`wing`** set) so search spans **all category rooms** under that wing.

### Chroma `get()` / listing drawers

- Newer Chroma validates `include=` strictly. **`"ids"` must not appear in `include`** — IDs are returned by default. Including `"ids"` caused **`ValueError`** and HTTP 500 on `GET /memory/items`.
- **Symptom in the browser**: “CORS blocked” / no `Access-Control-Allow-Origin` — often because the **real response was 500** from an unhandled exception, not a missing CORS config.

### Metadata we set on upserted facts

- `wing`, `room` (category slug), `source_file` (synthetic path under `_journal_facts/`), `chunk_index`, `added_by`, `filed_at`, `normalize_version`, **`hall`** from `detect_hall(line)`.

### Stable keys and collisions

- **Labeled facts** — `label_key = label.lower()`; same category + same label → same drawer → **update**.
- **Unlabeled facts in one category** — `label_key = "v-" + sha256(value)[:16]` so multiple standalone facts in the same room **do not** overwrite each other.

### Ollama extraction

- **`format: "json"`** on `/api/chat` nudges structured output; prompt asks for `{"facts":[{"category","label","value"},...]}`.
- Parser tolerates optional markdown fences around JSON.
- Prompt quality **directly** affects stored noise; we iterated on **priority** (name/place vs app meta).

### HTTP API (this app)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/memory/items` | Paginated list for the Memory library. |
| `POST` | `/memory/delete` | Delete a drawer by `drawer_id`. |
| `POST` | `/chat` | Chat; optional MemPalace retrieval; async fact extract + upsert after reply. |

CORS is configured for the Next.js origin (e.g. `http://localhost:3000`).

---

## References in this repo

| Area | Files |
|------|--------|
| Retrieval + chat | `backend/main.py` |
| List/delete drawers | `backend/memory_items.py` |
| Ollama extraction | `backend/memory_extract.py` |
| Upsert facts | `backend/memory_facts.py` |

---

## Quick checklist for future changes

1. After changing how drawers are stored, confirm **`search_memories`** filters still include all relevant **rooms** (or drop `room` filter).
2. After Chroma upgrades, re-check **`collection.get(include=[...])`** against current Chroma docs.
3. If the UI shows CORS errors, **curl the API with `Origin:`** and inspect status body — often **500**, not CORS misconfiguration.
4. Tune extraction prompts when users report **wrong or shallow facts**; consider post-filters only as a last resort (brittle).

---

*Document generated from Smart Journal integration work; adjust as MemPalace/Chroma/Ollama versions evolve.*
