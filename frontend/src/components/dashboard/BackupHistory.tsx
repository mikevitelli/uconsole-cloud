import { Sparkline } from "@/components/viz/Sparkline";
import { StatCards } from "@/components/viz/StatCards";
import { CalendarGrid } from "@/components/viz/CalendarGrid";
import { fmtDate } from "@/lib/utils";
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

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4CA;</span>{" "}
        {content?.heading ?? "Backup History"}
      </h2>

      {backups.length > 0 && (
        <>
          <CalendarGrid data={counts} />

          <div className="text-xs text-dim mb-2 mt-3">
            {content?.sparklineLabel ?? "Last 30 days"}
          </div>
          <div className="w-full overflow-hidden h-12">
            <Sparkline data={sparkData} width={400} height={50} />
          </div>

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
            ]}
          />

          <div className="max-h-48 overflow-y-auto">
            {backups.slice(0, 5).map((b) => (
              <div
                key={b.sha}
                className="flex items-start gap-2.5 py-1.5 border-b border-[#1c2129] last:border-b-0 text-xs"
              >
                <span className="w-2 h-2 rounded-full bg-accent shrink-0 mt-1.5" />
                <div className="flex-1">
                  <div className="text-foreground">{b.message}</div>
                  <div>
                    <span className="text-dim text-sm">
                      {fmtDate(b.date)}
                    </span>{" "}
                    <span className="text-dim font-mono text-sm">
                      {b.sha.substring(0, 7)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
