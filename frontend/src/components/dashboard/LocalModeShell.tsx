import { DeviceStatus } from "@/components/dashboard/DeviceStatus";
import { QuickActions } from "@/components/dashboard/QuickActions";
import type { DeviceStatusPayload, WifiFallbackStatus } from "@/lib/deviceStatus";

interface DeviceStatusContent {
  heading?: string;
  offlineMessage?: string;
}

interface LocalModeShellProps {
  isSameNetwork?: boolean;
  deviceLocalIp?: string | null;
  /** @deprecated Use deviceLocalIp — kept for backwards compat while page.tsx migrates */
  deviceIp?: string | null;
  serverStatus: DeviceStatusPayload | null;
  ageMinutes: number;
  lastKnownFallback?: WifiFallbackStatus | null;
  content?: DeviceStatusContent;
}

/**
 * Server-rendered shell that wraps DeviceStatus with same-network detection.
 * When the user's phone and uConsole share the same public IP (NAT),
 * shows a prominent banner with a direct link to the local webdash.
 */
export function LocalModeShell({
  isSameNetwork = false,
  deviceLocalIp: deviceLocalIpProp,
  deviceIp,
  serverStatus,
  ageMinutes,
  lastKnownFallback,
  content,
}: LocalModeShellProps) {
  // Support both new (deviceLocalIp) and legacy (deviceIp) prop names
  const deviceLocalIp = deviceLocalIpProp ?? deviceIp ?? null;
  const webdashUrl =
    deviceLocalIp && deviceLocalIp !== "none"
      ? `https://${deviceLocalIp}`
      : null;

  return (
    <>
      {/* Same-network banner — prominent bridge to local webdash */}
      {isSameNetwork && webdashUrl && (
        <section
          className="rounded-xl border p-4 space-y-3"
          style={{
            background: "color-mix(in srgb, var(--green) 5%, var(--bg))",
            borderColor: "color-mix(in srgb, var(--green) 30%, var(--border))",
          }}
        >
          {/* Header */}
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--green)] opacity-75 animate-ping" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[var(--green)]" />
            </span>
            <span className="text-sm font-semibold text-bright">
              Same network detected
            </span>
          </div>

          <p className="text-xs text-sub leading-relaxed">
            Your phone and uConsole are on the same network.
          </p>

          {/* Primary CTA */}
          <a
            href={webdashUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm font-semibold text-bright hover:border-[var(--accent)] transition-colors"
            style={{
              borderColor: "color-mix(in srgb, var(--green) 25%, var(--border))",
              background: "color-mix(in srgb, var(--green) 8%, var(--bg))",
            }}
          >
            <span>Open Local Dashboard &rarr;</span>
            <span className="text-xs font-normal text-dim font-mono">
              {deviceLocalIp}
            </span>
          </a>
          <p className="text-[11px] text-dim">
            Real-time monitoring, terminal, 60+ scripts
          </p>

          {/* Quick links */}
          <QuickActions deviceLocalIp={deviceLocalIp!} />
        </section>
      )}

      {/* Device status — always shown */}
      <DeviceStatus
        status={serverStatus}
        ageMinutes={ageMinutes}
        lastKnownFallback={lastKnownFallback}
        content={content}
        isSameNetwork={isSameNetwork}
        deviceLocalIp={deviceLocalIp}
      />
    </>
  );
}
