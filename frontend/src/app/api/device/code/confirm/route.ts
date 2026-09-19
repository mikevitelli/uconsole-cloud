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

  // Hold the outgoing token: generateDeviceToken overwrites the settings
  // reference, and once that pointer moves the old value is unreachable.
  const priorToken = settings.deviceToken;

  const deviceToken = await generateDeviceToken(session.user.id, settings.repo);
  const result = await confirmDeviceCode(normalized, deviceToken, settings.repo);

  if (!result.success) {
    // Confirmation lost a race (the code expired between claim and write).
    // Roll the new token back rather than leaving it orphaned.
    await revokeDeviceTokenValue(deviceToken);

    // Compare-and-set, not a blind restore. Writing back the snapshot taken at
    // the top of the request would clobber anything a concurrent request
    // committed in the meantime — including its token pointer, orphaning the
    // live credential it just minted. Only revert what this request moved.
    const current = await getUserSettings(session.user.id);
    if (current?.deviceToken === deviceToken) {
      await setUserSettings(session.user.id, {
        ...current,
        deviceToken: priorToken,
      });
    }

    // Let a legitimate retry take the code again.
    await releaseDeviceCode(normalized);
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  // Superseded only now that the replacement is committed. Revoking earlier
  // would strand a working device if confirmation failed.
  if (priorToken && priorToken !== deviceToken) {
    await revokeDeviceTokenValue(priorToken);
  }

  return NextResponse.json({ success: true, repo: settings.repo });
}
