"""
Smart Journal API — FastAPI + MemPalace retrieval + Ollama (local LLM).
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mempalace.miner import add_drawer
from mempalace.palace import get_collection
from mempalace.searcher import search_memories

logger = logging.getLogger("smart_journal")

PALACE_PATH = os.environ.get(
    "MEMPALACE_PATH",
    str(Path(__file__).resolve().parent / "data" / "palace"),
)
WING = "smart-journal"
ROOM = "journal"
AGENT = "smart-journal-api"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16_000)


class ChatResponse(BaseModel):
    reply: str


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
    system = (
        "You are a thoughtful journaling companion for Smart Journal. "
        "Be warm, concise, and helpful. If prior journal context is provided, "
        "use it naturally without quoting it verbatim unless asked."
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


def save_user_message_to_palace(text: str) -> None:
    collection = get_collection(PALACE_PATH, create=True)
    source = str(Path(PALACE_PATH) / "journal_entries.md")
    chunk_index = int(time.time_ns() % (2**31))
    add_drawer(
        collection=collection,
        wing=WING,
        room=ROOM,
        content=text.strip(),
        source_file=source,
        chunk_index=chunk_index,
        agent=AGENT,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    ensure_palace()
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


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    ensure_palace()

    search = search_memories(
        query=user_text,
        palace_path=PALACE_PATH,
        wing=WING,
        room=ROOM,
        n_results=5,
    )
    context = format_mempalace_context(search)

    reply = generate_reply(user_text, context)

    try:
        save_user_message_to_palace(user_text)
    except Exception:
        logger.exception("Failed to save user message to MemPalace")

    return ChatResponse(reply=reply)
