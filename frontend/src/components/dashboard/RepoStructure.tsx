import type { TreeEntry } from "@/lib/types";

interface RepoStructureProps {
  tree: TreeEntry[];
}

export function RepoStructure({ tree }: RepoStructureProps) {
  const dirs = tree
    .filter((t) => t.type === "tree")
    .sort((a, b) => a.path.localeCompare(b.path));
  const files = tree
    .filter((t) => t.type === "blob")
    .sort((a, b) => a.path.localeCompare(b.path));

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4C1;</span> Repository Structure
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
        return (
          <div key={f.path} className="flex items-center gap-1.5 py-0.5 text-xs">
            <span className="text-dim shrink-0">&#x1F4C4;</span>
            <span className="text-foreground">{f.path}</span>
            <span className="text-dim ml-auto tabular-nums">{sz}</span>
          </div>
        );
      })}
    </section>
  );
}
