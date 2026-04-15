"""
Smart Journal API — FastAPI + MemPalace retrieval + Ollama (local LLM).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db as journal_db
import memory_items as memory_catalog
import memory_extract
import memory_facts
from mempalace.palace import get_collection
from mempalace.searcher import search_memories

logger = logging.getLogger("smart_journal")

PALACE_PATH = os.environ.get(
    "MEMPALACE_PATH",
    str(Path(__file__).resolve().parent / "data" / "palace"),
)
WING = "smart-journal"
AGENT = "smart-journal-api"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
JOURNAL_DB_PATH = os.environ.get(
    "JOURNAL_DB_PATH",
    str(Path(__file__).resolve().parent / "data" / "journal.sqlite"),
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16_000)
    session_id: str = Field(
        ...,
        min_length=8,
        description="Client-generated id for this diary session (new on each page load).",
    )
    journal_date: str = Field(
        ...,
        description="Calendar day for this entry (YYYY-MM-DD). Must be today to write.",
    )
    use_memory: bool = Field(
        False,
        description="If true, retrieve related passages from MemPalace for this message.",
    )


class ChatResponse(BaseModel):
    reply: str


class JournalMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class JournalDayListResponse(BaseModel):
    days: list[str]


class JournalSessionOut(BaseModel):
    session_id: str
    journal_date: str
    started_at: str


class JournalSessionListResponse(BaseModel):
    sessions: list[JournalSessionOut]


class JournalMessagesResponse(BaseModel):
    session_id: str
    journal_date: str | None
    messages: list[JournalMessageOut]


class MemoryItemOut(BaseModel):
    drawer_id: str
    wing: str
    room: str
    hall: str | None = None
    preview: str
    text: str
    source_file: str | None = None
    filed_at: str | None = None
    added_by: str | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryItemOut]
    total: int


class DeleteMemoryRequest(BaseModel):
    drawer_id: str = Field(..., min_length=1)


def ensure_palace() -> None:
    Path(PALACE_PATH).mkdir(parents=True, exist_ok=True)
    get_collection(PALACE_PATH, create=True)


def format_mempalace_context(search: dict) -> str:
    if search.get("error"):
        logger.warning("MemPalace search note: %s", search.get("error"))
        return ""
    results = search.get("results") or []
    if not results:
        return ""
    lines: list[str] = []
    for hit in results:
        text = (hit.get("text") or "").strip()
        if not text:
            continue
        sim = hit.get("similarity", 0)
        lines.append(f"[similarity={sim}] {text}")
    return "\n\n".join(lines)


def generate_reply(user_message: str, mempalace_context: str) -> str:
    if mempalace_context:
        system = (
            "You are a thoughtful journaling companion for Smart Journal. "
            "The user chose to connect this message with older journal memories (shown below). "
            "Use them only where they help; be warm and concise."
        )
    else:
        system = (
            "You are a thoughtful journaling companion for Smart Journal. "
            "Respond to what they wrote right now in this conversation. "
            "Do not bring up older diary entries, past days, or memories unless the user explicitly asks you to — "
            "they are not providing that context for this turn."
        )
    user_parts: list[str] = []
    if mempalace_context:
        user_parts.append(
            "Relevant memories from the user's journal (retrieved via MemPalace):\n"
            + mempalace_context
        )
    user_parts.append(f"User message:\n{user_message}")

    url = urljoin(OLLAMA_BASE_URL + "/", "api/chat")
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=payload)
    except httpx.ConnectError as e:
        logger.exception("Cannot reach Ollama")
        raise HTTPException(
            status_code=503,
            detail=(
                f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
                "Start the Ollama app or run `ollama serve`, then `ollama pull "
                f"{OLLAMA_MODEL}` if you have not pulled this model yet."
            ),
        ) from e

    if r.status_code != 200:
        detail = r.text[:500] if r.text else r.reason_phrase
        logger.error("Ollama error %s: %s", r.status_code, detail)
        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned {r.status_code}: {detail}",
        )

    try:
        data = r.json()
    except ValueError as e:
        raise HTTPException(status_code=502, detail="Invalid JSON from Ollama") from e

    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        raise HTTPException(
            status_code=502,
            detail="Empty response from Ollama. Is the model downloaded? `ollama pull "
            + OLLAMA_MODEL
            + "`",
        )
    return content


def parse_ymd(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail="journal_date must be YYYY-MM-DD.",
        ) from e


def assert_writable_day(journal_date: str) -> None:
    """Only today's session accepts new messages (journal semantics)."""
    jd = parse_ymd(journal_date)
    today = date.today()
    if jd != today:
        raise HTTPException(
            status_code=400,
            detail="Past days are read-only. You can only write in today's journal.",
        )


