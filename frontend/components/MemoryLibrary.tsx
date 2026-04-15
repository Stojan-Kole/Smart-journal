"use client";

import { useCallback, useEffect, useState } from "react";

export type MemoryItem = {
  drawer_id: string;
  wing: string;
  room: string;
  hall: string | null;
  preview: string;
  text: string;
  source_file: string | null;
  filed_at: string | null;
  added_by: string | null;
};

export function MemoryLibrary({
  apiBase,
  open,
  onClose,
}: {
  apiBase: string;
  open: boolean;
  onClose: () => void;
}) {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/memory/items?limit=200&offset=0`);
      const data = (await res.json()) as {
        items?: MemoryItem[];
        total?: number;
        detail?: unknown;
      };
      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? res.statusText);
        throw new Error(detail || `Failed to load (${res.status})`);
      }
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load memories");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  async function handleDelete(drawerId: string) {
    if (
      !confirm(
        "Remove this entry from MemPalace? Retrieval will no longer use it.",
      )
    ) {
      return;
    }
    setDeleting(drawerId);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/memory/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drawer_id: drawerId }),
      });
      const data = (await res.json()) as { detail?: unknown };
      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? res.statusText);
        throw new Error(detail || `Delete failed (${res.status})`);
      }
      setItems((prev) => prev.filter((x) => x.drawer_id !== drawerId));
      setTotal((t) => Math.max(0, t - 1));
      if (expanded === drawerId) setExpanded(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <button
        type="button"
        className="absolute inset-0 bg-zinc-900/40 backdrop-blur-[2px]"
        aria-label="Close"
        onClick={onClose}
      />
      <div
        className="relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-[#f7f5f2] shadow-xl"
        role="dialog"
        aria-labelledby="memory-library-title"
      >
        <div className="flex items-start justify-between gap-3 border-b border-zinc-200 bg-white/90 px-4 py-3 sm:px-5">
          <div>
            <h2
              id="memory-library-title"
              className="font-serif text-lg font-medium text-zinc-900"
            >
              Saved memories (MemPalace)
            </h2>
            <p className="mt-0.5 text-sm text-zinc-500">
              Each line is stored with a <span className="font-medium">wing</span>{" "}
              and <span className="font-medium">room</span> (category) for
              retrieval. Delete anything you do not want kept.
            </p>
            {!loading && (
              <p className="mt-1 text-xs text-zinc-400">
                Showing {items.length} of {total} drawers
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg px-2 py-1 text-sm text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"
          >
            Close
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5">
          {loading && (
            <p className="text-center text-sm text-zinc-500">Loading…</p>
          )}
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="text-center text-sm text-zinc-500">
              Nothing stored yet. Send messages in your journal to build memory.
            </p>
          )}
          <ul className="space-y-3">
            {items.map((m) => (
              <li
                key={m.drawer_id}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-3 shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                  <span className="rounded-md bg-zinc-100 px-2 py-0.5 font-medium text-zinc-700">
                    wing: {m.wing}
                  </span>
                  <span className="rounded-md bg-amber-50 px-2 py-0.5 font-medium text-amber-900">
                    room: {m.room}
                  </span>
                  {m.hall && (
                    <span className="rounded-md bg-zinc-50 px-2 py-0.5 text-zinc-600">
                      hall: {m.hall}
                    </span>
                  )}
                  {m.filed_at && (
                    <span className="ml-auto">{m.filed_at}</span>
                  )}
                </div>
                <p className="mt-2 text-[15px] leading-relaxed text-zinc-800">
                  {expanded === m.drawer_id ? m.text : m.preview}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(m.preview.endsWith("…") || m.text.length > 280) && (
                    <button
                      type="button"
                      className="text-sm text-zinc-600 underline hover:text-zinc-900"
                      onClick={() =>
                        setExpanded((v) =>
                          v === m.drawer_id ? null : m.drawer_id,
                        )
                      }
                    >
                      {expanded === m.drawer_id ? "Show less" : "Show full"}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={deleting === m.drawer_id}
                    className="ml-auto rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                    onClick={() => void handleDelete(m.drawer_id)}
                  >
                    {deleting === m.drawer_id ? "Removing…" : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
