import { randomUUID } from "crypto";
import { redis } from "./redis";
import { getUserSettings, setUserSettings } from "./redis";

const TOKEN_TTL = 60 * 60 * 24 * 90; // 90 days

interface DeviceTokenData {
  userId: string;
  repo: string;
  createdAt: string;
}

export async function generateDeviceToken(
  userId: string,
  repo: string
): Promise<string> {
  const token = randomUUID();
  const data: DeviceTokenData = {
    userId,
    repo,
    createdAt: new Date().toISOString(),
  };

  await redis.set(`devicetoken:${token}`, data, { ex: TOKEN_TTL });

  // Store token reference in user settings
  const settings = await getUserSettings(userId);
  if (settings) {
    await setUserSettings(userId, { ...settings, deviceToken: token });
  }

  return token;
}

export async function validateDeviceToken(
  token: string
): Promise<{ userId: string; repo: string } | null> {
  const data = await redis.get<DeviceTokenData>(`devicetoken:${token}`);
  if (!data) return null;
  return { userId: data.userId, repo: data.repo };
}

export async function revokeDeviceToken(userId: string): Promise<void> {
  const settings = await getUserSettings(userId);
  if (settings?.deviceToken) {
    await redis.del(`devicetoken:${settings.deviceToken}`);
    await setUserSettings(userId, {
      repo: settings.repo,
      linkedAt: settings.linkedAt,
    });
  }
}

export async function regenerateDeviceToken(
  userId: string,
  repo: string
): Promise<string> {
  await revokeDeviceToken(userId);
  return generateDeviceToken(userId, repo);
}
