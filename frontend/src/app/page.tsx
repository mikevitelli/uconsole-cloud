import Image from "next/image";
import { auth } from "@/lib/auth";
import { getUserSettings } from "@/lib/redis";
import {
  fetchRepoInfo,
  fetchCommits,
  fetchTree,
  fetchAllPackages,
  fetchExtensions,
  fetchScriptsManifest,
  GitHubError,
} from "@/lib/github";
import type { BackupEntry, TreeEntry, RepoInfo, GitHubCommit } from "@/lib/types";
import { categorizeAptPackages } from "@/lib/packageCategories";
import { parseBackupMessage } from "@/lib/utils";
import { RepoStats } from "@/components/dashboard/RepoStats";
import { BackupHistory } from "@/components/dashboard/BackupHistory";
import { PackageInventory } from "@/components/dashboard/PackageInventory";
import { BrowserExtensions } from "@/components/dashboard/BrowserExtensions";
import { ScriptsManifest } from "@/components/dashboard/ScriptsManifest";
import { BackupCoverage } from "@/components/dashboard/BackupCoverage";
import { RepoStructure } from "@/components/dashboard/RepoStructure";
import { SystemSummary } from "@/components/dashboard/SystemSummary";
import { LocalModeShell } from "@/components/dashboard/LocalModeShell";
import { RepoLinker } from "@/components/RepoLinker";
import { ConfirmButton } from "@/components/ConfirmButton";
import { UserAvatar } from "@/components/UserWidget";
import { getDeviceStatus, getLastKnownFallback } from "@/lib/deviceStatus";
import { CopyCommand } from "@/components/CopyCommand";
import { fetchSiteContent } from "@/lib/sanity";
import { signInAction, signOutAction, unlinkAction } from "./actions";

