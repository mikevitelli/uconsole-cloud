import { auth, signIn, signOut } from "@/lib/auth";
import { getUserSettings, deleteUserSettings } from "@/lib/redis";
import {
  fetchRepoInfo,
  fetchCommits,
  fetchTree,
  fetchAllPackages,
  fetchExtensions,
  fetchScriptsManifest,
} from "@/lib/github";
import type { CommitData, TreeEntry, RepoInfo } from "@/lib/types";
import { RepoStats } from "@/components/dashboard/RepoStats";
import { CommitHistory } from "@/components/dashboard/CommitHistory";
import { PackageInventory } from "@/components/dashboard/PackageInventory";
import { BrowserExtensions } from "@/components/dashboard/BrowserExtensions";
import { ScriptsManifest } from "@/components/dashboard/ScriptsManifest";
import { BackupCoverage } from "@/components/dashboard/BackupCoverage";
import { RepoStructure } from "@/components/dashboard/RepoStructure";
import { RepoLinker } from "@/components/RepoLinker";
import { redirect } from "next/navigation";

interface GitHubCommit {
  sha: string;
  commit: {
    message: string;
    author: { date: string };
  };
}

export default async function Home() {
  const session = await auth();

  // ── Not signed in ──────────────────────────────────────
  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-card border border-border rounded-xl p-8 max-w-sm w-full text-center">
          <h1 className="text-2xl font-bold text-bright mb-2">
            uConsole Dashboard
          </h1>
          <p className="text-sub text-sm mb-6">
            Monitor your system backup repository on GitHub.
          </p>
          <form
            action={async () => {
              "use server";
              await signIn("github");
            }}
          >
            <button
              type="submit"
              className="w-full bg-accent text-[#0d1117] font-semibold rounded-lg px-4 py-2.5 text-sm hover:opacity-90 transition-opacity cursor-pointer"
            >
              Sign in with GitHub
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Signed in, no repo linked ──────────────────────────
  const settings = await getUserSettings(session.user.id);

  if (!settings?.repo) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-card border border-border rounded-xl p-8 max-w-md w-full">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              {session.user?.image && (
                <img
                  src={session.user.image}
                  alt=""
                  className="w-8 h-8 rounded-full"
                />
              )}
              <span className="text-sm text-foreground">
                {session.user?.name}
              </span>
            </div>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/" });
              }}
            >
              <button
                type="submit"
                className="text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
              >
                Sign out
              </button>
            </form>
          </div>
          <h2 className="text-lg font-bold text-bright mb-1">
            Link Repository
          </h2>
          <p className="text-sub text-sm mb-4">
            Enter your uconsole backup repository to get started.
          </p>
          <RepoLinker />
        </div>
      </div>
    );
  }

  // ── Dashboard ──────────────────────────────────────────
  const [repoInfoRaw, commitsRaw, treeRaw, packages, extensions, scriptsRaw] =
    await Promise.all([
      fetchRepoInfo(session.accessToken, settings.repo),
      fetchCommits(session.accessToken, settings.repo),
      fetchTree(session.accessToken, settings.repo),
      fetchAllPackages(session.accessToken, settings.repo),
      fetchExtensions(session.accessToken, settings.repo),
      fetchScriptsManifest(session.accessToken, settings.repo),
    ]);

  const repoInfo = repoInfoRaw as RepoInfo | null;
  const commits: CommitData[] = Array.isArray(commitsRaw)
    ? (commitsRaw as GitHubCommit[]).map((c) => ({
        sha: c.sha,
        message: c.commit.message,
        date: c.commit.author.date,
      }))
    : [];
  const tree: TreeEntry[] = treeRaw
    ? ((treeRaw as { tree: TreeEntry[] }).tree || [])
    : [];
  const totalPackages = Object.values(packages).reduce(
    (sum, arr) => sum + arr.length,
    0
  );

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border px-4 py-3">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-bold text-bright">
              uConsole Dashboard
            </h1>
            <span className="text-xs text-sub font-mono bg-background border border-border rounded px-1.5 py-0.5">
              {settings.repo}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {session.user?.image && (
                <img
                  src={session.user.image}
                  alt=""
                  className="w-6 h-6 rounded-full"
                />
              )}
              <span className="text-sm text-foreground hidden sm:inline">
                {session.user?.name}
              </span>
            </div>
            <form
              action={async () => {
                "use server";
                const s = await auth();
                if (s?.user?.id) await deleteUserSettings(s.user.id);
                redirect("/");
              }}
            >
              <button
                type="submit"
                className="text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
              >
                Unlink
              </button>
            </form>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/" });
              }}
            >
              <button
                type="submit"
                className="text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* Dashboard content */}
      <main className="max-w-5xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 [&>section]:mb-0">
          <BackupCoverage
            totalPackages={totalPackages}
            extensionCount={extensions.length}
            hasScripts={!!scriptsRaw}
          />
          {repoInfo && <RepoStats info={repoInfo} />}
        </div>

        <CommitHistory commits={commits} />
        <PackageInventory packages={packages} />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 [&>section]:mb-0">
          <BrowserExtensions extensions={extensions} />
          <ScriptsManifest raw={scriptsRaw} />
        </div>

        <RepoStructure tree={tree} />
      </main>
    </div>
  );
}
