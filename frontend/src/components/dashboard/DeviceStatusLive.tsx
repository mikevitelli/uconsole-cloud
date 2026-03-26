"use client";

import { useLocalMode } from "@/components/LocalModeProvider";
import { Donut } from "@/components/viz/Donut";
import { StatCards } from "@/components/viz/StatCards";
import type { DeviceStatusPayload, WifiFallbackStatus } from "@/lib/deviceStatus";
import type { LocalStats } from "@/hooks/useLocalDevice";

interface DeviceStatusContent {
  heading?: string;
  offlineMessage?: string;
}

interface DeviceStatusLiveProps {
  /** Server-rendered status from Redis (may be stale) */
  serverStatus: DeviceStatusPayload | null;
  ageMinutes: number;
  lastKnownFallback?: WifiFallbackStatus | null;
  content?: DeviceStatusContent;
}

function batteryColor(capacity: number): string {
  if (capacity > 50) return "var(--green)";
  if (capacity > 20) return "var(--yellow)";
  return "var(--red)";
}

function tempColor(tempC: number): string {
  if (tempC < 60) return "var(--green)";
  if (tempC < 75) return "var(--yellow)";
  return "var(--red)";
}

/**
 * Client-side wrapper around DeviceStatus that overlays live local stats
 * when local mode is active. Falls back to the server-rendered data otherwise.
 */
