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
  const [repo, setRepo] = useState("");
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    async function fetchRepos() {
      try {
        const res = await fetch("/api/github/repos");
        if (res.ok) {
          const data = await res.json();
          setRepos(data);
        }
      } catch {
        // Fall back to manual input
      } finally {
        setLoadingRepos(false);
      }
    }
    fetchRepos();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
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

  return (
    <form onSubmit={handleSubmit}>
      {loadingRepos ? (
        <div className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-dim">
          {content?.loadingText ?? "Loading repositories..."}
        </div>
      ) : repos.length > 0 ? (
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
              {r.full_name} {r.private ? "🔒" : ""}
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
    </form>
  );
}
