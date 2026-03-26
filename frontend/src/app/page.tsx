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
import { DeviceStatus } from "@/components/dashboard/DeviceStatus";
import { SystemSummary } from "@/components/dashboard/SystemSummary";
import { RepoLinker } from "@/components/RepoLinker";
import { ConfirmButton } from "@/components/ConfirmButton";
import { UserAvatar } from "@/components/UserWidget";
import { getDeviceStatus } from "@/lib/deviceStatus";
import { DeviceSetup } from "@/components/DeviceSetup";
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
        <div className="flex-1 flex flex-col items-center justify-center px-4 py-16">
          {/* Device Image */}
          <div className="mb-10">
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
          <h1 className="text-4xl sm:text-5xl font-bold text-bright tracking-tight text-center mb-4">
            {content?.landing?.heading ?? "uConsole Cloud"}
          </h1>
          <p className="text-sub text-base sm:text-lg text-center max-w-lg mb-10 leading-relaxed">
            {content?.landing?.description ??
              "Monitor your uConsole from anywhere. Battery, CPU, memory, WiFi, and more — pushed every 5 minutes."}
          </p>

          {/* Install command */}
          <div className="w-full max-w-lg mb-4">
            <CopyCommand command="curl -fsSL https://uconsole.cloud/install | bash" />
          </div>
          <p className="text-dim text-sm mb-10">
            and then <span className="font-mono text-sub">uconsole setup</span> to link your device
          </p>

          {/* Sign in */}
          <div className="flex flex-col items-center gap-3">
            <p className="text-dim text-xs">Already have an account?</p>
            <form action={signInAction}>
              <button
                type="submit"
                className="flex items-center gap-2 bg-[#24292f] text-white font-medium rounded-lg px-5 py-2.5 text-sm hover:bg-[#32383f] transition-colors cursor-pointer border border-[#3d444d]"
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
            <div>
              <div className="text-accent text-2xl font-bold mb-1">5 min</div>
              <div className="text-sub text-sm">Status push interval</div>
            </div>
            <div>
              <div className="text-accent text-2xl font-bold mb-1">1 command</div>
              <div className="text-sub text-sm">Install and setup</div>
            </div>
            <div>
              <div className="text-accent text-2xl font-bold mb-1">Zero config</div>
              <div className="text-sub text-sm">Device code auth</div>
            </div>
          </div>
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

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 overflow-hidden space-y-4">
        {settings.deviceToken && (
          <DeviceSetup
            deviceToken={settings.deviceToken}
            repo={settings.repo}
            apiUrl={process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL
              ? `https://${process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL}`
              : "https://uconsole.cloud"}
          />
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
