import { StatCards } from "@/components/viz/StatCards";
import { fmtDate, fmtSize } from "@/lib/utils";
import type { RepoInfo } from "@/lib/types";

interface RepoStatsProps {
  info: RepoInfo;
}

export function RepoStats({ info }: RepoStatsProps) {
  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x2699;</span> Repository
      </h2>
      <StatCards
        items={[
          { value: fmtSize(info.size), label: "Repo Size" },
          { value: info.default_branch || "main", label: "Branch" },
          { value: fmtDate(info.pushed_at), label: "Last Push" },
          { value: info.visibility || "private", label: "Visibility" },
        ]}
      />
    </section>
  );
}
