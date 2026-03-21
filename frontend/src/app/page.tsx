import { auth, signIn, signOut } from "@/lib/auth";
import { getUserSettings, deleteUserSettings } from "@/lib/redis";
import {
  fetchRepoInfo,
  fetchCommits,
  fetchTree,
  fetchAllPackages,
  fetchExtensions,
  fetchScriptsManifest,
  GitHubError,
} from "@/lib/github";
import type { BackupEntry, TreeEntry, RepoInfo } from "@/lib/types";
import { categorizeAptPackages } from "@/lib/packageCategories";
import { parseBackupMessage } from "@/lib/utils";
import { RepoStats } from "@/components/dashboard/RepoStats";
import { BackupHistory } from "@/components/dashboard/BackupHistory";
import { PackageInventory } from "@/components/dashboard/PackageInventory";
import { BrowserExtensions } from "@/components/dashboard/BrowserExtensions";
import { ScriptsManifest } from "@/components/dashboard/ScriptsManifest";
import { BackupCoverage } from "@/components/dashboard/BackupCoverage";
import { RepoStructure } from "@/components/dashboard/RepoStructure";
import { DeviceStatus } from "@/components/dashboard/DeviceStatus";
import { SystemSummary } from "@/components/dashboard/SystemSummary";
import { RepoLinker } from "@/components/RepoLinker";
import { ConfirmButton } from "@/components/ConfirmButton";
import { getDeviceStatus } from "@/lib/deviceStatus";
import { fetchSiteContent } from "@/lib/sanity";
import { redirect } from "next/navigation";

interface GitHubCommit {
  sha: string;
  html_url: string;
  commit: {
    message: string;
    author: { date: string };
  };
}

