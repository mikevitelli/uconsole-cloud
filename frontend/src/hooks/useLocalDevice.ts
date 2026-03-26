"use client";

import { useState, useEffect, useCallback, useRef } from "react";

/**
 * Stats shape returned by the local webdash /api/stats endpoint.
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

export interface LocalDeviceState {
  isLocal: boolean;
  stats: LocalStats | null;
  baseUrl: string | null;
  /** True during the initial probe (before first result) */
  probing: boolean;
}

const PROBE_TIMEOUT_MS = 3000;
const REPROBE_INTERVAL_MS = 30_000;
const POLL_INTERVAL_MS = 5_000;

async function tryFetch(url: string): Promise<LocalStats | null> {
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      // Self-signed cert will cause a network error in the browser —
      // that's fine, we catch it and stay in remote mode.
    });
    if (!res.ok) return null;
    return (await res.json()) as LocalStats;
  } catch {
    return null;
  }
}

/**
 * Probes the local webdash to detect same-network access.
 * Tries the device WiFi IP first, then uconsole.local (mDNS).
 * When local, polls /api/stats every 5 seconds for live data.
 * Re-probes every 30 seconds if not local.
 */
export function useLocalDevice(deviceIp: string | null): LocalDeviceState {
  const [state, setState] = useState<LocalDeviceState>({
    isLocal: false,
    stats: null,
    baseUrl: null,
    probing: true,
  });

  const baseUrlRef = useRef<string | null>(null);

  const probe = useCallback(async () => {
    const candidates: string[] = [];
    if (deviceIp && deviceIp !== "none") {
      candidates.push(`https://${deviceIp}`);
    }
    candidates.push("https://uconsole.local");

    for (const base of candidates) {
      const stats = await tryFetch(`${base}/api/stats`);
      if (stats) {
        baseUrlRef.current = base;
        setState({ isLocal: true, stats, baseUrl: base, probing: false });
        return true;
      }
    }

    baseUrlRef.current = null;
    setState((prev) => ({ ...prev, isLocal: false, stats: null, baseUrl: null, probing: false }));
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
      const stats = await tryFetch(`${base}/api/stats`);
      if (cancelled) return;

      if (stats) {
        setState((prev) => ({ ...prev, stats }));
      } else {
        // Device went away — fall back to remote mode, start re-probing
        baseUrlRef.current = null;
        setState({ isLocal: false, stats: null, baseUrl: null, probing: false });
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, [state.isLocal]);

  return state;
}
