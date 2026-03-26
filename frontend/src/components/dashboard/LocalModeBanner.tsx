"use client";

import { useLocalMode } from "@/components/LocalModeProvider";

export function LocalModeBanner() {
  const { isLocal, baseUrl } = useLocalMode();

  if (!isLocal) return null;

  return (
    <div className="flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-1.5 text-xs">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--green)] opacity-75 animate-ping" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--green)]" />
      </span>
      <span className="text-bright font-medium">Local mode</span>
      <span className="text-dim">— live data from</span>
      <span className="text-sub font-mono">{baseUrl}</span>
    </div>
  );
}
