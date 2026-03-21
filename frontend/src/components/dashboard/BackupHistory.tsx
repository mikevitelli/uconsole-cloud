import { Sparkline } from "@/components/viz/Sparkline";
import { StatCards } from "@/components/viz/StatCards";
import { CalendarGrid } from "@/components/viz/CalendarGrid";
import { BackupTimeline } from "@/components/dashboard/BackupTimeline";
import { fmtDate, daysSince, ageLabel, getLastBackupByCategory, CATEGORY_COLORS, categoryLabel } from "@/lib/utils";
import type { BackupEntry } from "@/lib/types";

interface BackupHistoryContent {
  heading?: string;
  sparklineLabel?: string;
  totalLabel?: string;
  latestLabel?: string;
}

interface BackupHistoryProps {
  backups: BackupEntry[];
  content?: BackupHistoryContent;
}


export function BackupHistory({ backups, content }: BackupHistoryProps) {
  // Build sparkline data for last 30 days
  const counts: Record<string, number> = {};
  const now = new Date();
  for (let d = 29; d >= 0; d--) {
    const day = new Date(now.getTime() - d * 86400000);
    counts[day.toISOString().slice(0, 10)] = 0;
  }
  for (const b of backups) {
    const dk = b.date.slice(0, 10);
    if (dk in counts) counts[dk]++;
  }
  const sparkData = Object.keys(counts)
    .sort()
    .map((k) => counts[k]);

  // Aggregate stats
  const totalFiles = backups.reduce(
    (sum, b) => sum + (b.fileCount ?? 0),
    0
  );

  // Last backup per category
  const lastBackupByCategory = getLastBackupByCategory(backups);
  // Remove "all" — it's a meta-category, the individual categories within it
  // are what matters. But if "all" is the only one, keep it.
  const categoryEntries = Object.entries(lastBackupByCategory)
    .filter(([name]) => name !== "all" || Object.keys(lastBackupByCategory).length === 1)
    .sort((a, b) => {
      // Sort: most recently backed up first
      return new Date(b[1]).getTime() - new Date(a[1]).getTime();
    });

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4CA;</span>{" "}
        {content?.heading ?? "Backup History"}
      </h2>

      {backups.length > 0 && (
        <>
          <CalendarGrid data={counts} />

          <div className="text-xs text-dim mb-2 mt-4">
            {content?.sparklineLabel ?? "Last 30 days"}
          </div>
          <div className="w-full overflow-hidden h-12">
            <Sparkline data={sparkData} width={400} height={50} />
          </div>

          <div className="mt-4" />
          <StatCards
            items={[
              {
                value: String(backups.length),
                label: content?.totalLabel ?? "Recent Backups",
              },
              {
                value: fmtDate(backups[0].date),
                label: content?.latestLabel ?? "Latest",
              },
              {
                value: totalFiles.toLocaleString(),
                label: "Files Backed Up",
              },
              {
                value: String(categoryEntries.length),
                label: "Categories Tracked",
              },
            ]}
          />

          {/* Last backup per category */}
          {categoryEntries.length > 0 && (
            <div className="mt-4">
              <div className="text-xs text-dim mb-2">
                Last Backup by Category
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {categoryEntries.map(([name, date]) => {
                  const age = ageLabel(date);
                  const color = CATEGORY_COLORS[name] || "var(--accent)";
                  return (
                    <div
                      key={name}
                      className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-2 text-xs"
                    >
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ background: age.color }}
                      />
                      <span
                        className="font-medium shrink-0"
                        style={{ color }}
                      >
                        {categoryLabel(name)}
                      </span>
                      <span className="text-dim ml-auto tabular-nums shrink-0">
                        {age.text}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Interactive timeline */}
          <BackupTimeline backups={backups} />
        </>
      )}
    </section>
  );
}
