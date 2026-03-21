import { StatusGrid } from "@/components/viz/StatusGrid";
import type { BackupEntry } from "@/lib/types";
import { categoryLabel, ageLabel, freshnessColor, getLastBackupByCategory } from "@/lib/utils";

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

// Map backup categories to coverage items
// Some coverage items map directly to backup categories,
// others are derived from file existence checks
export const COVERAGE_ITEMS: {
  name: string;
  backupCategory: string; // matches against backup commit categories
  fileCheck?: "packages" | "extensions" | "scripts"; // also derived from file data
}[] = [
  { name: "Shell configs", backupCategory: "dotfiles" },
  { name: "System configs", backupCategory: "system" },
  { name: "Package manifests", backupCategory: "packages", fileCheck: "packages" },
  { name: "Browser", backupCategory: "browser", fileCheck: "extensions" },
  { name: "Scripts", backupCategory: "scripts", fileCheck: "scripts" },
  { name: "Desktop (dconf)", backupCategory: "desktop" },
  { name: "Git/SSH config", backupCategory: "git" },
  { name: "GitHub CLI", backupCategory: "gh" },
];


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

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F6E1;</span>{" "}
        {content?.heading ?? "Backup Coverage"}
      </h2>
      <StatusGrid items={items} />
    </section>
  );
}
