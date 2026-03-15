import { StatusGrid } from "@/components/viz/StatusGrid";

interface BackupCoverageProps {
  totalPackages: number;
  extensionCount: number;
  hasScripts: boolean;
}

export function BackupCoverage({
  totalPackages,
  extensionCount,
  hasScripts,
}: BackupCoverageProps) {
  const items = [
    { name: "Shell configs", color: "var(--green)", detail: "symlinked" },
    { name: "System configs", color: "var(--green)", detail: "copied" },
    {
      name: "Package manifests",
      color: totalPackages > 0 ? "var(--green)" : "var(--red)",
      detail: `${totalPackages} pkgs`,
    },
    {
      name: "Browser",
      color: extensionCount > 0 ? "var(--green)" : "var(--yellow)",
      detail: `${extensionCount} ext`,
    },
    {
      name: "Scripts",
      color: hasScripts ? "var(--green)" : "var(--yellow)",
      detail: hasScripts ? "manifest" : "missing",
    },
    { name: "Desktop (dconf)", color: "var(--green)", detail: "backed up" },
    { name: "Git/SSH config", color: "var(--green)", detail: "symlinked" },
    { name: "GitHub CLI", color: "var(--green)", detail: "backed up" },
  ];

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F6E1;</span> Backup Coverage
      </h2>
      <StatusGrid items={items} />
    </section>
  );
}
