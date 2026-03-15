export function parseLines(text: string | null): string[] {
  if (!text) return [];
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function fmtSize(kb: number): string {
  return kb > 1024 ? (kb / 1024).toFixed(1) + " MB" : kb + " KB";
}

export function parseScriptsManifest(
  text: string | null
): { columns: string[]; rows: string[][] } {
  const lines = parseLines(text);
  if (!lines.length) return { columns: [], rows: [] };

  const delim = lines[0].includes("\t") ? "\t" : /\s{2,}/;
  const columns = lines[0]
    .split(delim)
    .map((c) => c.trim())
    .filter(Boolean);

  const rows: string[][] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i]
      .split(delim)
      .map((c) => c.trim())
      .filter(Boolean);
    if (cols[0] && /^[-=\u2500]+$/.test(cols[0])) continue;
    if (cols.length) rows.push(cols);
  }

  return { columns, rows };
}
