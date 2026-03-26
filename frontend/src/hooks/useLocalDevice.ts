"use client";

import { useState, useEffect, useCallback, useRef } from "react";

/**
 * Stats shape returned by the local webdash /api/public/stats endpoint.
 * NOTE: The webdash nginx config must include
 *   Access-Control-Allow-Origin: https://uconsole.cloud
 * for this fetch to succeed from the browser.
 */
export interface LocalStats {
  battery: {
    capacity: number;
    voltage: number;
    current: number;
    status: string;
    health: string;
  };
  cpu: {
    tempC: number;
    loadAvg: [number, number, number];
    cores: number;
  };
  memory: {
    totalMB: number;
    usedMB: number;
    availableMB: number;
  };
  disk: {
    totalGB: number;
    usedGB: number;
    availableGB: number;
    usedPercent: number;
  };
  wifi: {
    ssid: string;
    signalDBm: number;
    quality: number;
    bitrateMbps: number;
    ip: string;
  };
  uptime: string;
  hostname: string;
  kernel: string;
}

export type ProbeResult = 'probing' | 'local' | 'unreachable' | 'cert_error';

export interface LocalDeviceState {
  isLocal: boolean;
  stats: LocalStats | null;
  baseUrl: string | null;
  /** True during the initial probe (before first result) */
  probing: boolean;
  /** Detailed probe result for downstream components like CertNudge */
  probeResult: ProbeResult;
  /** True when local mode is active but connection is unstable (1-2 consecutive failures) */
  connectionUnstable: boolean;
}

const PROBE_TIMEOUT_MS = 3000;
const REPROBE_INTERVAL_MS = 30_000;
const POLL_INTERVAL_MS = 5_000;

type FetchResult =
  | { ok: true; stats: LocalStats }
  | { ok: false; reason: 'cert_error' | 'unreachable' };

async function tryFetch(url: string): Promise<FetchResult> {
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      // Self-signed cert will cause a network error in the browser —
      // that's fine, we catch it and stay in remote mode.
    });
    if (!res.ok) return { ok: false, reason: 'unreachable' };
    const stats = (await res.json()) as LocalStats;
    return { ok: true, stats };
  } catch (err) {
    // TypeError is typical for cert issues (mixed content / self-signed)
    if (err instanceof TypeError) {
      return { ok: false, reason: 'cert_error' };
    }
    return { ok: false, reason: 'unreachable' };
  }
}

/**
 * Probes the local webdash to detect same-network access.
 * Tries the device WiFi IP first, then uconsole.local (mDNS).
 * When local, polls /api/public/stats every 5 seconds for live data.
 * Re-probes every 30 seconds if not local.
 */
export function useLocalDevice(deviceIp: string | null): LocalDeviceState {
  const [state, setState] = useState<LocalDeviceState>({
    isLocal: false,
    stats: null,
    baseUrl: null,
    probing: true,
    probeResult: 'probing',
    connectionUnstable: false,
  });

  const baseUrlRef = useRef<string | null>(null);
  /** Track consecutive poll failures for hysteresis (require 3 before dropping to remote) */
  const consecutiveFailuresRef = useRef(0);
  const HYSTERESIS_THRESHOLD = 3;

  const probe = useCallback(async () => {
    const candidates: string[] = [];
    if (deviceIp && deviceIp !== "none") {
      candidates.push(`https://${deviceIp}`);
    }
    candidates.push("https://uconsole.local");

    let lastReason: 'cert_error' | 'unreachable' = 'unreachable';

    for (const base of candidates) {
      const result = await tryFetch(`${base}/api/public/stats`);
      if (result.ok) {
        baseUrlRef.current = base;
        consecutiveFailuresRef.current = 0;
        setState({ isLocal: true, stats: result.stats, baseUrl: base, probing: false, probeResult: 'local', connectionUnstable: false });
        return true;
      }
      lastReason = result.reason;
    }

    baseUrlRef.current = null;
    setState((prev) => ({ ...prev, isLocal: false, stats: null, baseUrl: null, probing: false, probeResult: lastReason, connectionUnstable: false }));
    return false;
  }, [deviceIp]);

  // Initial probe + re-probe interval
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval>;

    probe().then((found) => {
      if (cancelled) return;
      // If not local, re-probe every 30s. If local, polling takes over.
      if (!found) {
        timer = setInterval(() => {
          if (!cancelled) probe();
        }, REPROBE_INTERVAL_MS);
      }
    });

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [probe]);

  // Live poll when local
  useEffect(() => {
    if (!state.isLocal || !baseUrlRef.current) return;

    let cancelled = false;
    const base = baseUrlRef.current;

    const poll = setInterval(async () => {
      if (cancelled) return;
      const result = await tryFetch(`${base}/api/public/stats`);
      if (cancelled) return;

      if (result.ok) {
        consecutiveFailuresRef.current = 0;
        setState((prev) => ({ ...prev, stats: result.stats, connectionUnstable: false }));
      } else {
        consecutiveFailuresRef.current += 1;
        if (consecutiveFailuresRef.current >= HYSTERESIS_THRESHOLD) {
          // Device went away — fall back to remote mode, start re-probing
          baseUrlRef.current = null;
          consecutiveFailuresRef.current = 0;
          setState({ isLocal: false, stats: null, baseUrl: null, probing: false, probeResult: result.reason, connectionUnstable: false });
        } else {
          // Grace period: keep last known stats, show unstable indicator
          setState((prev) => ({ ...prev, connectionUnstable: true }));
        }
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, [state.isLocal]);

  return state;
}