export default async function Home() {
  const session = await auth();
  const content = await fetchSiteContent();

  // ── Not signed in ──────────────────────────────────────
  if (!session) {
    return (
      <div className="min-h-screen flex flex-col">
        {/* Hero */}
        <div className="flex-1 flex flex-col items-center justify-center px-4 py-20 sm:py-24">
          {/* Device Image */}
          <div className="mb-12">
            <Image
              src="/uConsole-spin.gif"
              alt="ClockworkPi uConsole"
              width={320}
              height={320}
              unoptimized
              priority
            />
          </div>

          {/* Heading */}
          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight text-center mb-5 bg-gradient-to-r from-bright via-accent to-bright bg-clip-text text-transparent">
            {content?.landing?.heading ?? "uConsole Cloud"}
          </h1>
          <p className="text-sub text-base sm:text-lg text-center max-w-lg mb-12 leading-relaxed">
            {content?.landing?.description ??
              "Monitor your uConsole from anywhere. Battery, CPU, memory, WiFi, and more — pushed every 5 minutes."}
          </p>

          {/* Install command */}
          <div className="w-full max-w-lg mb-4">
            <CopyCommand command="curl -fsSL https://uconsole.cloud/install | bash" />
          </div>
          <p className="text-dim text-sm mb-14">
            and then <span className="font-mono text-sub">uconsole setup</span> to link your device
          </p>

          {/* Sign in */}
          <div className="flex flex-col items-center gap-3">
            <p className="text-dim text-xs">Already have an account?</p>
            <form action={signInAction}>
              <button
                type="submit"
                className="flex items-center gap-2 bg-[#24292f] text-white font-medium rounded-lg px-5 py-2.5 text-sm hover:bg-[#32383f] hover:shadow-[0_0_12px_rgba(88,166,255,0.15)] transition-all cursor-pointer border border-[#3d444d]"
              >
                <Image src="/github-mark-white.svg" alt="" width={18} height={18} className="w-[18px] h-[18px]" />
                {content?.landing?.signInButton ?? "Sign in with GitHub"}
              </button>
            </form>
          </div>
        </div>

        {/* Features */}
        <div className="border-t border-border py-16 px-4">
          <div className="max-w-3xl mx-auto grid grid-cols-1 sm:grid-cols-3 gap-8 text-center">
            <div className="flex flex-col items-center gap-2">
              <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center mb-1">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              </div>
              <div className="text-accent text-2xl font-bold">5 min</div>
              <div className="text-sub text-sm">Status push interval</div>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center mb-1">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
              </div>
              <div className="text-accent text-2xl font-bold">1 command</div>
              <div className="text-sub text-sm">Install and setup</div>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center mb-1">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              </div>
              <div className="text-accent text-2xl font-bold">Zero config</div>
              <div className="text-sub text-sm">Device code auth</div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-border py-6 px-4 text-center">
          <p className="text-dim text-xs">Built for ClockworkPi uConsole</p>
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
            <UserAvatar session={session} size="w-8 h-8" />
            <form action={signOutAction}>
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

  // ── Session expired ────────────────────────────────────
  if (!session.accessToken) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-xl font-semibold text-red-400">Session expired</h2>
          <p className="text-sub text-sm">Please sign out and sign back in.</p>
          <form action={signOutAction}>
            <button className="text-sm underline text-sub hover:text-fg cursor-pointer">Sign out</button>
          </form>
        </div>
      </div>
    );
  }

  // ── Fetch dashboard data ───────────────────────────────
  let repoInfoRaw, commitsRaw, treeRaw, packages, extensions, scriptsRaw, deviceStatus, lastKnownFallback;
  try {
    [repoInfoRaw, commitsRaw, treeRaw, packages, extensions, scriptsRaw, deviceStatus, lastKnownFallback] =
      await Promise.all([
        fetchRepoInfo(session.accessToken, settings.repo),
        fetchCommits(session.accessToken, settings.repo),
        fetchTree(session.accessToken, settings.repo),
        fetchAllPackages(session.accessToken, settings.repo),
        fetchExtensions(session.accessToken, settings.repo),
        fetchScriptsManifest(session.accessToken, settings.repo),
        getDeviceStatus(settings.repo),
        getLastKnownFallback(settings.repo),
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
            <form action={signOutAction}>
              <button className="text-sm underline text-sub hover:text-fg cursor-pointer">Sign out</button>
            </form>
          </div>
        </div>
      );
    }
    throw err;
  }

  // ── Transform data ─────────────────────────────────────
  const repoInfo = repoInfoRaw as RepoInfo | null;
  const commits: BackupEntry[] = Array.isArray(commitsRaw)
    ? (commitsRaw as GitHubCommit[]).map((c) => ({
        sha: c.sha,
        message: c.commit.message,
        date: c.commit.author.date,
        htmlUrl: c.html_url ?? "",
        ...parseBackupMessage(c.commit.message),
      }))
    : [];
  const tree: TreeEntry[] = treeRaw
    ? ((treeRaw as { tree: TreeEntry[] }).tree || [])
    : [];
  const totalPackages = Object.values(packages).reduce(
    (sum, arr) => sum + arr.length,
    0
  );
  const aptCategories = categorizeAptPackages(packages["APT"] || []);
  // eslint-disable-next-line react-hooks/purity -- Server Component: Date.now() is safe here
  const now = Date.now();
  const deviceAgeMinutes = deviceStatus
    ? Math.floor(
        (now - new Date(deviceStatus.collectedAt).getTime()) / 60000
      )
    : 0;

  // ── Render dashboard ───────────────────────────────────
  return (
    <div className="min-h-screen overflow-x-hidden">
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md px-4 py-2">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="text-sm font-bold text-bright whitespace-nowrap">
              {content?.dashboard?.headerTitle ?? "uConsole Dashboard"}
            </h1>
            <span className="text-[11px] text-accent font-mono bg-accent/10 border border-accent/20 rounded-md px-2 py-0.5 truncate max-w-[180px] sm:max-w-none">
              {settings.repo}
            </span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <UserAvatar session={session} />
            <form action={unlinkAction}>
              <ConfirmButton
                message="Are you sure you want to unlink this repo? You can re-link it later."
                className="text-xs text-sub hover:text-foreground transition-colors cursor-pointer"
              >
                {content?.dashboard?.unlinkButton ?? "Unlink"}
              </ConfirmButton>
            </form>
            <form action={signOutAction}>
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

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 overflow-hidden space-y-5">
        {!deviceStatus && (
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: "var(--yellow)" }}
              />
              <h2 className="text-sm font-semibold text-bright">
                Waiting for device
              </h2>
            </div>
            <p className="text-xs text-sub mb-3">
              Run these commands on your uConsole to start sending data:
            </p>
            <div className="space-y-2">
              <CopyCommand command="curl -fsSL https://uconsole.cloud/install | bash" />
              <CopyCommand command="uconsole setup" />
            </div>
            <p className="text-xs text-dim mt-3">
              Then enter the code at{" "}
              <a href="/link" className="text-accent hover:underline">
                uconsole.cloud/link
              </a>
            </p>
          </section>
        )}
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

        <LocalModeShell
          deviceIp={deviceStatus?.wifi?.ip ?? null}
          serverStatus={deviceStatus}
          ageMinutes={deviceAgeMinutes}
          lastKnownFallback={lastKnownFallback}
          content={content?.deviceStatus}
        />

        <BackupHistory backups={commits} content={content?.backupHistory} />
        <PackageInventory
          packages={packages}
          aptCategories={aptCategories}
          content={content?.packageInventory}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4 [&>section]:mb-0 opacity-90">
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
