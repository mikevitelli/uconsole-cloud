import { Donut } from "@/components/viz/Donut";
import { StatCards } from "@/components/viz/StatCards";
import { StatusGrid } from "@/components/viz/StatusGrid";
import type { DeviceStatusPayload, WifiFallbackStatus } from "@/lib/deviceStatus";

interface DeviceStatusContent {
  heading?: string;
  offlineMessage?: string;
}

interface DeviceStatusProps {
  status: DeviceStatusPayload | null;
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

function stalenessColor(minutes: number): string {
  if (minutes < 10) return "var(--green)";
  if (minutes < 30) return "var(--yellow)";
  return "var(--red)";
}

function fmtAge(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
}

export function DeviceStatus({
  status,
  ageMinutes,
  lastKnownFallback,
  content,
}: DeviceStatusProps) {
  const heading = content?.heading ?? "Device Status";

  // ── Offline state ──
  if (!status) {
    const fallbackEnabled = lastKnownFallback?.enabled;
    const apName = lastKnownFallback?.apName ?? "uConsole";

    return (
      <section className="bg-card border border-border rounded-xl p-4">
        <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
          <span>&#x1F4F1;</span> {heading}
        </h2>
        <div className="py-6 space-y-3">
          <div className="flex items-center justify-center gap-2">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: "var(--red)" }}
            />
            <p className="text-sub text-sm">
              {content?.offlineMessage ?? "Device offline — no status received."}
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

  // ── Online state ──
  const { battery, cpu, memory, disk, wifi, aio, screen } = status;
  const memUsedPct = Math.round((memory.usedMB / memory.totalMB) * 100);

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-bold text-bright flex items-center gap-2">
          <span>&#x1F4F1;</span> {heading}
        </h2>
        <div className="flex items-center gap-1.5 text-xs text-sub">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: stalenessColor(ageMinutes) }}
          />
          <span>{fmtAge(ageMinutes)}</span>
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
            value: `${cpu.tempC.toFixed(1)}°C`,
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
          />
          <div className="text-xs text-dim mt-1 text-center space-y-0.5">
            <div>
              {(battery.voltage / 1000).toFixed(2)}V /{" "}
              {Math.abs(battery.current)}mA
            </div>
            <div>{battery.health}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {[
            {
              label: "WiFi",
              value: `${wifi.ssid} (${wifi.signalDBm} dBm)`,
            },
            {
              label: "Bitrate",
              value: `${wifi.bitrateMbps} Mbps`,
            },
            {
              label: "IP",
              value: wifi.ip,
            },
            {
              label: "CPU Load",
              value: cpu.loadAvg.map((l) => l.toFixed(2)).join(", "),
            },
            {
              label: "Uptime",
              value: status.uptime,
            },
            {
              label: "Screen",
              value:
                screen.maxBrightness > 0
                  ? `${Math.round((screen.brightness / screen.maxBrightness) * 100)}%`
                  : `${screen.brightness}`,
            },
            {
              label: "Kernel",
              value: status.kernel,
            },
            {
              label: "Host",
              value: status.hostname,
            },
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

      {/* AIO Board */}
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-bright mb-1 flex items-center gap-1.5">
          <span>&#x1F4E1;</span> AIO Board
        </h3>
        <StatusGrid
          items={[
            {
              name: "RTL-SDR",
              color: aio.sdr.detected ? "var(--green)" : "var(--dim)",
              detail: aio.sdr.detected
                ? aio.sdr.chip ?? "detected"
                : "not found",
            },
            {
              name: "LoRa",
              color: aio.lora.detected ? "var(--green)" : "var(--dim)",
              detail: aio.lora.detected
                ? aio.lora.chip ?? "SX1262"
                : "not found",
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
                        // Parse device-local time directly (avoid server TZ conversion)
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
          ]}
        />
      </div>

      {/* Local Shell Hub */}
      {status.webdash?.running && wifi.ip && wifi.ip !== "none" && (
        <div className="mt-3 flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-2">
          <span className="w-2 h-2 rounded-full bg-[var(--green)] shrink-0" />
          <div className="flex-1 min-w-0">
            <a
              href="https://uconsole.local"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-bright hover:underline"
            >
              Local Shell Hub
            </a>
            <span className="text-xs text-dim ml-2">
              {wifi.ip}
            </span>
          </div>
          <span className="text-xs text-dim shrink-0">same network</span>
        </div>
      )}
    </section>
  );
}
