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

  // From here the token key exists. Anything that throws before the caller
  // receives it leaves a live credential nothing references or can reach —
  // the exact orphan this module exists to prevent — so undo it on the way out.
  try {
    // Index before the pointer moves, so the token is revocable even if the
    // write below never lands.
    await redis.sadd(tokenIndexKey(userId), token);
    await redis.expire(tokenIndexKey(userId), TOKEN_TTL);

    // Read the pointer as late as possible and report what was actually
    // displaced. Callers that revoke a value captured earlier in the request
    // can revoke a token a concurrent write already superseded.
    const settings = await getUserSettings(userId);
    const replaced = settings?.deviceToken;
    if (settings) {
      await setUserSettings(userId, { ...settings, deviceToken: token });
    }

    return { token, replaced };
  } catch (err) {
    await discard(userId, token);
    throw err;
  }
}

/** Best-effort removal of a token the caller never got to use. */
async function discard(userId: string, token: string): Promise<void> {
  try {
    await redis.del(`devicetoken:${token}`);
    await redis.srem(tokenIndexKey(userId), token);
  } catch {
    // Nothing better to do: the original failure is what the caller needs to
    // see, and the token is in the index if that part landed.
  }
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
    // Remove exactly what was snapshotted rather than deleting the index key.
    // A concurrent mint that indexed a token after the snapshot keeps its
    // membership, so its credential stays revocable instead of being stranded.
    await redis.srem(tokenIndexKey(userId), ...tokens);
  }

  const settings = await getUserSettings(userId);
  if (settings?.deviceToken) {
    // Cover a token minted before this index existed.
    if (!tokens.includes(settings.deviceToken)) {
      await redis.del(`devicetoken:${settings.deviceToken}`);
    }
    // Compare-and-set: only clear the pointer if it still references a token
    // this call actually revoked. A concurrent mint may have moved it to a
    // live token, and clearing that would orphan it.
    const current = await getUserSettings(userId);
    if (current?.deviceToken && current.deviceToken === settings.deviceToken) {
      await setUserSettings(userId, {
        repo: current.repo,
        linkedAt: current.linkedAt,
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
