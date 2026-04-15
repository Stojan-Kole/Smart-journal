# Smart Journal

Minimal full-stack journaling demo: a **Next.js** chat UI talks to a **FastAPI** backend that retrieves context with **MemPalace** and generates replies with **Ollama** (local LLM — no API fees).

```
frontend (Next.js)  →  POST /chat  →  backend (FastAPI)
                                         ↓
                              MemPalace search → Ollama (llama3.2, …)
                                         ↓
                              Save user line to MemPalace
```

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** (with npm)
- **Ollama** — [ollama.com](https://ollama.com) (install, then pull a model)

Install MemPalace from PyPI only: [pypi.org/project/mempalace](https://pypi.org/project/mempalace) (official package; avoid unofficial installers).

## Repository layout

| Path | Role |
|------|------|
| `frontend/` | Next.js App Router + Tailwind — `npm run dev` (default **http://localhost:3000**) |
| `backend/` | FastAPI — `uvicorn main:app` (default **http://127.0.0.1:8000**) |

Local MemPalace / Chroma data lives under `backend/data/` and is **not** committed (see `.gitignore`).

## Quick start

### 1. Ollama

```bash
ollama pull llama3.2
# or another model; set OLLAMA_MODEL if different
```

Ensure the Ollama daemon is running (the app expects **http://127.0.0.1:11434** by default).

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the app

Use a **colon** before the port:

- **http://localhost:3000** — correct  
- `http://localhost/3000` — wrong (that is a path, not port 3000)

## Configuration (optional)

| Variable | Default | Meaning |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama HTTP API |
| `OLLAMA_MODEL` | `llama3.2` | Model name (`ollama list`) |
| `MEMPALACE_PATH` | `backend/data/palace` | MemPalace / Chroma storage directory |

## API

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/chat` | `{"message":"..."}` | `{"reply":"..."}` |

CORS allows `http://localhost:3000`.

## Troubleshooting

- **Connection refused / 503 from Ollama** — Start Ollama; run `ollama serve` if needed; confirm `ollama list` shows your model.
- **Empty or slow first reply** — First local inference can be slow; ensure RAM is sufficient for the chosen model.
- **Wrong URL** — Always `http://localhost:3000` (colon `:`), not slash `/`.

## Presenting / demo video (outline)

1. **Intro (30–45 s)** — Problem: journaling + memory; solution stack (Next, FastAPI, MemPalace, Ollama).
2. **Environment (30 s)** — Terminal: `ollama list`, then start backend + frontend (split terminal or two tabs).
3. **Browser (60–90 s)** — Open `http://localhost:3000`, send 2–3 messages; show a follow-up that benefits from prior context.
4. **Optional (30 s)** — `GET /health` or show `backend/data/` (explain it is local only / gitignored).
5. **Outro (15 s)** — Repo link, “local-only, no cloud LLM cost.”

Record full screen or browser + one terminal; 1080p, clear mic; rehearse once to avoid long waits on first model load.

## License

MIT — adjust if you prefer another license.
