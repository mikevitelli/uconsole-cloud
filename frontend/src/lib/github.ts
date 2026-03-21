const GITHUB_API = "https://api.github.com";
const GITHUB_RAW = "https://raw.githubusercontent.com";

export class GitHubError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "GitHubError";
  }
}

async function githubFetch(
  url: string,
  token: string,
  isJson = true
): Promise<unknown | null> {
  const res = await fetch(url, {
    headers: {
      Authorization: `token ${token}`,
      Accept: "application/vnd.github.v3+json",
      "User-Agent": "uconsole-cloud",
    },
    next: { revalidate: 60 },
  });
  if (res.status === 401) throw new GitHubError(401, "GitHub token expired");
  if (res.status === 403) throw new GitHubError(403, "GitHub rate limit exceeded");
  if (!res.ok) return null;
  return isJson ? res.json() : res.text();
}

export async function fetchRepoInfo(
  token: string,
  repo: string
) {
  return githubFetch(`${GITHUB_API}/repos/${repo}`, token);
}

export async function fetchCommits(
  token: string,
  repo: string,
  perPage = 50
) {
  return githubFetch(
    `${GITHUB_API}/repos/${repo}/commits?per_page=${perPage}`,
    token
  );
}

export async function fetchTree(
  token: string,
  repo: string,
  branch = "main"
) {
  return githubFetch(
    `${GITHUB_API}/repos/${repo}/git/trees/${branch}`,
    token
  );
}

export async function fetchRawFile(
  token: string,
  repo: string,
  path: string,
  branch = "main"
): Promise<string | null> {
  return githubFetch(
    `${GITHUB_RAW}/${repo}/${branch}/${path}`,
    token,
    false
  ) as Promise<string | null>;
}

const PACKAGE_FILES: Record<string, string> = {
  APT: "packages/apt-manual.txt",
  Flatpak: "packages/flatpak.txt",
  Snap: "packages/snap.txt",
  Cargo: "packages/cargo.txt",
  pip: "packages/pip-user.txt",
  ClockworkPi: "packages/clockworkpi.txt",
};

export async function fetchAllPackages(
  token: string,
  repo: string
): Promise<Record<string, string[]>> {
  const entries = Object.entries(PACKAGE_FILES);
  const results = await Promise.all(
    entries.map(([, path]) => fetchRawFile(token, repo, path))
  );

  const packages: Record<string, string[]> = {};
  entries.forEach(([manager], i) => {
    const text = results[i];
    packages[manager] = text
      ? text
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l && !l.startsWith("#"))
      : [];
  });
  return packages;
}

export async function fetchExtensions(
  token: string,
  repo: string
): Promise<string[]> {
  const text = await fetchRawFile(token, repo, "config/chromium/extensions.txt");
  if (!text) return [];
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
}

export async function fetchScriptsManifest(
  token: string,
  repo: string
): Promise<string | null> {
  return fetchRawFile(token, repo, "scripts/scripts-manifest.txt");
}

export async function fetchCommitDetail(
  token: string,
  repo: string,
  sha: string
): Promise<{
  sha: string;
  stats: { total: number; additions: number; deletions: number };
  files: {
    filename: string;
    status: string;
    additions: number;
    deletions: number;
  }[];
} | null> {
  const data = (await githubFetch(
    `${GITHUB_API}/repos/${repo}/commits/${sha}`,
    token
  )) as {
    sha: string;
    stats: { total: number; additions: number; deletions: number };
    files: {
      filename: string;
      status: string;
      additions: number;
      deletions: number;
    }[];
  } | null;
  if (!data) return null;
  return {
    sha: data.sha,
    stats: data.stats,
    files: (data.files ?? []).map((f) => ({
      filename: f.filename,
      status: f.status,
      additions: f.additions,
      deletions: f.deletions,
    })),
  };
}

export async function validateUconsoleRepo(
  token: string,
  repo: string
): Promise<boolean> {
  const apt = await fetchRawFile(token, repo, "packages/apt-manual.txt");
  return apt !== null;
}
