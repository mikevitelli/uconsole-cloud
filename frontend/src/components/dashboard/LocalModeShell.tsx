"use client";

import { LocalModeProvider } from "@/components/LocalModeProvider";
import { LocalModeBanner } from "@/components/dashboard/LocalModeBanner";
import { DeviceStatusLive } from "@/components/dashboard/DeviceStatusLive";
import { QuickActions } from "@/components/dashboard/QuickActions";
import type { DeviceStatusPayload, WifiFallbackStatus } from "@/lib/deviceStatus";

interface DeviceStatusContent {
  heading?: string;
  offlineMessage?: string;
}

interface LocalModeShellProps {
  deviceIp: string | null;
  serverStatus: DeviceStatusPayload | null;
  ageMinutes: number;
  lastKnownFallback?: WifiFallbackStatus | null;
  content?: DeviceStatusContent;
}

/**
 * Client boundary that provides local mode context around the
 * DeviceStatus section. Keeps the rest of the dashboard as
 * server-rendered components.
 */
export function LocalModeShell({
  deviceIp,
  serverStatus,
  ageMinutes,
  lastKnownFallback,
  content,
}: LocalModeShellProps) {
  return (
    <LocalModeProvider deviceIp={deviceIp}>
      <LocalModeBanner />
      <DeviceStatusLive
        serverStatus={serverStatus}
        ageMinutes={ageMinutes}
        lastKnownFallback={lastKnownFallback}
        content={content}
      />
      <QuickActions />
    </LocalModeProvider>
  );
}
