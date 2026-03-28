import type { HardwareManifest } from "@/lib/device-config-schema";

interface HardwarePanelProps {
  hardware?: HardwareManifest | null;
}

const COMPONENTS: {
  key: keyof Pick<HardwareManifest, "sdr" | "lora" | "gps" | "rtc" | "esp32">;
  label: string;
}[] = [
  { key: "sdr", label: "RTL-SDR" },
  { key: "lora", label: "LoRa" },
  { key: "gps", label: "GPS" },
  { key: "rtc", label: "RTC" },
  { key: "esp32", label: "ESP32" },
];

function expansionLabel(expansion: string): string {
  switch (expansion) {
    case "aio-v1":
      return "AIO Board v1 (HackerGadgets)";
    case "aio-v2":
      return "AIO Board v2 (HackerGadgets)";
    case "4g":
      return "4G LTE Module";
    case "none":
      return "No Expansion";
    default:
      return expansion;
  }
}

function componentDetail(
  component: HardwareManifest["sdr"] | HardwareManifest["gps"] | HardwareManifest["esp32"]
): string {
  if (!component.detected) {
    return component.reason ?? "not detected";
  }
  const chip = component.chip ?? component.device ?? "detected";
  return chip;
}

export function HardwarePanel({ hardware }: HardwarePanelProps) {
  if (!hardware) {
    return (
      <section className="bg-card border border-border rounded-xl p-4">
        <h2 className="text-base font-bold text-bright flex items-center gap-2">
          <span>&#x2699;</span> Hardware
        </h2>
        <p className="text-sm text-sub mt-2">
          No hardware manifest available. Install uconsole-cloud ≥0.1.0 and run{" "}
          <code className="bg-background px-1 rounded text-xs">uconsole setup</code>{" "}
          to generate hardware.json.
        </p>
      </section>
    );
  }

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-bold text-bright flex items-center gap-2">
          <span>&#x2699;</span> Hardware
        </h2>
        {hardware.detected_at && (
          <span className="text-xs text-dim">
            scanned {new Date(hardware.detected_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Expansion module header */}
      <div className="bg-background border border-border rounded-lg px-3 py-2 mb-3">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{
              background:
                hardware.expansion !== "none"
                  ? "var(--green)"
                  : "var(--dim)",
            }}
          />
          <span className="text-sm font-medium text-bright">
            {expansionLabel(hardware.expansion)}
          </span>
        </div>
        <div className="flex gap-4 mt-1 text-xs text-sub">
          <span>{hardware.compute_module}</span>
          <span>{hardware.os}</span>
          <span>{hardware.kernel}</span>
        </div>
      </div>

      {/* Component grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {COMPONENTS.map(({ key, label }) => {
          const comp = hardware[key];
          if (!comp) return null;
          return (
            <div
              key={key}
              className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  background: comp.detected
                    ? "var(--green)"
                    : "var(--dim)",
                }}
              />
              <span className="text-sub font-medium shrink-0 w-12">
                {label}
              </span>
              <span className="text-foreground truncate font-mono">
                {componentDetail(comp)}
              </span>
            </div>
          );
        })}
      </div>

      {/* WiFi method */}
      {hardware.wifi_method && (
        <div className="mt-2 text-xs text-dim">
          WiFi: {hardware.wifi_method}
        </div>
      )}
    </section>
  );
}
