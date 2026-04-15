"use client";

import { MemoryLibrary } from "@/components/MemoryLibrary";
import { useCallback, useEffect, useRef, useState } from "react";

type Role = "user" | "assistant";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
};

type JournalSession = {
  session_id: string;
  journal_date: string;
  started_at: string;
};

const API_BASE = "http://localhost:8000";

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatDayHeading(ymd: string): string {
  const [y, mo, day] = ymd.split("-").map(Number);
  const dt = new Date(y, mo - 1, day);
  return dt.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function formatSessionLabel(s: JournalSession): string {
  const [y, mo, day] = s.journal_date.split("-").map(Number);
  const dt = new Date(y, mo - 1, day);
  const today = ymdLocal(new Date());
  const datePart =
    s.journal_date === today
      ? "Today"
      : dt.toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: y !== new Date().getFullYear() ? "numeric" : undefined,
        });
  const t = new Date(s.started_at);
  const timePart = t.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  return `${datePart} · ${timePart}`;
}

export default function Home() {
  const todayStr = ymdLocal(new Date());
  const [activeSessionId] = useState(() => crypto.randomUUID());
  const [selectedSessionId, setSelectedSessionId] = useState(activeSessionId);

  const [sessions, setSessions] = useState<JournalSession[]>([]);
  const [headingYmd, setHeadingYmd] = useState(todayStr);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [useMemory, setUseMemory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingJournal, setLoadingJournal] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(
    null,
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  const isReadOnly = selectedSessionId !== activeSessionId;

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/journal/sessions`);
      if (!res.ok) return;
      const data = (await res.json()) as { sessions?: JournalSession[] };
      setSessions(data.sessions ?? []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    let cancelled = false;
    async function loadSession() {
      setLoadingJournal(true);
      setError(null);
      try {
        const res = await fetch(
          `${API_BASE}/journal/session/${encodeURIComponent(selectedSessionId)}`,
        );
        const data = (await res.json()) as {
          session_id?: string;
          journal_date?: string | null;
          messages?: { id: number; role: Role; content: string }[];
          detail?: unknown;
        };
        if (!res.ok) {
          const detail =
            typeof data.detail === "string"
              ? data.detail
              : JSON.stringify(data.detail ?? res.statusText);
          throw new Error(detail || `Failed to load session (${res.status})`);
        }
        const mapped: ChatMessage[] = (data.messages ?? []).map((m) => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
        }));
        if (!cancelled) {
          setMessages(mapped);
          if (data.journal_date) {
            setHeadingYmd(data.journal_date);
          } else if (selectedSessionId === activeSessionId) {
            setHeadingYmd(todayStr);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load session");
          setMessages([]);
        }
      } finally {
        if (!cancelled) setLoadingJournal(false);
      }
    }
    void loadSession();
    return () => {
      cancelled = true;
    };
  }, [selectedSessionId, activeSessionId, todayStr]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading || isReadOnly) return;

    setError(null);
    setInput("");
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: activeSessionId,
          journal_date: todayStr,
          use_memory: useMemory,
        }),
      });
      const data = (await res.json()) as { reply?: string; detail?: unknown };

      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? res.statusText);
        throw new Error(detail || `Request failed (${res.status})`);
      }

      if (!data.reply) {
        throw new Error("No reply in response");
      }

      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.reply!,
        },
      ]);
      void loadSessions();
      const r = await fetch(
        `${API_BASE}/journal/session/${encodeURIComponent(activeSessionId)}`,
      );
      const j = (await r.json()) as {
        messages?: { id: number; role: Role; content: string }[];
        journal_date?: string | null;
      };
      if (r.ok && j.messages) {
        setMessages(
          j.messages.map((m) => ({
            id: String(m.id),
            role: m.role,
            content: m.content,
          })),
        );
        if (j.journal_date) setHeadingYmd(j.journal_date);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setError(msg);
      setMessages((m) => m.filter((x) => x.id !== userMsg.id));
    } finally {
      setLoading(false);
    }
  }

  const otherSessions = sessions.filter((s) => s.session_id !== activeSessionId);

  async function deletePastSession(sessionId: string) {
    if (
      !confirm(
        "Remove this chat from your journal? This cannot be undone.",
      )
    ) {
      return;
    }
    setDeletingSessionId(sessionId);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/journal/session/${encodeURIComponent(sessionId)}`,
        { method: "DELETE" },
      );
      const data = (await res.json()) as { detail?: unknown };
      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? res.statusText);
        throw new Error(detail || `Failed to delete (${res.status})`);
      }
      await loadSessions();
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(activeSessionId);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete entry");
    } finally {
      setDeletingSessionId(null);
    }
  }

  return (
    <div className="flex min-h-full flex-1 flex-col bg-[#f7f5f2] text-zinc-800">
      <header className="border-b border-zinc-200/80 bg-white/70 px-6 py-4 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="font-serif text-xl font-medium tracking-tight text-zinc-900">
              Smart Journal
            </h1>
            <p className="mt-0.5 text-sm text-zinc-500">
              Each visit starts a new entry. Turn on &quot;Use past memories&quot;
              only when you want the AI to draw on older journal lines.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setMemoryOpen(true)}
            className="shrink-0 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-800 shadow-sm transition hover:bg-zinc-50"
          >
            Memory library
          </button>
        </div>
      </header>

      <MemoryLibrary
        apiBase={API_BASE}
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
      />

      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 pb-6 pt-4 sm:flex-row sm:px-6">
        <aside className="shrink-0 sm:w-56 lg:w-60">
          <p className="mb-2 hidden text-xs font-medium uppercase tracking-wide text-zinc-400 sm:block">
            Entries
          </p>
          <nav
            className="flex flex-row gap-1 overflow-x-auto pb-2 sm:flex-col sm:overflow-x-visible sm:pb-0"
            aria-label="Journal entries"
          >
            <button
              type="button"
              onClick={() => setSelectedSessionId(activeSessionId)}
              className={
                selectedSessionId === activeSessionId
                  ? "shrink-0 rounded-lg bg-zinc-900 px-3 py-2 text-left text-sm font-medium text-white"
                  : "shrink-0 rounded-lg px-3 py-2 text-left text-sm text-zinc-600 transition hover:bg-zinc-200/60"
              }
            >
              Current entry
            </button>
            {otherSessions.map((s) => (
              <div
                key={s.session_id}
                className="flex min-w-0 shrink-0 items-stretch gap-0.5 rounded-lg sm:w-full"
              >
                <button
                  type="button"
                  onClick={() => setSelectedSessionId(s.session_id)}
                  disabled={deletingSessionId === s.session_id}
                  className={
                    selectedSessionId === s.session_id
                      ? "min-w-0 flex-1 rounded-l-lg bg-zinc-900 px-3 py-2 text-left text-sm font-medium text-white"
                      : "min-w-0 flex-1 rounded-l-lg px-3 py-2 text-left text-sm text-zinc-600 transition hover:bg-zinc-200/60 disabled:opacity-50"
                  }
                >
                  {formatSessionLabel(s)}
                </button>
                <button
                  type="button"
                  title="Delete this chat"
                  aria-label="Delete this chat"
                  disabled={deletingSessionId !== null}
                  onClick={() => void deletePastSession(s.session_id)}
                  className={
                    selectedSessionId === s.session_id
                      ? "shrink-0 rounded-r-lg bg-zinc-800 px-2 py-2 text-sm text-zinc-200 transition hover:bg-zinc-700 disabled:opacity-50"
                      : "shrink-0 rounded-r-lg px-2 py-2 text-sm text-zinc-500 transition hover:bg-red-100 hover:text-red-800 disabled:opacity-50"
                  }
                >
                  {deletingSessionId === s.session_id ? "…" : "×"}
                </button>
              </div>
            ))}
          </nav>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="mb-3">
            <h2 className="font-serif text-lg text-zinc-900">
              {formatDayHeading(headingYmd)}
            </h2>
            {isReadOnly && (
              <p className="mt-1 text-sm text-amber-800">
                Reading a past entry — it cannot be changed. Use &quot;Current
                entry&quot; to write.
              </p>
            )}
          </div>

          <div className="flex min-h-[50vh] flex-1 flex-col rounded-2xl border border-zinc-200/80 bg-white/90 shadow-sm">
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6">
              {loadingJournal && (
                <p className="text-center text-sm text-zinc-500">Loading…</p>
              )}
              {!loadingJournal &&
                messages.length === 0 &&
                !loading &&
                !isReadOnly && (
                  <p className="text-center font-serif text-lg leading-relaxed text-zinc-500">
                    A fresh page — write below. Refresh or a new tab starts a new
                    entry; past sessions stay in the list.
                  </p>
                )}
              {!loadingJournal &&
                messages.length === 0 &&
                !loading &&
                isReadOnly && (
                  <p className="text-center text-zinc-500">
                    No messages in this entry.
                  </p>
                )}
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={
                    m.role === "user"
                      ? "ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-zinc-900 px-4 py-3 text-[15px] leading-relaxed text-zinc-50 shadow-sm"
                      : "mr-auto max-w-[90%] rounded-2xl rounded-bl-md border border-zinc-100 bg-[#faf9f7] px-4 py-3 text-[15px] leading-relaxed text-zinc-800"
                  }
                >
                  {m.content}
                </div>
              ))}
              {loading && (
                <div className="mr-auto max-w-[90%] rounded-2xl rounded-bl-md border border-dashed border-zinc-200 bg-[#faf9f7] px-4 py-3 text-sm italic text-zinc-500">
                  Thinking…
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {error && (
              <div className="border-t border-red-100 bg-red-50/90 px-4 py-2 text-sm text-red-800 sm:px-6">
                {error}
              </div>
            )}

            <div className="border-t border-zinc-100 p-3 sm:p-4">
              {isReadOnly ? (
                <p className="text-center text-sm text-zinc-500">
                  Read-only — open &quot;Current entry&quot; to add to your
                  diary.
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-600">
                    <input
                      type="checkbox"
                      checked={useMemory}
                      onChange={(e) => setUseMemory(e.target.checked)}
                      className="size-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-950/20"
                      disabled={loading}
                    />
                    <span>Use past memories (MemPalace) for this message</span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      placeholder="What is on your mind?"
                      className="min-h-11 flex-1 rounded-xl border border-zinc-200 bg-white px-4 text-[15px] text-zinc-900 placeholder:text-zinc-400 outline-none ring-zinc-950/10 focus:ring-2"
                      disabled={loading}
                      aria-label="Journal entry"
                    />
                    <button
                      type="button"
                      onClick={() => void send()}
                      disabled={loading || !input.trim()}
                      className="shrink-0 rounded-xl bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Send
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
