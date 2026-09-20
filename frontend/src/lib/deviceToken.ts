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
 * Revoke every token this user holds except `keep`.
 *
 * Every flow that mints a replacement calls this rather than revoking the one
 * value it displaced. Sweeping the whole index means a cleanup that failed on
 * an earlier relink is retried here instead of leaving that credential live
 * for the rest of its 90 days.
 */
export async function revokeOtherDeviceTokens(
  userId: string,
  keep: string
): Promise<void> {
  const stale = (await redis.smembers<string[]>(tokenIndexKey(userId))).filter(
    (t) => t !== keep
  );
  if (stale.length === 0) return;

  await redis.del(...stale.map((t) => `devicetoken:${t}`));
  await redis.srem(tokenIndexKey(userId), ...stale);
}

/**
 * Revoke every token this user holds, not just the one settings point at.
 *
 * Callers (unlink, repo delete) mean "this user's devices lose access". Going
 * through the pointer alone left every superseded token live.
 *
 * Settings are the caller's to update: both callers delete them outright right
 * after. Clearing the pointer here meant reading it, comparing it and writing
 * it back as three separate round trips, and a mint landing inside that window
 * had its pointer overwritten — the replacement credential stayed live and
 * indexed with nothing in settings naming it.
 */
export async function revokeDeviceToken(userId: string): Promise<void> {
  const tokens = await redis.smembers<string[]>(tokenIndexKey(userId));

  // Cover a token minted before this index existed, which only the pointer
  // knows about.
  const pointer = (await getUserSettings(userId))?.deviceToken;
  const all =
    pointer && !tokens.includes(pointer) ? [...tokens, pointer] : tokens;
  if (all.length === 0) return;

  await redis.del(...all.map((t) => `devicetoken:${t}`));
  // Remove exactly what was snapshotted rather than deleting the index key.
  // A concurrent mint that indexed a token after the snapshot keeps its
  // membership, so its credential stays revocable instead of being stranded.
  await redis.srem(tokenIndexKey(userId), ...all);
}

/**
 * Replace the device credential with a fresh one.
 *
 * Mint first: revoking first left the device dead with nothing in its place if
 * the mint then failed. The sweep is allowed to throw — retiring the old
 * credential is the whole point of regenerating, so a failure here must be
 * reported rather than swallowed. The next regenerate or relink sweeps again.
 */
export async function regenerateDeviceToken(
  userId: string,
  repo: string
): Promise<string> {
  const { token } = await generateDeviceToken(userId, repo);
  await revokeOtherDeviceTokens(userId, token);
  return token;
}
