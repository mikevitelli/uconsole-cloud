import { redis } from "./redis";

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
  collectedAt: string;
}

// ── Redis fetch ────────────────────────────────────────

export async function getDeviceStatus(
  repo: string
): Promise<DeviceStatusPayload | null> {
  const status = await redis.get<DeviceStatusPayload>(`device:${repo}:status`);

  // Persist wifi-fallback state with longer TTL so we can show
  // smart offline messaging after the status TTL expires
  if (status?.wifiFallback) {
    await redis.set(`device:${repo}:fallback`, status.wifiFallback, {
      ex: 60 * 60 * 24, // 24 hours
    });
  }

  return status;
}

export async function getLastKnownFallback(
  repo: string
): Promise<WifiFallbackStatus | null> {
  return redis.get<WifiFallbackStatus>(`device:${repo}:fallback`);
}
