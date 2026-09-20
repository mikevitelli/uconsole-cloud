import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-helpers";
import { getUserSettings, setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeDeviceTokenValue,
} from "@/lib/deviceToken";
import {
  claimDeviceCode,
  confirmDeviceCode,
  releaseDeviceCode,
} from "@/lib/deviceCode";

/**
 * Undo a confirmation that did not commit: drop this request's token, put the
 * pointer back if it still references it, and hand the code back for a retry.
 */
async function rollback(
  userId: string,
  deviceToken: string | undefined,
  replaced: string | undefined,
  code: string
): Promise<void> {
  if (deviceToken) {
    await revokeDeviceTokenValue(userId, deviceToken);

    // Compare-and-set, not a blind restore. Writing back a snapshot would
    // clobber anything a concurrent request committed in the meantime —
    // including its token pointer, orphaning the credential it just minted.
    const current = await getUserSettings(userId);
    if (current?.deviceToken === deviceToken) {
      await setUserSettings(userId, { ...current, deviceToken: replaced });
    }
  }
  await releaseDeviceCode(code);
}

export async function POST(req: NextRequest) {
  const session = await requireAuth();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { code } = await req.json();
  if (!code || typeof code !== "string") {
    return NextResponse.json({ error: "Code is required" }, { status: 400 });
  }

  const normalized = code.trim().toUpperCase();
  if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(normalized)) {
    return NextResponse.json({ error: "Invalid code format" }, { status: 400 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json(
      { error: "No repository linked. Please link a repo first." },
      { status: 400 }
    );
  }

  // Reserve the code before minting anything. A bad code must not leave a live
  // 90-day token in Redis, and the claim is atomic so two simultaneous
  // confirmations of the same code cannot both mint one.
  const claim = await claimDeviceCode(normalized);
  if (!claim.success) {
    return NextResponse.json({ error: claim.error }, { status: 400 });
  }

  let deviceToken: string | undefined;
  let replaced: string | undefined;

  try {
    const minted = await generateDeviceToken(session.user.id, settings.repo);
    deviceToken = minted.token;
    // What the pointer actually held when it moved, not a snapshot taken at the
    // top of the request. A concurrent link may have superseded that already.
    replaced = minted.replaced;

    const result = await confirmDeviceCode(normalized, deviceToken, settings.repo);

    if (!result.success) {
      await rollback(session.user.id, deviceToken, replaced, normalized);
      return NextResponse.json({ error: result.error }, { status: 400 });
    }
  } catch (err) {
    // A throw between minting and confirming (a failed Redis write, say) would
    // otherwise leave the token live, the pointer moved, and the code claimed
    // until its TTL expires.
    await rollback(session.user.id, deviceToken, replaced, normalized);
    throw err;
  }

  // Superseded only now that the replacement is committed. Revoking earlier
  // would strand a working device if confirmation failed.
  if (replaced && replaced !== deviceToken) {
    await revokeDeviceTokenValue(session.user.id, replaced);
  }

  return NextResponse.json({ success: true, repo: settings.repo });
}
