"use client";

import { useEffect, useRef, useState } from "react";

type Role = "user" | "assistant";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
};

const API_URL = "http://localhost:8000/chat";

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

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
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
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
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-full flex-1 flex-col bg-[#f7f5f2] text-zinc-800">
      <header className="border-b border-zinc-200/80 bg-white/70 px-6 py-4 backdrop-blur-sm">
        <div className="mx-auto flex max-w-2xl items-baseline justify-between gap-4">
          <div>
            <h1 className="font-serif text-xl font-medium tracking-tight text-zinc-900">
              Smart Journal
            </h1>
            <p className="mt-0.5 text-sm text-zinc-500">
              Write freely — your companion remembers with MemPalace.
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 pb-6 pt-6 sm:px-6">
        <div className="flex min-h-[50vh] flex-1 flex-col rounded-2xl border border-zinc-200/80 bg-white/90 shadow-sm">
          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6">
            {messages.length === 0 && !loading && (
              <p className="text-center font-serif text-lg leading-relaxed text-zinc-500">
                Start a quiet entry below. Past thoughts surface when they
                matter — then the AI responds, and your line is saved to
                memory.
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
        </div>
      </main>
    </div>
  );
}
