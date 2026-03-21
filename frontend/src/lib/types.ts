export interface PackageData {
  manager: string;
  packages: string[];
}

export interface BackupEntry {
  sha: string;
  message: string;
  date: string;
  categories: string[];
  fileCount: number | null;
  htmlUrl: string;
}

export interface CommitFileChange {
  filename: string;
  status: "added" | "removed" | "modified" | "renamed";
  additions: number;
  deletions: number;
}

export interface CommitDetail {
  sha: string;
  stats: { total: number; additions: number; deletions: number };
  files: CommitFileChange[];
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
  deviceToken?: string;
}

export interface GitHubCommit {
  sha: string;
  html_url: string;
  commit: {
    message: string;
    author: { date: string };
  };
}

export interface AptCategory {
  name: string;
  color: string;
  packages: string[];
}
