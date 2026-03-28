"use client";

import { useEffect } from "react";
import { Spinner } from "@/components/ui/Spinner";

export interface FilePreview {
  filename: string;
  content: string | null;
  loading: boolean;
}

interface FilePreviewModalProps {
  preview: FilePreview;
  error: string | null;
  onClose: () => void;
}

export function FilePreviewModal({
  preview,
  error,
  onClose,
}: FilePreviewModalProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const ext = preview.filename.split(".").pop() || "";
  const basename = preview.filename.split("/").pop() || preview.filename;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70" />

      {/* Modal */}
      <div
        className="relative bg-card border border-border rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs text-dim font-mono truncate">
              {preview.filename}
            </span>
            {ext && (
              <span className="text-[10px] text-sub bg-background border border-border rounded px-1.5 py-0.5 shrink-0">
                .{ext}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-dim hover:text-foreground text-lg cursor-pointer bg-transparent border-none shrink-0 ml-2"
          >
            &#x2715;
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {preview.loading && (
            <div className="flex items-center justify-center py-12">
              <Spinner className="w-6 h-6" />
            </div>
          )}
          {!preview.loading && preview.content !== null && (
            <pre className="text-xs font-mono text-foreground whitespace-pre overflow-x-auto leading-relaxed">
              <code>
                {preview.content.split("\n").map((line, i) => (
                  <div key={i} className="flex hover:bg-background/50">
                    <span className="text-dim select-none w-10 shrink-0 text-right pr-3 tabular-nums">
                      {i + 1}
                    </span>
                    <span className="flex-1">{line}</span>
                  </div>
                ))}
              </code>
            </pre>
          )}
          {!preview.loading && preview.content === null && (
            <p className="text-sm text-sub text-center py-8">
              {error || `Could not load ${basename}`}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
