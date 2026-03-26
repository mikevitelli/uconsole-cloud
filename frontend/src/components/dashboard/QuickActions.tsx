"use client";

import { useState } from "react";
import { useLocalMode } from "@/components/LocalModeProvider";

interface ActionResult {
  status: "idle" | "running" | "success" | "error";
  message?: string;
}

/**
 * Quick action buttons that execute commands on the local webdash.
 * Only renders when local mode is active.
 *
 * NOTE: The webdash nginx config must include
 *   Access-Control-Allow-Origin: https://uconsole.cloud
 * and allow POST methods for /api/run/* endpoints.
 */
export function QuickActions() {
  const { isLocal, baseUrl } = useLocalMode();
  const [results, setResults] = useState<Record<string, ActionResult>>({});

  if (!isLocal || !baseUrl) return null;

  async function runAction(id: string, method: string, path: string) {
    setResults((prev) => ({ ...prev, [id]: { status: "running" } }));

    try {
      const res = await fetch(`${baseUrl}${path}`, {
        method,
        signal: AbortSignal.timeout(30_000),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "unknown error");
        setResults((prev) => ({
          ...prev,
          [id]: { status: "error", message: `${res.status}: ${text.slice(0, 120)}` },
        }));
        return;
      }

      const text = await res.text().catch(() => "");
      setResults((prev) => ({
        ...prev,
        [id]: { status: "success", message: text.slice(0, 200) || "done" },
      }));
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [id]: { status: "error", message: String(err) },
      }));
    }
  }

  const actions = [
    {
      id: "backup",
      label: "Push backup now",
      method: "POST",
      path: "/api/run/backup-all",
      description: "Run backup-all on device",
    },
    {
      id: "logs",
      label: "View logs",
      method: "GET",
      path: "/api/logs/journal",
      description: "Recent journal entries",
    },
  ];

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x26A1;</span> Quick Actions
        <span className="text-xs font-normal text-dim">(local only)</span>
      </h2>

      {/* Prominent link to the full local webdash */}
      <a
        href={baseUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-between bg-background border rounded-lg px-4 py-2.5 text-sm font-semibold text-bright hover:border-[var(--accent)] transition-colors mb-3"
        style={{
          borderColor: "color-mix(in srgb, var(--green) 25%, var(--border))",
          background: "color-mix(in srgb, var(--green) 5%, var(--bg))",
        }}
      >
        <span>Open webdash &rarr;</span>
        <span className="text-xs font-normal text-dim font-mono">{baseUrl}</span>
      </a>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {actions.map((action) => {
          const result = results[action.id] ?? { status: "idle" };

          return (
            <div key={action.id} className="space-y-1">
              <button
                type="button"
                onClick={() => runAction(action.id, action.method, action.path)}
                disabled={result.status === "running"}
                className="w-full flex items-center justify-between bg-background border border-border rounded-lg px-3 py-2 text-xs hover:border-[var(--accent)] transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-wait"
              >
                <span className="text-bright font-medium">{action.label}</span>
                <span className="text-dim">{action.description}</span>
              </button>

              {result.status !== "idle" && (
                <div
                  className="text-xs px-2 py-1 rounded font-mono truncate"
                  style={{
                    color:
                      result.status === "running"
                        ? "var(--sub)"
                        : result.status === "success"
                          ? "var(--green)"
                          : "var(--red)",
                  }}
                >
                  {result.status === "running"
                    ? "running..."
                    : result.message}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
