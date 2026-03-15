import type { TreeEntry } from "@/lib/types";

interface RepoStructureContent {
  heading?: string;
}

interface RepoStructureProps {
  tree: TreeEntry[];
  content?: RepoStructureContent;
}

export function RepoStructure({ tree, content }: RepoStructureProps) {
  const dirs = tree
    .filter((t) => t.type === "tree")
    .sort((a, b) => a.path.localeCompare(b.path));
  const files = tree
    .filter((t) => t.type === "blob")
    .sort((a, b) => a.path.localeCompare(b.path));
  const maxSize = Math.max(...files.map((f) => f.size || 0), 1);

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4C1;</span>{" "}
        {content?.heading ?? "Repository Structure"}
      </h2>
      {dirs.map((d) => (
        <div key={d.path} className="flex items-center gap-1.5 py-0.5 text-xs">
          <span className="text-dim shrink-0">&#x1F4C1;</span>
          <span className="text-foreground">{d.path}/</span>
        </div>
      ))}
      {files.map((f) => {
        const sz = f.size
          ? f.size > 1024
            ? (f.size / 1024).toFixed(1) + "K"
            : f.size + "B"
          : "";
        const barWidth = f.size ? Math.round((f.size / maxSize) * 60) : 0;
        return (
          <div key={f.path} className="flex items-center gap-1.5 py-0.5 text-xs">
            <span className="text-dim shrink-0">&#x1F4C4;</span>
            <span className="text-foreground">{f.path}</span>
            <span className="ml-auto flex items-center gap-1.5">
              {barWidth > 0 && (
                <span
                  className="inline-block h-1.5 rounded-full bg-accent opacity-40"
                  style={{ width: `${barWidth}px` }}
                />
              )}
              <span className="text-dim tabular-nums min-w-[40px] text-right">
                {sz}
              </span>
            </span>
          </div>
        );
      })}
    </section>
  );
}
