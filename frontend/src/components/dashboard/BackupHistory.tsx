import { Sparkline } from "@/components/viz/Sparkline";
import { StatCards } from "@/components/viz/StatCards";
import { CalendarGrid } from "@/components/viz/CalendarGrid";
import { BackupTimeline } from "@/components/dashboard/BackupTimeline";
import { fmtDate, ageLabel, getLastBackupByCategory, CATEGORY_COLORS, categoryLabel } from "@/lib/utils";
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
  const now = new Date();

  // Build calendar grid data for full year (all backups)
  const calendarCounts: Record<string, number> = {};
  for (const b of backups) {
    const dk = b.date.slice(0, 10);
    calendarCounts[dk] = (calendarCounts[dk] || 0) + 1;
  }

  // Build sparkline data for last 30 days
  const sparkCounts: Record<string, number> = {};
  for (let d = 29; d >= 0; d--) {
    const day = new Date(now.getTime() - d * 86400000);
    sparkCounts[day.toISOString().slice(0, 10)] = 0;
  }
  for (const b of backups) {
    const dk = b.date.slice(0, 10);
    if (dk in sparkCounts) sparkCounts[dk]++;
  }
  const sparkData = Object.keys(sparkCounts)
    .sort()
    .map((k) => sparkCounts[k]);

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
          <div className="bg-background border border-border rounded-lg p-3">
            <div className="text-[11px] text-sub font-medium mb-2 tracking-wide uppercase">
              {content?.sparklineLabel ?? "Last 30 days"}
            </div>
            <CalendarGrid data={calendarCounts} days={30} />
            <div className="mt-3 w-full overflow-hidden h-14">
              <Sparkline data={sparkData} width={440} height={56} />
            </div>
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
              <div className="text-[11px] text-sub font-medium mb-2 tracking-wide uppercase">
                Last Backup by Category
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
                {categoryEntries.map(([name, date]) => {
                  const age = ageLabel(date);
                  const color = CATEGORY_COLORS[name] || "var(--accent)";
                  return (
                    <div
                      key={name}
                      className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
                      style={{ borderLeftWidth: 2, borderLeftColor: color }}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="font-medium truncate" style={{ color }}>
                          {categoryLabel(name)}
                        </div>
                        <div className="text-dim tabular-nums text-[10px]">
                          {age.text}
                        </div>
                      </div>
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: age.color }}
                      />
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
