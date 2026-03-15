import { StatusGrid } from "@/components/viz/StatusGrid";

interface BackupCoverageContent {
  heading?: string;
  items?: { key?: string; name?: string; defaultDetail?: string }[];
}

interface BackupCoverageProps {
  totalPackages: number;
  extensionCount: number;
  hasScripts: boolean;
  content?: BackupCoverageContent;
}

const DEFAULT_ITEMS: { key: string; name: string; defaultDetail: string }[] = [
  { key: "shell", name: "Shell configs", defaultDetail: "symlinked" },
  { key: "system", name: "System configs", defaultDetail: "copied" },
  { key: "packages", name: "Package manifests", defaultDetail: "" },
  { key: "browser", name: "Browser", defaultDetail: "" },
  { key: "scripts", name: "Scripts", defaultDetail: "" },
  { key: "desktop", name: "Desktop (dconf)", defaultDetail: "backed up" },
  { key: "gitssh", name: "Git/SSH config", defaultDetail: "symlinked" },
  { key: "ghcli", name: "GitHub CLI", defaultDetail: "backed up" },
];

function getItemByKey(
  contentItems: BackupCoverageContent["items"],
  key: string
) {
  return contentItems?.find((i) => i.key === key);
}

export function BackupCoverage({
  totalPackages,
  extensionCount,
  hasScripts,
  content,
}: BackupCoverageProps) {
  const dynamicDetails: Record<string, () => { color: string; detail: string }> =
    {
      packages: () => ({
        color: totalPackages > 0 ? "var(--green)" : "var(--red)",
        detail: `${totalPackages} pkgs`,
      }),
      browser: () => ({
        color: extensionCount > 0 ? "var(--green)" : "var(--yellow)",
        detail: `${extensionCount} ext`,
      }),
      scripts: () => ({
        color: hasScripts ? "var(--green)" : "var(--yellow)",
        detail: hasScripts ? "manifest" : "missing",
      }),
    };

  const items = DEFAULT_ITEMS.map((def) => {
    const override = getItemByKey(content?.items, def.key);
    const name = override?.name ?? def.name;
    const dynamic = dynamicDetails[def.key];

    if (dynamic) {
      return { name, ...dynamic() };
    }

    return {
      name,
      color: "var(--green)",
      detail: override?.defaultDetail ?? def.defaultDetail,
    };
  });

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F6E1;</span>{" "}
        {content?.heading ?? "Backup Coverage"}
      </h2>
      <StatusGrid items={items} />
    </section>
  );
}
