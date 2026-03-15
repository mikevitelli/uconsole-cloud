export interface PackageData {
  manager: string;
  packages: string[];
}

export interface CommitData {
  sha: string;
  message: string;
  date: string;
}

export interface TreeEntry {
  path: string;
  type: "tree" | "blob";
  size?: number;
}

export interface RepoInfo {
  size: number;
  default_branch: string;
  pushed_at: string;
  visibility: string;
}

export interface ScriptEntry {
  name: string;
  size: string;
  description: string;
}

export interface BackupItem {
  name: string;
  color: string;
  detail: string;
}

export interface UserSettings {
  repo: string;
  linkedAt: string;
}

export interface AptCategory {
  name: string;
  color: string;
  packages: string[];
}
