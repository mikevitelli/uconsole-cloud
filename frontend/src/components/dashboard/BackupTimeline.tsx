"use client";

import { useState, useCallback } from "react";
import { CategoryPills } from "@/components/viz/CategoryPills";
import { CATEGORY_COLORS, categoryLabel } from "@/lib/utils";
import type { BackupEntry, CommitDetail } from "@/lib/types";
import { FilePreviewModal } from "@/components/dashboard/FilePreviewModal";
import type { FilePreview } from "@/components/dashboard/FilePreviewModal";
import { BackupTimelineRow } from "@/components/dashboard/BackupTimelineRow";

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

  // Reverse lookup: display label -> raw key
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
        {visible.map((b) => (
          <BackupTimelineRow
            key={b.sha}
            backup={b}
            isExpanded={expandedSha === b.sha}
            detail={details[b.sha]}
            isLoading={loading === b.sha}
            commitError={commitError}
            onExpand={toggleExpand}
            onPreview={openFilePreview}
          />
        ))}
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
          error={previewError}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
