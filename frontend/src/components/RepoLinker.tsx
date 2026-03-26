"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface Repo {
  full_name: string;
  private: boolean;
}

interface RepoLinkerContent {
  placeholder?: string;
  selectPlaceholder?: string;
  buttonText?: string;
  loadingButton?: string;
  loadingText?: string;
}

interface RepoLinkerProps {
  content?: RepoLinkerContent;
}

export function RepoLinker({ content }: RepoLinkerProps) {
  const [mode, setMode] = useState<"auto" | "select" | "create">("auto");
  const [repo, setRepo] = useState("");
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [autoDetected, setAutoDetected] = useState<Repo | null>(null);
  const router = useRouter();

  // Create mode state
  const [repoName, setRepoName] = useState("uconsole");
  const [isPrivate, setIsPrivate] = useState(true);
  const [username, setUsername] = useState("");

  useEffect(() => {
    async function fetchRepos() {
      try {
        const res = await fetch("/api/github/repos");
        if (res.ok) {
          const data: Repo[] = await res.json();
          setRepos(data);
          if (data.length > 0) {
            setUsername(data[0].full_name.split("/")[0]);
          }

          // Auto-detect: look for a repo named "uconsole"
          const uconsoleRepo = data.find((r) => {
            const name = r.full_name.split("/")[1];
            return name === "uconsole";
          });

          if (uconsoleRepo) {
            setAutoDetected(uconsoleRepo);
            setRepo(uconsoleRepo.full_name);
            setMode("auto");
          } else {
            // No uconsole repo found — default to create mode
            setMode("create");
          }
        } else {
          setMode("create");
        }
      } catch {
        setMode("create");
      } finally {
        setLoadingRepos(false);
      }
    }
    fetchRepos();
  }, []);

  useEffect(() => {
    if (mode === "create" && !username) {
      fetch("/api/github/user")
        .then((r) => r.json())
        .then((d) => d.login && setUsername(d.login))
        .catch(() => {});
    }
  }, [mode, username]);

  async function handleLink(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repo.trim() }),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.error || "Failed to link repository");
        return;
      }

      router.refresh();
    } catch {
      setError("Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/github/repos/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: repoName.trim(), private: isPrivate }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Failed to create repository");
        return;
      }

      router.refresh();
    } catch {
      setError("Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  if (loadingRepos) {
    return (
      <div className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-dim">
        {content?.loadingText ?? "Loading repositories..."}
      </div>
    );
  }

  // Auto-detected uconsole repo — one-click link
  if (mode === "auto" && autoDetected) {
    return (
      <div>
        <p className="text-sm text-sub mb-3">
          Found your backup repo:{" "}
          <span className="font-mono text-foreground">{autoDetected.full_name}</span>
          {autoDetected.private ? " \uD83D\uDD12" : ""}
        </p>
        {error && <p className="text-red text-xs mb-2">{error}</p>}
        <form onSubmit={handleLink}>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent text-[#0d1117] font-semibold rounded-lg px-4 py-2.5 text-sm hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Linking..." : "Link this repo"}
          </button>
        </form>
        <button
          type="button"
          onClick={() => { setMode("select"); setRepo(""); setError(""); }}
          className="w-full mt-2 text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
        >
          Use a different repo
        </button>
      </div>
    );
  }

  if (mode === "create") {
    return (
      <form onSubmit={handleCreate}>
        <div className="flex items-center gap-1 mb-3">
          <span className="text-sub text-sm font-mono">
            {username ? `${username}/` : ""}
          </span>
          <input
            type="text"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value.replace(/[^a-zA-Z0-9_.-]/g, ""))}
            placeholder="uconsole"
            className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono text-foreground placeholder:text-dim focus:outline-none focus:border-accent"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-sub mb-3 cursor-pointer">
          <input
            type="checkbox"
            checked={isPrivate}
            onChange={(e) => setIsPrivate(e.target.checked)}
            className="accent-accent"
          />
          Private repository
        </label>
        {error && <p className="text-red text-xs mb-2">{error}</p>}
        <button
          type="submit"
          disabled={loading || !repoName.trim()}
          className="w-full bg-accent text-[#0d1117] font-semibold rounded-lg px-4 py-2.5 text-sm hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Creating..." : "Create & Link"}
        </button>
        <button
          type="button"
          onClick={() => { setMode("select"); setError(""); }}
          className="w-full mt-2 text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
        >
          Link an existing repo instead
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={handleLink}>
      {repos.length > 0 ? (
        <select
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        >
          <option value="">
            {content?.selectPlaceholder ?? "Select a repository"}
          </option>
          {repos.map((r) => (
            <option key={r.full_name} value={r.full_name}>
              {r.full_name} {r.private ? "\uD83D\uDD12" : ""}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder={content?.placeholder ?? "owner/repo"}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-dim focus:outline-none focus:border-accent"
        />
      )}
      {error && <p className="text-red text-xs mt-2">{error}</p>}
      <button
        type="submit"
        disabled={loading || !repo.trim()}
        className="w-full mt-3 bg-accent text-[#0d1117] font-semibold rounded-lg px-4 py-2.5 text-sm hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading
          ? (content?.loadingButton ?? "Linking...")
          : (content?.buttonText ?? "Link Repository")}
      </button>
      <button
        type="button"
        onClick={() => { setMode("create"); setError(""); }}
        className="w-full mt-2 text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
      >
        or create a new repo
      </button>
    </form>
  );
}
