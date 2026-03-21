import { Redis } from "@upstash/redis";
import type { UserSettings } from "./types";

export const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});

export async function getUserSettings(
  userId: string
): Promise<UserSettings | null> {
  return redis.get<UserSettings>(`user:${userId}`);
}

export async function setUserSettings(
  userId: string,
  settings: UserSettings
): Promise<void> {
  await redis.set(`user:${userId}`, settings);
}

export async function deleteUserSettings(userId: string): Promise<void> {
  await redis.del(`user:${userId}`);
}
