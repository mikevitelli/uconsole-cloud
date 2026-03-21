import { Redis } from "@upstash/redis";
import type { UserSettings } from "./types";

export const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});

export async function getUserSettings(
  userId: string
): Promise<UserSettings | null> {
  const settings = await redis.get<UserSettings>(`user:${userId}`);
  if (settings) {
    await redis.expire(`user:${userId}`, 60 * 60 * 24 * 90);
  }
  return settings;
}

export async function setUserSettings(
  userId: string,
  settings: UserSettings
): Promise<void> {
  await redis.set(`user:${userId}`, settings, { ex: 60 * 60 * 24 * 90 });
}

export async function deleteUserSettings(userId: string): Promise<void> {
  await redis.del(`user:${userId}`);
}
