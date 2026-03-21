import { sanityClient } from "./client";

export interface SiteContent {
  site?: { title?: string; description?: string };
  landing?: { heading?: string; description?: string; signInButton?: string };
  repoLinker?: {
    heading?: string;
    description?: string;
    placeholder?: string;
    selectPlaceholder?: string;
    buttonText?: string;
    loadingButton?: string;
    loadingText?: string;
  };
  dashboard?: {
    headerTitle?: string;
    unlinkButton?: string;
    signOutButton?: string;
  };
  backupCoverage?: {
    heading?: string;
    items?: { key?: string; name?: string; defaultDetail?: string }[];
  };
  backupHistory?: {
    heading?: string;
    sparklineLabel?: string;
    totalLabel?: string;
    latestLabel?: string;
  };
  packageInventory?: { heading?: string; totalLabel?: string };
  browserExtensions?: {
    heading?: string;
    statLabel?: string;
    emptyState?: string;
  };
  scriptsManifest?: { heading?: string; emptyState?: string };
  repoStats?: {
    heading?: string;
    sizeLabel?: string;
    branchLabel?: string;
    lastPushLabel?: string;
    visibilityLabel?: string;
  };
  repoStructure?: { heading?: string };
  deviceStatus?: { heading?: string; offlineMessage?: string };
}

const SITE_CONTENT_QUERY = `*[_id == "siteContent"][0]{
  site,
  landing,
  repoLinker,
  dashboard,
  backupCoverage,
  backupHistory,
  packageInventory,
  browserExtensions,
  scriptsManifest,
  repoStats,
  repoStructure,
  deviceStatus
}`;

export async function fetchSiteContent(): Promise<SiteContent | null> {
  try {
    return await sanityClient.fetch<SiteContent | null>(
      SITE_CONTENT_QUERY,
      {},
      { next: { revalidate: 60 } }
    );
  } catch {
    return null;
  }
}
