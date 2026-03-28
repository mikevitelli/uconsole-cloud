import type { WifiFallbackStatus } from "@/lib/deviceStatus";

interface DeviceOfflineProps {
  heading: string;
  offlineMessage?: string;
  lastKnownFallback?: WifiFallbackStatus | null;
}

export function DeviceOffline({
  heading,
  offlineMessage,
  lastKnownFallback,
}: DeviceOfflineProps) {
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
            {offlineMessage ?? "Device offline — no status received."}
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
