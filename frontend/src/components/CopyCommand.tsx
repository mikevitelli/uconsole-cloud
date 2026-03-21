"use client";

import { useState } from "react";

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex items-center gap-2 bg-background border border-border rounded-lg px-4 py-3 font-mono text-sm">
      <span className="text-dim select-none">$</span>
      <code className="flex-1 text-foreground overflow-x-auto whitespace-nowrap">
        {command}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="text-dim hover:text-foreground transition-colors cursor-pointer shrink-0"
        aria-label="Copy command"
      >
        {copied ? (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3.5 8.5 6.5 11.5 12.5 5.5" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
            <path d="M10.5 5.5V3.5A1.5 1.5 0 009 2H3.5A1.5 1.5 0 002 3.5V9a1.5 1.5 0 001.5 1.5h2" />
          </svg>
        )}
      </button>
    </div>
  );
}
