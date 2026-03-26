"use client";

import { useState, useEffect } from "react";
import { useLocalMode } from "@/components/LocalModeProvider";

interface CertNudgeProps {
  deviceIp: string | null;
}

function storageKey(ip: string) {
  return `certNudgeDismissed:${ip}`;
}

/**
 * Shows a nudge when the device is on the same network but the self-signed
 * certificate hasn't been trusted yet. Only shows once per device IP.
 */
export function CertNudge({ deviceIp }: CertNudgeProps) {
  const { isLocal, probeResult } = useLocalMode();
  const [dismissed, setDismissed] = useState(true); // default hidden until we check

  useEffect(() => {
    if (!deviceIp || deviceIp === "none") return;
    const wasDismissed = localStorage.getItem(storageKey(deviceIp)) === "1";
    setDismissed(wasDismissed);
  }, [deviceIp]);

  // Only show when: probe found a cert error, not in local mode, and we have a device IP
  if (
    isLocal ||
    probeResult !== "cert_error" ||
    !deviceIp ||
    deviceIp === "none" ||
    dismissed
  ) {
    return null;
  }

  function handleDismiss() {
    if (deviceIp && deviceIp !== "none") {
      localStorage.setItem(storageKey(deviceIp), "1");
    }
    setDismissed(true);
  }

  const deviceUrl = `https://${deviceIp}`;

  return (
    <div
      className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
      style={{
        background: "color-mix(in srgb, var(--yellow) 6%, var(--bg))",
        borderColor: "color-mix(in srgb, var(--yellow) 30%, var(--border))",
      }}
    >
      <span className="shrink-0 mt-0.5" style={{ color: "var(--yellow)" }}>
        &#x1F512;
      </span>
      <div className="flex-1 min-w-0 space-y-1.5">
        <p className="text-bright text-xs font-medium">
          Certificate not trusted
        </p>
        <p className="text-sub text-xs leading-relaxed">
          Your uConsole is on this network but the certificate hasn&apos;t been
          trusted. Visit{" "}
          <a
            href={deviceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline font-mono"
          >
            {deviceUrl}
          </a>{" "}
          in your browser to accept the certificate, then come back.
        </p>
        <div className="flex items-center gap-3 pt-0.5">
          <a
            href={deviceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium px-2.5 py-1 rounded-md border border-border bg-background text-bright hover:border-[var(--accent)] transition-colors"
          >
            Open device
          </a>
          <button
            type="button"
            onClick={handleDismiss}
            className="text-xs text-dim hover:text-sub transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