export function DeviceStatusLive({
  serverStatus,
  ageMinutes,
  lastKnownFallback,
  content,
}: DeviceStatusLiveProps) {
  const { isLocal, stats, baseUrl, connectionUnstable } = useLocalMode();
  const heading = content?.heading ?? "Device Status";

  // Use local stats when available, otherwise fall back to server-rendered
  const liveStats: LocalStats | null = isLocal && stats ? stats : null;

  // ── Offline state (no server data and no local data) ──
  if (!serverStatus && !liveStats) {
    const fallbackEnabled = lastKnownFallback?.enabled;
    const apName = lastKnownFallback?.apName ?? "uConsole";

    return (
      <section className="bg-card border border-border rounded-xl p-4">
        <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
          <span>&#x1F4F1;</span> {heading}
        </h2>
        <div className="py-8 space-y-4">
          {/* Pulsing radar animation */}
          <div className="flex justify-center">
            <div className="relative w-16 h-16 flex items-center justify-center">
              <span
                className="absolute inline-flex h-full w-full rounded-full opacity-20 animate-ping"
                style={{ background: "var(--dim)", animationDuration: "2s" }}
              />
              <span
                className="absolute inline-flex h-10 w-10 rounded-full opacity-15 animate-ping"
                style={{ background: "var(--dim)", animationDuration: "2s", animationDelay: "0.5s" }}
              />
              <span
                className="relative inline-flex h-4 w-4 rounded-full"
                style={{ background: "var(--red)" }}
              />
            </div>
          </div>
          <div className="text-center">
            <p className="text-sub text-sm">
              {content?.offlineMessage ?? "Waiting for device..."}
            </p>
            <p className="text-dim text-xs mt-1">
              No status received yet. Install the agent to start monitoring.
            </p>
          </div>
          {fallbackEnabled && (
            <div className="bg-background border border-border rounded-lg px-4 py-3 max-w-sm mx-auto">
              <p className="text-xs text-bright font-medium mb-1">
                WiFi fallback is enabled
              </p>
              <p className="text-xs text-sub">
                Your uConsole may be running its own WiFi.
                Connect to <span className="font-mono text-bright">{apName}</span> in
                your WiFi settings, then open{" "}
                <a
                  href="https://10.42.0.1"
                  className="text-accent hover:underline font-mono"
                >
                  10.42.0.1
                </a>
              </p>
            </div>
          )}
        </div>
      </section>
    );
  }

  // ── Build display values ──
  // Prefer live local stats; fall back to server-rendered Redis data
  const battery = liveStats?.battery ?? serverStatus!.battery;
  const cpu = liveStats?.cpu ?? serverStatus!.cpu;
  const memory = liveStats?.memory ?? serverStatus!.memory;
  const disk = liveStats?.disk ?? serverStatus!.disk;
  const wifi = liveStats?.wifi ?? serverStatus!.wifi;
  const uptime = liveStats?.uptime ?? serverStatus!.uptime;
  const hostname = liveStats?.hostname ?? serverStatus!.hostname;
  const kernel = liveStats?.kernel ?? serverStatus!.kernel;
  const screen = serverStatus?.screen;

  const memUsedPct = Math.round((memory.usedMB / memory.totalMB) * 100);
  const isCharging = battery.status === "Charging";

  // Screen brightness as percentage (only from server data)
  const brightnessPct =
    screen && screen.maxBrightness > 0
      ? Math.round((screen.brightness / screen.maxBrightness) * 100)
      : null;

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-bold text-bright flex items-center gap-2">
          <span>&#x1F4F1;</span> {heading}
        </h2>
        <div className="flex items-center gap-1.5 text-xs text-sub">
          {isLocal ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${connectionUnstable ? "bg-[var(--yellow)]" : "bg-[var(--green)]"}`} />
                <span className={`relative inline-flex h-2 w-2 rounded-full ${connectionUnstable ? "bg-[var(--yellow)]" : "bg-[var(--green)]"}`} />
              </span>
              <span>{connectionUnstable ? "unstable" : "live"}</span>
            </>
          ) : (
            <>
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  background:
                    ageMinutes < 10
                      ? "var(--green)"
                      : ageMinutes < 30
                        ? "var(--yellow)"
                        : "var(--red)",
                }}
              />
              <span>{fmtAge(ageMinutes)}</span>
            </>
          )}
        </div>
      </div>

      {/* Top stats */}
      <StatCards
        items={[
          {
            value: `${battery.capacity}%`,
            label: "Battery",
            color: batteryColor(battery.capacity),
          },
          {
            value: `${cpu.tempC.toFixed(1)}\u00b0C`,
            label: "CPU Temp",
            color: tempColor(cpu.tempC),
          },
          {
            value: `${memory.usedMB.toLocaleString()} MB`,
            label: `Memory (${memUsedPct}%)`,
          },
          {
            value: `${disk.usedGB.toFixed(1)} / ${disk.totalGB.toFixed(1)} GB`,
            label: `Disk (${disk.usedPercent}%)`,
          },
        ]}
      />

      {/* Battery donut + system details */}
      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-4 items-start mt-3">
        <div className="flex flex-col items-center gap-1">
          <Donut
            percent={battery.capacity}
            size={100}
            label="Battery"
            centerText={`${battery.capacity}%`}
            subText={battery.status}
            color={batteryColor(battery.capacity)}
            glow={isCharging}
          />
          <div className="text-xs text-dim mt-1 text-center space-y-0.5">
            <div>
              {(battery.voltage / 1000).toFixed(2)}V /{" "}
              {Math.abs(battery.current)}mA
            </div>
            <div>{battery.health}</div>
          </div>
        </div>

        <div className="space-y-3">
          {/* Network group */}
          <div>
            <h4 className="text-[10px] text-dim uppercase tracking-wider font-semibold mb-1.5 px-1">
              Network
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {[
                { label: "WiFi", value: `${wifi.ssid} (${wifi.signalDBm} dBm)` },
                { label: "Bitrate", value: `${wifi.bitrateMbps} Mbps` },
                { label: "IP", value: wifi.ip },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
                >
                  <span className="text-sub font-medium shrink-0 w-14">
                    {item.label}
                  </span>
                  <span className="text-foreground truncate font-mono">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* System group */}
          <div>
            <h4 className="text-[10px] text-dim uppercase tracking-wider font-semibold mb-1.5 px-1">
              System
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {[
                {
                  label: "CPU Load",
                  value: cpu.loadAvg.map((l) => l.toFixed(2)).join(", "),
                },
                { label: "Uptime", value: uptime },
                { label: "Host", value: hostname },
                { label: "Kernel", value: kernel },
                ...(brightnessPct !== null
                  ? [{ label: "Screen", value: `${brightnessPct}% brightness` }]
                  : []),
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
                >
                  <span className="text-sub font-medium shrink-0 w-14">
                    {item.label}
                  </span>
                  <span className="text-foreground truncate font-mono">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* AIO Board — show when we have server data (visible in both local and remote mode) */}
      {serverStatus?.aio && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold text-bright mb-1.5 flex items-center gap-1.5">
            <span>&#x1F4E1;</span> AIO Board
          </h3>
          <AioBoardGrid aio={serverStatus.aio} />
        </div>
      )}

      {/* Local Shell Hub / Full Dashboard — show when webdash running, more prominent in local mode */}
      {(serverStatus?.webdash?.running || isLocal) && wifi.ip && wifi.ip !== "none" && (
        <div
          className="mt-3 flex items-center gap-3 border rounded-lg px-4 py-3"
          style={{
            background: "color-mix(in srgb, var(--green) 5%, var(--bg))",
            borderColor: "color-mix(in srgb, var(--green) 25%, var(--border))",
          }}
        >
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--green)] opacity-75 animate-ping" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[var(--green)]" />
          </span>
          <div className="flex-1 min-w-0">
            <a
              href={isLocal && baseUrl ? baseUrl : `https://${wifi.ip}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-semibold text-bright hover:underline"
            >
              {isLocal ? "Open full dashboard \u2192" : "Local Shell Hub"}
            </a>
            <span className="text-xs text-dim font-mono ml-2">
              {wifi.ip}
            </span>
          </div>
          <span
            className="text-xs font-medium shrink-0 px-2 py-0.5 rounded-full"
            style={{
              color: "var(--green)",
              background: "color-mix(in srgb, var(--green) 12%, transparent)",
            }}
          >
            {isLocal ? "local" : "same network"}
          </span>
        </div>
      )}
    </section>
  );
}

