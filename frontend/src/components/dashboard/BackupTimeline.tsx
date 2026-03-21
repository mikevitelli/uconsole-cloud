"use client";

import { useState, useCallback, useEffect } from "react";
import { CategoryPills } from "@/components/viz/CategoryPills";
import { fmtDate, CATEGORY_COLORS, categoryLabel } from "@/lib/utils";
import { Spinner } from "@/components/ui/Spinner";
import type { BackupEntry, CommitDetail } from "@/lib/types";

interface FilePreview {
  filename: string;
  content: string | null;
  loading: boolean;
}

function FilePreviewModal({
  preview,
  onClose,
}: {
  preview: FilePreview;
  onClose: () => void;
}) {
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
              {previewError || `Could not load ${basename}`}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

interface BackupTimelineProps {
  backups: BackupEntry[];
}

export function BackupTimeline({ backups }: BackupTimelineProps) {
  const [expandedSha, setExpandedSha] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, CommitDetail>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [commitError, setCommitError] = useState<string | null>(null);

  const openFilePreview = useCallback(async (filename: string) => {
    setPreview({ filename, content: null, loading: true });
    setPreviewError(null);
    try {
      const res = await fetch(
        `/api/raw?path=${encodeURIComponent(filename)}`
      );
      if (res.ok) {
        const text = await res.text();
        setPreview({ filename, content: text, loading: false });
      } else {
        setPreview({ filename, content: null, loading: false });
        setPreviewError(`Failed to load file (${res.status})`);
      }
    } catch {
      setPreview({ filename, content: null, loading: false });
      setPreviewError("Network error loading file");
    }
  }, []);

  // Build category pill items
  const categoryCounts: Record<string, number> = {};
  for (const b of backups) {
    for (const c of b.categories) {
      categoryCounts[c] = (categoryCounts[c] || 0) + 1;
    }
  }
  const pillItems = Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({
      name: categoryLabel(name),
      count,
      color: CATEGORY_COLORS[name] || "var(--accent)",
      key: name,
    }));

  // Reverse lookup: display label → raw key
  const labelToKey: Record<string, string> = {};
  for (const p of pillItems) {
    labelToKey[p.name] = p.key;
  }

  // Filter
  const selectedKey = selectedCategory ? labelToKey[selectedCategory] ?? selectedCategory : null;
  const filtered = selectedKey
    ? backups.filter((b) => b.categories.includes(selectedKey))
    : backups;
  const visible = showAll ? filtered : filtered.slice(0, 8);

  // Fetch commit detail on demand
  const toggleExpand = useCallback(
    async (sha: string) => {
      if (expandedSha === sha) {
        setExpandedSha(null);
        return;
      }
      setExpandedSha(sha);
      setCommitError(null);
      if (!details[sha]) {
        setLoading(sha);
        try {
          const res = await fetch(`/api/github/commits/${sha}`);
          if (res.ok) {
            const data = await res.json();
            setDetails((prev) => ({ ...prev, [sha]: data }));
          }
        } catch {
          setCommitError("Network error loading commit details");
        } finally {
          setLoading(null);
        }
      }
    },
    [expandedSha, details]
  );

  const firstLine = (msg: string) => msg.split("\n")[0];
  const isBackup = (b: BackupEntry) => b.categories.length > 0;

  // Separate counts for the legend
  const backupCount = filtered.filter(isBackup).length;
  const manualCount = filtered.length - backupCount;

  return (
    <div className="mt-4">
      {/* Category filter pills */}
      {pillItems.length > 0 && (
        <div className="mb-3">
          <CategoryPills
            items={pillItems}
            selected={selectedCategory}
            onSelect={setSelectedCategory}
          />
        </div>
      )}

      {/* Source legend */}
      <div className="flex items-center gap-4 mb-3 text-xs text-dim">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: "var(--green)" }} />
          Automated backup ({backupCount})
        </span>
        {manualCount > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: "var(--sub)" }} />
            Manual / other ({manualCount})
          </span>
        )}
      </div>

      {/* Commit list */}
      <div className="space-y-0.5">
        {visible.map((b) => {
          const isExpanded = expandedSha === b.sha;
          const detail = details[b.sha];
          const isLoading = loading === b.sha;
          const automated = isBackup(b);

          return (
            <div key={b.sha}>
              {/* Commit row */}
              <button
                onClick={() => toggleExpand(b.sha)}
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
                                openFilePreview(f.filename);
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
        })}
      </div>

      {/* Show more / less */}
      {filtered.length > 8 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-2 text-xs text-accent hover:underline cursor-pointer bg-transparent border-none"
        >
          {showAll
            ? "Show less"
            : `Show all ${filtered.length} backups`}
        </button>
      )}

      {/* File preview lightbox */}
      {preview && (
        <FilePreviewModal
          preview={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