export default async function Home() {
  const session = await auth();
  const content = await fetchSiteContent();

  // ── Not signed in ──────────────────────────────────────
  if (!session) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 px-4">
        <div className="w-full max-w-md aspect-square rounded-xl overflow-hidden border border-border">
          <iframe
            title="ClockworkPi uConsole"
            className="w-full h-full"
            frameBorder="0"
            allowFullScreen
            allow="autoplay; fullscreen; xr-spatial-tracking"
            src="https://sketchfab.com/models/8c1124b60692407095fce5d9978e2528/embed?autostart=1&ui_theme=dark&ui_infos=0&ui_controls=1&ui_stop=0"
          />
        </div>
        <div className="bg-card border border-border rounded-xl p-8 max-w-sm w-full text-center">
          <h1 className="text-2xl font-bold text-bright mb-2">
            {content?.landing?.heading ?? "uConsole Dashboard"}
          </h1>
          <p className="text-sub text-sm mb-6">
            {content?.landing?.description ??
              "Monitor your system backup repository on GitHub."}
          </p>
          <form
            action={async () => {
              "use server";
              await signIn("github");
            }}
          >
            <button
              type="submit"
              className="w-full flex items-center justify-center gap-2 bg-[#24292f] text-white font-semibold rounded-lg px-4 py-2.5 text-sm hover:bg-[#32383f] transition-colors cursor-pointer"
            >
              <img
                src="/github-mark-white.svg"
                alt=""
                className="w-5 h-5"
              />
              {content?.landing?.signInButton ?? "Sign in with GitHub"}
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
                {content?.dashboard?.signOutButton ?? "Sign out"}
              </button>
            </form>
          </div>
          <h2 className="text-lg font-bold text-bright mb-1">
            {content?.repoLinker?.heading ?? "Link Repository"}
          </h2>
          <p className="text-sub text-sm mb-4">
            {content?.repoLinker?.description ??
              "Enter your uconsole backup repository to get started."}
          </p>
          <RepoLinker
            content={
              content?.repoLinker
                ? {
                    placeholder: content.repoLinker.placeholder,
                    selectPlaceholder: content.repoLinker.selectPlaceholder,
                    buttonText: content.repoLinker.buttonText,
                    loadingButton: content.repoLinker.loadingButton,
                    loadingText: content.repoLinker.loadingText,
                  }
                : undefined
            }
          />
        </div>
      </div>
    );
  }

  // ── Dashboard ──────────────────────────────────────────
  if (!session.accessToken) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-xl font-semibold text-red-400">Session expired</h2>
          <p className="text-sub text-sm">Please sign out and sign back in.</p>
          <form action={async () => { "use server"; await signOut(); }}>
            <button className="text-sm underline text-sub hover:text-fg cursor-pointer">Sign out</button>
          </form>
        </div>
      </div>
    );
  }

  let repoInfoRaw, commitsRaw, treeRaw, packages, extensions, scriptsRaw, deviceStatus;
  try {
    [repoInfoRaw, commitsRaw, treeRaw, packages, extensions, scriptsRaw, deviceStatus] =
      await Promise.all([
        fetchRepoInfo(session.accessToken, settings.repo),
        fetchCommits(session.accessToken, settings.repo),
        fetchTree(session.accessToken, settings.repo),
        fetchAllPackages(session.accessToken, settings.repo),
        fetchExtensions(session.accessToken, settings.repo),
        fetchScriptsManifest(session.accessToken, settings.repo),
        getDeviceStatus(settings.repo),
      ]);
  } catch (err) {
    if (err instanceof GitHubError) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center space-y-4">
            <h2 className="text-xl font-semibold text-red-400">{err.message}</h2>
            <p className="text-sub text-sm">
              {err.status === 401
                ? "Please sign out and sign back in to refresh your token."
                : "Please wait a few minutes and try again."}
            </p>
            <form action={async () => { "use server"; await signOut(); }}>
              <button className="text-sm underline text-sub hover:text-fg">Sign out</button>
            </form>
          </div>
        </div>
      );
    }
    throw err;
  }

  const repoInfo = repoInfoRaw as RepoInfo | null;
  const commits: BackupEntry[] = Array.isArray(commitsRaw)
    ? (commitsRaw as GitHubCommit[]).map((c) => {
        const parsed = parseBackupMessage(c.commit.message);
        return {
          sha: c.sha,
          message: c.commit.message,
          date: c.commit.author.date,
          htmlUrl: c.html_url ?? "",
          categories: parsed.categories,
          fileCount: parsed.fileCount,
        };
      })
    : [];
  const tree: TreeEntry[] = treeRaw
    ? ((treeRaw as { tree: TreeEntry[] }).tree || [])
    : [];
  const totalPackages = Object.values(packages).reduce(
    (sum, arr) => sum + arr.length,
    0
  );
  const aptCategories = categorizeAptPackages(packages["APT"] || []);
  const deviceAgeMinutes = deviceStatus
    ? Math.floor(
        (Date.now() - new Date(deviceStatus.collectedAt).getTime()) / 60000
      )
    : 0;

  return (
    <div className="min-h-screen overflow-x-hidden">
      {/* Header */}
      <header className="border-b border-border px-4 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-bold text-bright">
              {content?.dashboard?.headerTitle ?? "uConsole Dashboard"}
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
              <ConfirmButton
                message="Are you sure you want to unlink this repo? You can re-link it later."
                className="text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
              >
                {content?.dashboard?.unlinkButton ?? "Unlink"}
              </ConfirmButton>
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
                {content?.dashboard?.signOutButton ?? "Sign out"}
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* Dashboard content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 overflow-hidden space-y-4">
        <SystemSummary
          backups={commits}
          deviceStatus={deviceStatus}
          deviceAgeMinutes={deviceAgeMinutes}
          totalPackages={totalPackages}
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4 [&>section]:mb-0">
          <BackupCoverage
            backups={commits}
            totalPackages={totalPackages}
            extensionCount={extensions.length}
            hasScripts={!!scriptsRaw}
            content={content?.backupCoverage}
          />
          {repoInfo && (
            <RepoStats info={repoInfo} content={content?.repoStats} />
          )}
        </div>

        <DeviceStatus
          status={deviceStatus}
          ageMinutes={deviceAgeMinutes}
          content={content?.deviceStatus}
        />

        <BackupHistory backups={commits} content={content?.backupHistory} />
        <PackageInventory
          packages={packages}
          aptCategories={aptCategories}
          content={content?.packageInventory}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4 [&>section]:mb-0">
          <BrowserExtensions
            extensions={extensions}
            content={content?.browserExtensions}
          />
          <ScriptsManifest raw={scriptsRaw} content={content?.scriptsManifest} />
        </div>

        <RepoStructure tree={tree} content={content?.repoStructure} />
      </main>
    </div>
  );
}
