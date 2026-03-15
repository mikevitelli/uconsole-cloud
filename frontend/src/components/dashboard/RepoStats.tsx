import { StatCards } from "@/components/viz/StatCards";
import { fmtDate, fmtSize } from "@/lib/utils";
import type { RepoInfo } from "@/lib/types";

interface RepoStatsContent {
  heading?: string;
  sizeLabel?: string;
  branchLabel?: string;
  lastPushLabel?: string;
  visibilityLabel?: string;
}

interface RepoStatsProps {
  info: RepoInfo;
  content?: RepoStatsContent;
}

export function RepoStats({ info, content }: RepoStatsProps) {
  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x2699;</span>{" "}
        {content?.heading ?? "Repository"}
      </h2>
      <StatCards
        items={[
          {
            value: fmtSize(info.size),
            label: content?.sizeLabel ?? "Repo Size",
          },
          {
            value: info.default_branch || "main",
            label: content?.branchLabel ?? "Branch",
          },
          {
            value: fmtDate(info.pushed_at),
            label: content?.lastPushLabel ?? "Last Push",
          },
          {
            value: info.visibility || "private",
            label: content?.visibilityLabel ?? "Visibility",
          },
        ]}
      />
    </section>
  );
}
