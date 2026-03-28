import { redis } from "./redis";
import type { HardwareManifest } from "./device-config-schema";

// ── Types ──────────────────────────────────────────────

export interface BatteryStatus {
  capacity: number;
  voltage: number;
  current: number;
  status: string;
  health: string;
}

export interface CpuStatus {
  tempC: number;
  loadAvg: [number, number, number];
  cores: number;
}

export interface MemoryStatus {
  totalMB: number;
  usedMB: number;
  availableMB: number;
}

export interface DiskStatus {
  totalGB: number;
  usedGB: number;
  availableGB: number;
  usedPercent: number;
}

export interface WifiStatus {
  ssid: string;
  signalDBm: number;
  quality: number;
  bitrateMbps: number;
  ip: string;
}

export interface AioDevice {
  detected: boolean;
  chip?: string;
}

export interface AioGps {
  detected: boolean;
  hasFix: boolean;
}

export interface AioBoardStatus {
  sdr: AioDevice;
  lora: AioDevice;
  gps: AioGps;
  rtc: { detected: boolean; synced: boolean; time?: string };
}

export interface WebdashStatus {
  running: boolean;
  port: number;
}

export interface WifiFallbackStatus {
  enabled: boolean;
  apName: string;
}

export interface DeviceStatusPayload {
  hostname: string;
  uptime: string;
  uptimeSeconds: number;
  kernel: string;
  battery: BatteryStatus;
  cpu: CpuStatus;
  memory: MemoryStatus;
  disk: DiskStatus;
  wifi: WifiStatus;
  aio: AioBoardStatus;
  screen: { brightness: number; maxBrightness: number };
  webdash?: WebdashStatus;
  wifiFallback?: WifiFallbackStatus;
  /** Hardware manifest from /etc/uconsole/hardware.json — present on devices with uconsole-tools ≥0.1.0 */
  hardware?: HardwareManifest;
  collectedAt: string;
}

// ── Redis fetch ────────────────────────────────────────

const ONLINE_THRESHOLD_MIN = 15;

export interface DeviceStatusResult {
  status: DeviceStatusPayload;
  isOnline: boolean;
  ageMinutes: number;
}

export async function getDeviceStatus(
  repo: string
): Promise<DeviceStatusResult | null> {
  const status = await redis.get<DeviceStatusPayload>(`device:${repo}:status`);
  if (!status) return null;

  if (status.wifiFallback) {
    await redis.set(`device:${repo}:fallback`, status.wifiFallback, {
      ex: 60 * 60 * 24,
    });
  }

  const ageMinutes = Math.floor(
    (Date.now() - new Date(status.collectedAt).getTime()) / 60000
  );
  return { status, isOnline: ageMinutes < ONLINE_THRESHOLD_MIN, ageMinutes };
}

export function formatAge(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
  }
  return `${Math.floor(minutes / 1440)}d ago`;
}

export async function getLastKnownFallback(
  repo: string
): Promise<WifiFallbackStatus | null> {
  return redis.get<WifiFallbackStatus>(`device:${repo}:fallback`);
}