// ── Helpers ──────────────────────────────────────────────

function fmtAge(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
}

// Re-used from original DeviceStatus — extracted for the AIO section
function AioBoardGrid({ aio }: { aio: DeviceStatusPayload["aio"] }) {
  const items = [
    {
      name: "RTL-SDR",
      color: aio.sdr.detected ? "var(--green)" : "var(--dim)",
      detail: aio.sdr.detected ? aio.sdr.chip ?? "detected" : "not found",
    },
    {
      name: "LoRa",
      color: aio.lora.detected ? "var(--green)" : "var(--dim)",
      detail: aio.lora.detected ? aio.lora.chip ?? "SX1262" : "not found",
    },
    {
      name: "GPS",
      color: aio.gps.detected
        ? aio.gps.hasFix
          ? "var(--green)"
          : "var(--yellow)"
        : "var(--dim)",
      detail: aio.gps.detected
        ? aio.gps.hasFix
          ? "fix acquired"
          : "no fix"
        : "not found",
    },
    {
      name: "RTC",
      color: aio.rtc.detected
        ? aio.rtc.synced
          ? "var(--green)"
          : "var(--yellow)"
        : "var(--dim)",
      detail: aio.rtc.detected
        ? aio.rtc.synced
          ? aio.rtc.time
            ? (() => {
                const m = aio.rtc.time.match(/(\d+):(\d+):(\d+)/);
                if (!m) return "synced";
                const h = parseInt(m[1]);
                const min = m[2];
                const ampm = h >= 12 ? "PM" : "AM";
                const h12 = h % 12 || 12;
                return `${h12}:${min} ${ampm}`;
              })()
            : "synced"
          : "not synced"
        : "not found",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 my-2">
      {items.map((item) => (
        <div
          key={item.name}
          className="flex items-center gap-1.5 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
        >
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: item.color }}
          />
          <span className="text-foreground flex-1">{item.name}</span>
          {item.detail && (
            <span className="text-dim text-xs">{item.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
}
