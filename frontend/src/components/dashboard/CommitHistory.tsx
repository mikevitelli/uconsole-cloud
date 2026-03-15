import { Sparkline } from "@/components/viz/Sparkline";
import { StatCards } from "@/components/viz/StatCards";
import { CalendarGrid } from "@/components/viz/CalendarGrid";
import { fmtDate } from "@/lib/utils";
import type { CommitData } from "@/lib/types";

interface CommitHistoryContent {
  heading?: string;
  sparklineLabel?: string;
  totalLabel?: string;
  latestLabel?: string;
}

interface CommitHistoryProps {
  commits: CommitData[];
  content?: CommitHistoryContent;
}

export function CommitHistory({ commits, content }: CommitHistoryProps) {
  // Build sparkline data for last 30 days
  const counts: Record<string, number> = {};
  const now = new Date();
  for (let d = 29; d >= 0; d--) {
    const day = new Date(now.getTime() - d * 86400000);
    counts[day.toISOString().slice(0, 10)] = 0;
  }
  for (const c of commits) {
    const dk = c.date.slice(0, 10);
    if (dk in counts) counts[dk]++;
  }
  const sparkData = Object.keys(counts)
    .sort()
    .map((k) => counts[k]);

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4CA;</span>{" "}
        {content?.heading ?? "Commit History"}
      </h2>

      {commits.length > 0 && (
        <>
          <CalendarGrid data={counts} />

          <div className="text-[0.7rem] text-dim mb-2 mt-3">
            {content?.sparklineLabel ?? "Last 30 days"}
          </div>
          <Sparkline data={sparkData} width={400} height={50} />

          <StatCards
            items={[
              {
                value: String(commits.length),
                label: content?.totalLabel ?? "Recent Commits",
              },
              {
                value: fmtDate(commits[0].date),
                label: content?.latestLabel ?? "Latest",
              },
            ]}
          />

          <div className="max-h-[200px] overflow-y-auto">
            {commits.slice(0, 5).map((c) => (
              <div
                key={c.sha}
                className="flex items-start gap-2.5 py-1.5 border-b border-[#1c2129] last:border-b-0 text-xs"
              >
                <span className="w-2 h-2 rounded-full bg-accent shrink-0 mt-1.5" />
                <div className="flex-1">
                  <div className="text-foreground">{c.message}</div>
                  <div>
                    <span className="text-dim text-[0.85em]">
                      {fmtDate(c.date)}
                    </span>{" "}
                    <span className="text-dim font-mono text-[0.85em]">
                      {c.sha.substring(0, 7)}
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
