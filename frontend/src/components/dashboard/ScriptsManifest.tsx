import { parseScriptsManifest } from "@/lib/utils";

interface ScriptsManifestProps {
  raw: string | null;
}

export function ScriptsManifest({ raw }: ScriptsManifestProps) {
  const { columns, rows } = parseScriptsManifest(raw);

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4DC;</span> Scripts
      </h2>
      {rows.length > 0 ? (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="text-left text-sub font-semibold px-2 py-1 border-b border-border"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="px-2 py-1 text-foreground border-b border-border last:border-b-0"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sub text-sm">
          Run <code>backup.sh scripts</code> to generate manifest.
        </p>
      )}
    </section>
  );
}
