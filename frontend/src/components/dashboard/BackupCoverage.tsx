import { StatusGrid } from "@/components/viz/StatusGrid";
import type { BackupEntry } from "@/lib/types";
import { categoryLabel } from "@/lib/utils";

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
const COVERAGE_ITEMS: {
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

function ageText(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

function freshnessColor(iso: string | null): string {
  if (!iso) return "var(--red)";
  const days = Math.floor(
    (Date.now() - new Date(iso).getTime()) / 86400000
  );
  if (days < 7) return "var(--green)";
  if (days < 14) return "var(--yellow)";
  return "var(--red)";
}

export function BackupCoverage({
  backups,
  totalPackages,
  extensionCount,
  hasScripts,
  content,
}: BackupCoverageProps) {
  // Find last backup date for each category
  const lastBackupByCategory: Record<string, string> = {};
  for (const b of backups) {
    for (const c of b.categories) {
      if (!lastBackupByCategory[c]) {
        lastBackupByCategory[c] = b.date;
      }
    }
    // "all" means every category was backed up
    if (b.categories.includes("all")) {
      for (const item of COVERAGE_ITEMS) {
        if (item.backupCategory && !lastBackupByCategory[item.backupCategory]) {
          lastBackupByCategory[item.backupCategory] = b.date;
        }
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
            ? `${totalPackages} pkgs${lastDate ? " · " + ageText(lastDate) : ""}`
            : "missing",
      };
    }
    if (item.fileCheck === "extensions") {
      return {
        name: item.name,
        color: extensionCount > 0 ? freshnessColor(lastDate) : "var(--dim)",
        detail:
          extensionCount > 0
            ? `${extensionCount} ext${lastDate ? " · " + ageText(lastDate) : ""}`
            : "none tracked",
      };
    }
    if (item.fileCheck === "scripts") {
      return {
        name: item.name,
        color: hasScripts ? freshnessColor(lastDate) : "var(--yellow)",
        detail: hasScripts
          ? lastDate
            ? ageText(lastDate)
            : "present"
          : "no manifest",
      };
    }

    return {
      name: item.name,
      color: freshnessColor(lastDate),
      detail: lastDate ? ageText(lastDate) : "never",
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
