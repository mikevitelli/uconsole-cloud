import { StatusGrid } from "@/components/viz/StatusGrid";
import { COVERAGE_ITEMS } from "@/lib/backup-config";
import type { BackupEntry } from "@/lib/types";
import { ageLabel, freshnessColor, getLastBackupByCategory } from "@/lib/utils";

interface BackupCoverageContent {
  heading?: string;
}

interface BackupCoverageProps {
  backups: BackupEntry[];
  totalPackages: number;
  extensionCount: number;
  hasScripts: boolean;
  content?: BackupCoverageContent;
}


export function BackupCoverage({
  backups,
  totalPackages,
  extensionCount,
  hasScripts,
  content,
}: BackupCoverageProps) {
  // Find last backup date for each category
  const lastBackupByCategory = getLastBackupByCategory(backups);
  // "all" means every category was backed up — expand to individual items
  if (lastBackupByCategory["all"]) {
    for (const item of COVERAGE_ITEMS) {
      if (item.backupCategory && !lastBackupByCategory[item.backupCategory]) {
        lastBackupByCategory[item.backupCategory] = lastBackupByCategory["all"];
      }
    }
  }

  const items = COVERAGE_ITEMS.map((item) => {
    const lastDate = lastBackupByCategory[item.backupCategory] ?? null;

    // File-check based items (have extra data beyond just the date)
    if (item.fileCheck === "packages") {
      return {
        name: item.name,
        color: totalPackages > 0 ? freshnessColor(lastDate) : "var(--red)",
        detail:
          totalPackages > 0
            ? `${totalPackages} pkgs${lastDate ? " · " + ageLabel(lastDate).text : ""}`
            : "missing",
      };
    }
    if (item.fileCheck === "extensions") {
      return {
        name: item.name,
        color: extensionCount > 0 ? freshnessColor(lastDate) : "var(--dim)",
        detail:
          extensionCount > 0
            ? `${extensionCount} ext${lastDate ? " · " + ageLabel(lastDate).text : ""}`
            : "none tracked",
      };
    }
    if (item.fileCheck === "scripts") {
      return {
        name: item.name,
        color: hasScripts ? freshnessColor(lastDate) : "var(--yellow)",
        detail: hasScripts
          ? lastDate
            ? ageLabel(lastDate).text
            : "present"
          : "no manifest",
      };
    }

    return {
      name: item.name,
      color: freshnessColor(lastDate),
      detail: lastDate ? ageLabel(lastDate).text : "never",
    };
  });

  // Count coverage states
  const covered = items.filter((i) => i.detail !== "never" && i.detail !== "missing" && i.detail !== "none tracked" && i.detail !== "no manifest").length;

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-1 flex items-center gap-2">
        <span>&#x1F6E1;</span>{" "}
        {content?.heading ?? "Backup Coverage"}
      </h2>
      <div className="text-[11px] text-sub mb-3">
        {covered}/{items.length} categories covered
      </div>
      <StatusGrid items={items} />
    </section>
  );
}
