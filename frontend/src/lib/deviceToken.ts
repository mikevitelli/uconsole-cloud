import { randomUUID } from "crypto";
import { redis } from "./redis";
import { getUserSettings, setUserSettings } from "./redis";

const TOKEN_TTL = 60 * 60 * 24 * 90; // 90 days

interface DeviceTokenData {
  userId: string;
  repo: string;
  createdAt: string;
}

/**
 * Index of every live token a user holds.
 *
 * `settings.deviceToken` is a single pointer, and several flows move or clear
 * it: linking a repo rewrites settings without the field, creating a repo does
 * the same, and two concurrent links can each overwrite the other. Any token
 * the pointer stops referencing was previously unreachable — still valid in
 * Redis for the rest of its 90 days, with nothing able to revoke it.
 *
 * Membership here does not expire with the pointer, so revocation can always
 * reach every token. The pointer stays as the *current* token for the device;
 * this set is the full set of tokens to clean up.
 */
function tokenIndexKey(userId: string): string {
  return `usertokens:${userId}`;
}

export async function generateDeviceToken(
  userId: string,
  repo: string
): Promise<{ token: string; replaced?: string }> {
  const token = randomUUID();
  const data: DeviceTokenData = {
    userId,
    repo,
    createdAt: new Date().toISOString(),
  };

  await redis.set(`devicetoken:${token}`, data, { ex: TOKEN_TTL });

  // Index before the pointer moves, so the token is revocable even if the
  // write below never lands.
  await redis.sadd(tokenIndexKey(userId), token);
  await redis.expire(tokenIndexKey(userId), TOKEN_TTL);

  // Read the pointer as late as possible and report what was actually
  // displaced. Callers that revoke a value captured earlier in the request can
  // revoke a token that a concurrent write already superseded.
  const settings = await getUserSettings(userId);
  const replaced = settings?.deviceToken;
  if (settings) {
    await setUserSettings(userId, { ...settings, deviceToken: token });
  }

  return { token, replaced };
}

export async function validateDeviceToken(
  token: string
): Promise<{ userId: string; repo: string } | null> {
  const data = await redis.get<DeviceTokenData>(`devicetoken:${token}`);
  if (!data) return null;
  return { userId: data.userId, repo: data.repo };
}

/**
 * Delete one token by value, whether or not settings still reference it.
 */
export async function revokeDeviceTokenValue(
  userId: string,
  token: string
): Promise<void> {
  await redis.del(`devicetoken:${token}`);
  await redis.srem(tokenIndexKey(userId), token);
}

/**
 * Revoke every token this user holds, not just the one settings point at.
 *
 * Callers (unlink, repo delete) mean "this user's devices lose access". Going
 * through the pointer alone left every superseded token live.
 */
export async function revokeDeviceToken(userId: string): Promise<void> {
  const tokens = await redis.smembers<string[]>(tokenIndexKey(userId));
  if (tokens.length > 0) {
    await redis.del(...tokens.map((t) => `devicetoken:${t}`));
  }
  await redis.del(tokenIndexKey(userId));

  const settings = await getUserSettings(userId);
  if (settings) {
    // Cover a token minted before this index existed.
    if (settings.deviceToken && !tokens.includes(settings.deviceToken)) {
      await redis.del(`devicetoken:${settings.deviceToken}`);
    }
    if (settings.deviceToken) {
      await setUserSettings(userId, {
        repo: settings.repo,
        linkedAt: settings.linkedAt,
      });
    }
  }
}

export async function regenerateDeviceToken(
  userId: string,
  repo: string
): Promise<string> {
  await revokeDeviceToken(userId);
  const { token } = await generateDeviceToken(userId, repo);
  return token;
}