def assert_session_journal_date(
    session_id: str, journal_date: str, existing: str | None
) -> None:
    if existing is not None and existing != journal_date:
        raise HTTPException(
            status_code=400,
            detail="This session already belongs to a different calendar day.",
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    journal_db.init_db(JOURNAL_DB_PATH)
    ensure_palace()
    logger.info("Journal DB: %s", JOURNAL_DB_PATH)
    logger.info("MemPalace storage path: %s", PALACE_PATH)
    logger.info("Ollama: %s model=%s", OLLAMA_BASE_URL, OLLAMA_MODEL)
    yield


app = FastAPI(title="Smart Journal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/memory/items", response_model=MemoryListResponse)
def list_memory_items(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> MemoryListResponse:
    ensure_palace()
    raw, total = memory_catalog.list_drawer_items(
        PALACE_PATH, limit=limit, offset=offset
    )
    return MemoryListResponse(
        items=[MemoryItemOut(**r) for r in raw],
        total=total,
    )


@app.post("/memory/delete")
def delete_memory_item(body: DeleteMemoryRequest) -> dict[str, bool]:
    ensure_palace()
    ok = memory_catalog.delete_drawer(PALACE_PATH, body.drawer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory entry not found.")
    return {"ok": True}


@app.get("/journal/days", response_model=JournalDayListResponse)
def list_journal_days() -> JournalDayListResponse:
    days = journal_db.list_days(JOURNAL_DB_PATH)
    return JournalDayListResponse(days=days)


@app.get("/journal/sessions", response_model=JournalSessionListResponse)
def list_journal_sessions() -> JournalSessionListResponse:
    raw = journal_db.list_sessions(JOURNAL_DB_PATH)
    return JournalSessionListResponse(
        sessions=[
            JournalSessionOut(
                session_id=r["session_id"],
                journal_date=r["journal_date"],
                started_at=r["started_at"],
            )
            for r in raw
        ],
    )


@app.delete("/journal/session/{session_id}")
def delete_journal_session(session_id: str) -> dict[str, bool | int]:
    n = journal_db.delete_session(JOURNAL_DB_PATH, session_id)
    if n == 0:
        raise HTTPException(
            status_code=404,
            detail="No messages found for this session.",
        )
    return {"ok": True, "deleted": n}


@app.get("/journal/session/{session_id}", response_model=JournalMessagesResponse)
def get_journal_session(session_id: str) -> JournalMessagesResponse:
    rows = journal_db.get_messages_by_session(JOURNAL_DB_PATH, session_id)
    if not rows:
        return JournalMessagesResponse(
            session_id=session_id,
            journal_date=None,
            messages=[],
        )
    jd = rows[0]["journal_date"]
    return JournalMessagesResponse(
        session_id=session_id,
        journal_date=jd,
        messages=[
            JournalMessageOut(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ],
    )


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    assert_writable_day(body.journal_date)

    existing_jd = journal_db.get_session_journal_date(JOURNAL_DB_PATH, body.session_id)
    assert_session_journal_date(body.session_id, body.journal_date, existing_jd)

    ensure_palace()

    if body.use_memory:
        search = search_memories(
            query=user_text,
            palace_path=PALACE_PATH,
            wing=WING,
            room=None,
            n_results=5,
        )
        context = format_mempalace_context(search)
    else:
        context = ""

    reply = generate_reply(user_text, context)

    try:
        journal_db.insert_message(
            JOURNAL_DB_PATH, body.session_id, body.journal_date, "user", user_text
        )
        journal_db.insert_message(
            JOURNAL_DB_PATH, body.session_id, body.journal_date, "assistant", reply
        )
    except Exception:
        logger.exception("Failed to save journal messages to SQLite")

    try:
        extracted = memory_extract.extract_key_facts(
            user_text, OLLAMA_BASE_URL, OLLAMA_MODEL
        )
        memory_facts.save_extracted_facts(
            PALACE_PATH, WING, extracted, AGENT
        )
    except Exception:
        logger.exception("Failed to save extracted facts to MemPalace")

    return ChatResponse(reply=reply)
