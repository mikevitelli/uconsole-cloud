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

export function ageLabel(iso: string): { text: string; color: string } {
  const days = daysSince(iso);
  if (days === 0) return { text: "today", color: "var(--green)" };
  if (days === 1) return { text: "yesterday", color: "var(--green)" };
  if (days < 7) return { text: `${days}d ago`, color: "var(--green)" };
  if (days < 14) return { text: `${days}d ago`, color: "var(--yellow)" };
  return { text: `${days}d ago`, color: "var(--red)" };
}

export function freshnessColor(iso: string | null): string {
  if (!iso) return "var(--red)";
  const days = daysSince(iso);
  if (days < 7) return "var(--green)";
  if (days < 14) return "var(--yellow)";
  return "var(--red)";
}

export function getLastBackupByCategory(
  backups: { categories: string[]; date: string }[]
): Record<string, string> {
  const result: Record<string, string> = {};
  for (const b of backups) {
    for (const c of b.categories) {
      if (!result[c]) result[c] = b.date;
    }
  }
  return result;
}

export function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export function fmtBytes(bytes: number): string {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + "M";
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + "K";
  return bytes + "B";
}

export const CATEGORY_COLORS: Record<string, string> = {
  all: "#58a6ff",
  packages: "#3fb950",
  system: "#f85149",
  config: "#d29922",
  desktop: "#bc8cff",
  browser: "#79c0ff",
  git: "#56d364",
  scripts: "#e3b341",
  dotfiles: "#ff7b72",
  gh: "#d2a8ff",
  retropie: "#f778ba",
  emulators: "#ffa657",
  drivers: "#a5d6ff",
};

export const CATEGORY_LABELS: Record<string, string> = {
  all: "all",
  packages: "packages",
  system: "system",
  config: "config",
  desktop: "desktop",
  browser: "browser",
  git: "git config",
  scripts: "scripts",
  dotfiles: "dotfiles",
  gh: "GitHub CLI",
  retropie: "RetroPie",
  emulators: "emulators",
  drivers: "drivers",
};

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] || key;
}

const BACKUP_CATEGORIES_RE = /^backup\(([^)]+)\)/;
const BACKUP_PLAIN_RE = /^backup:/;
const BACKUP_FILES_RE = /(\d+)\s+file\(s\)/;

export function parseBackupMessage(message: string): {
  categories: string[];
  fileCount: number | null;
} {
  const firstLine = message.split("\n")[0];
  const fileMatch = firstLine.match(BACKUP_FILES_RE);

  // Format: backup(category1, category2) N file(s)
  const catMatch = firstLine.match(BACKUP_CATEGORIES_RE);
  if (catMatch) {
    return {
      categories: catMatch[1].split(",").map((c) => c.trim()),
      fileCount: fileMatch ? parseInt(fileMatch[1], 10) : null,
    };
  }

  // Format: backup: 2026-03-14 23:57 — N file(s)
  if (BACKUP_PLAIN_RE.test(firstLine)) {
    return {
      categories: ["all"],
      fileCount: fileMatch ? parseInt(fileMatch[1], 10) : null,
    };
  }

  return { categories: [], fileCount: null };
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
