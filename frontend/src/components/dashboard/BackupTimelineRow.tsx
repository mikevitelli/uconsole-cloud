"use client";

import { CATEGORY_COLORS, categoryLabel, fmtDate } from "@/lib/utils";
import { Spinner } from "@/components/ui/Spinner";
import type { BackupEntry, CommitDetail } from "@/lib/types";

interface BackupTimelineRowProps {
  backup: BackupEntry;
  isExpanded: boolean;
  detail: CommitDetail | undefined;
  isLoading: boolean;
  commitError: string | null;
  onExpand: (sha: string) => void;
  onPreview: (filename: string) => void;
}

export function BackupTimelineRow({
  backup: b,
  isExpanded,
  detail,
  isLoading,
  commitError,
  onExpand,
  onPreview,
}: BackupTimelineRowProps) {
  const firstLine = (msg: string) => msg.split("\n")[0];
  const automated = b.categories.length > 0;

  return (
    <div>
      {/* Commit row */}
      <button
        onClick={() => onExpand(b.sha)}
        className="w-full flex items-start gap-2 sm:gap-2.5 py-2.5 px-2 sm:px-2.5 rounded-lg text-left transition-colors hover:bg-background cursor-pointer border-none bg-transparent"
      >
        <span
          className="w-2 h-2 rounded-full shrink-0 mt-1.5"
          style={{
            background: isExpanded
              ? "var(--accent)"
              : automated
                ? "var(--green)"
                : "var(--sub)",
          }}
        />
        <div className="flex-1 min-w-0 space-y-1">
          {/* Message + source badge */}
          <div className="flex items-start gap-2 text-xs">
            <span className="text-foreground break-words sm:truncate flex-1">
              {firstLine(b.message)}
            </span>
            <span
              className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium border leading-tight"
              style={{
                color: automated ? "var(--green)" : "var(--sub)",
                borderColor: automated ? "var(--green)" : "var(--border)",
                background: automated ? "var(--green)15" : "transparent",
              }}
            >
              {automated ? "backup" : "manual"}
            </span>
          </div>

          {/* Meta row */}
          <div className="flex items-center gap-1.5 text-[11px] text-dim">
            <span>{fmtDate(b.date)}</span>
            <span className="font-mono">{b.sha.substring(0, 7)}</span>
            {b.fileCount !== null && (
              <span className="text-sub bg-background border border-border rounded px-1 py-px tabular-nums">
                {b.fileCount} file{b.fileCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {/* Category tags */}
          {b.categories.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {b.categories.map((cat) => (
                <span
                  key={cat}
                  className="text-[10px] rounded-full px-1.5 py-0.5 border leading-tight"
                  style={{
                    color: CATEGORY_COLORS[cat] || "var(--sub)",
                    borderColor: CATEGORY_COLORS[cat] || "var(--border)",
                    background: `${CATEGORY_COLORS[cat] || "var(--border)"}15`,
                  }}
                >
                  {categoryLabel(cat)}
                </span>
              ))}
            </div>
          )}
        </div>
        <a
          href={b.htmlUrl.startsWith("https://github.com/") ? b.htmlUrl : "#"}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-dim hover:text-accent text-xs shrink-0 mt-1"
          title="View on GitHub"
        >
          &#x2197;
        </a>
      </button>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="ml-4 sm:ml-5 mt-1 mb-3 bg-background border border-border rounded-lg p-3">
          {isLoading && (
            <div className="flex items-center justify-center py-4">
              <Spinner className="w-5 h-5" />
            </div>
          )}
          {!isLoading && detail && (
            <>
              <div className="flex gap-4 text-xs text-sub mb-2 font-mono">
                <span className="text-green">
                  +{detail.stats.additions}
                </span>
                <span className="text-red">
                  -{detail.stats.deletions}
                </span>
                <span className="text-dim">
                  {detail.files.length} file
                  {detail.files.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 mt-2">
                {detail.files.map((f) => (
                  <div
                    key={f.filename}
                    className="flex items-center gap-1.5 text-xs py-0.5"
                  >
                    <span
                      className="shrink-0 w-4 text-center font-mono"
                      style={{
                        color:
                          f.status === "added"
                            ? "var(--green)"
                            : f.status === "removed"
                              ? "var(--red)"
                              : "var(--yellow)",
                      }}
                    >
                      {f.status === "added"
                        ? "A"
                        : f.status === "removed"
                          ? "D"
                          : f.status === "renamed"
                            ? "R"
                            : "M"}
                    </span>
                    <span
                      className="text-accent font-mono text-[11px] truncate flex-1 min-w-0 cursor-pointer hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onPreview(f.filename);
                      }}
                    >
                      {f.filename}
                    </span>
                    <span className="text-green tabular-nums shrink-0 text-[11px]">
                      +{f.additions}
                    </span>
                    <span className="text-red tabular-nums shrink-0 text-[11px]">
                      -{f.deletions}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
          {!isLoading && !detail && (
            <p className="text-xs text-sub">
              {commitError || "Could not load commit details."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
