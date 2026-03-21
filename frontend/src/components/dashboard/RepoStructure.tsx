import type { TreeEntry } from "@/lib/types";
import { fmtBytes } from "@/lib/utils";

interface RepoStructureContent {
  heading?: string;
}

interface RepoStructureProps {
  tree: TreeEntry[];
  content?: RepoStructureContent;
}

const DIR_COLORS = [
  "#3b82f6", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b",
  "#ef4444", "#ec4899", "#6366f1", "#14b8a6", "#f97316",
  "#84cc16", "#a855f7", "#0ea5e9", "#22c55e", "#e11d48",
];


export function RepoStructure({ tree, content }: RepoStructureProps) {
  const dirs = tree
    .filter((t) => t.type === "tree")
    .sort((a, b) => a.path.localeCompare(b.path));
  const files = tree
    .filter((t) => t.type === "blob")
    .sort((a, b) => (b.size || 0) - (a.size || 0));

  // Calculate directory sizes by grouping files
  const dirSizes: Record<string, { size: number; files: number }> = {};
  let rootFileSize = 0;
  let rootFileCount = 0;

  for (const f of files) {
    const parts = f.path.split("/");
    if (parts.length > 1) {
      const dir = parts[0];
      if (!dirSizes[dir]) dirSizes[dir] = { size: 0, files: 0 };
      dirSizes[dir].size += f.size || 0;
      dirSizes[dir].files++;
    } else {
      rootFileSize += f.size || 0;
      rootFileCount++;
    }
  }

  // Add root files as a virtual directory
  if (rootFileCount > 0) {
    dirSizes["."] = { size: rootFileSize, files: rootFileCount };
  }

  // Sort by size descending for treemap
  const sortedDirs = Object.entries(dirSizes)
    .sort(([, a], [, b]) => b.size - a.size);
  const totalSize = sortedDirs.reduce((sum, [, d]) => sum + d.size, 0) || 1;

  // Top files for the detail list
  const topFiles = files.filter((f) => f.size).slice(0, 8);
  const maxFileSize = Math.max(...topFiles.map((f) => f.size || 0), 1);

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4C1;</span>{" "}
        {content?.heading ?? "Repository Structure"}
      </h2>

      {/* Treemap visualization */}
      <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 gap-1 mb-4">
        {sortedDirs.map(([dir, info], i) => {
          const pct = (info.size / totalSize) * 100;
          if (pct < 0.5) return null;
          const color = DIR_COLORS[i % DIR_COLORS.length];
          // Span 1-3 columns based on relative size
          const span = pct > 40 ? 3 : pct > 15 ? 2 : 1;
          return (
            <div
              key={dir}
              className="rounded-lg flex flex-col items-start justify-center transition-opacity hover:opacity-80 px-3 py-2.5"
              style={{
                background: color + "18",
                border: `1px solid ${color}33`,
                gridColumn: `span ${span}`,
              }}
            >
              <span className="text-xs font-semibold truncate w-full" style={{ color }}>
                {dir === "." ? "root" : dir}/
              </span>
              <span className="text-xs text-dim mt-0.5">{fmtBytes(info.size)} &middot; {info.files} file{info.files !== 1 ? "s" : ""}</span>
            </div>
          );
        })}
      </div>

      {/* Directory count + total */}
      <div className="flex items-center gap-3 mb-3 text-xs text-dim">
        <span>{dirs.length} directories</span>
        <span>&middot;</span>
        <span>{files.length} files</span>
        <span>&middot;</span>
        <span>{fmtBytes(totalSize)} total</span>
      </div>

      {/* Largest files bar chart */}
      {topFiles.length > 0 && (
        <div>
          <div className="text-xs text-dim mb-2">Largest Files</div>
          <div className="space-y-1">
            {topFiles.map((f) => {
              const pct = ((f.size || 0) / maxFileSize) * 100;
              const dirPart = f.path.includes("/") ? f.path.split("/")[0] : ".";
              const dirIdx = sortedDirs.findIndex(([d]) => d === dirPart);
              const color = DIR_COLORS[dirIdx >= 0 ? dirIdx % DIR_COLORS.length : 0];
              return (
                <div key={f.path} className="flex items-center gap-2 text-xs">
                  <span className="text-foreground truncate min-w-0 flex-1">{f.path}</span>
                  <div className="w-24 sm:w-32 shrink-0">
                    <div
                      className="h-2 rounded-full"
                      style={{ width: `${pct}%`, background: color, opacity: 0.6 }}
                    />
                  </div>
                  <span className="text-dim tabular-nums w-12 text-right shrink-0">
                    {fmtBytes(f.size || 0)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
