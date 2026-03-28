// Shared backup coverage configuration
// Used by BackupCoverage (rendering) and SystemSummary (restore-readiness scoring)

export interface CoverageItem {
  name: string;
  backupCategory: string; // matches against backup commit categories
  fileCheck?: "packages" | "extensions" | "scripts"; // also derived from file data
}

export const COVERAGE_ITEMS: CoverageItem[] = [
  { name: "Shell configs", backupCategory: "dotfiles" },
  { name: "System configs", backupCategory: "system" },
  { name: "Package manifests", backupCategory: "packages", fileCheck: "packages" },
  { name: "Browser", backupCategory: "browser", fileCheck: "extensions" },
  { name: "Scripts", backupCategory: "scripts", fileCheck: "scripts" },
  { name: "Desktop (dconf)", backupCategory: "desktop" },
  { name: "Git/SSH config", backupCategory: "git" },
  { name: "GitHub CLI", backupCategory: "gh" },
];
