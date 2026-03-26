import { parseScriptsManifest } from "@/lib/utils";

interface ScriptsManifestContent {
  heading?: string;
  emptyState?: string;
}

interface ScriptsManifestProps {
  raw: string | null;
  content?: ScriptsManifestContent;
}

export function ScriptsManifest({ raw, content }: ScriptsManifestProps) {
  const { columns, rows } = parseScriptsManifest(raw);

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4DC;</span>{" "}
        {content?.heading ?? "Scripts"}
      </h2>
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="text-left text-sub font-semibold px-2.5 py-1.5 border-b border-border whitespace-nowrap text-[11px] uppercase tracking-wide"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="hover:bg-background/50 transition-colors">
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className="px-2.5 py-1.5 text-foreground border-b border-border last:border-b-0 whitespace-nowrap sm:whitespace-normal"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sub text-sm">
          {content?.emptyState ??
            "Run backup.sh scripts to generate manifest."}
        </p>
      )}
    </section>
  );
}
