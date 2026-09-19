import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-helpers";
import { getUserSettings, setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeDeviceTokenValue,
} from "@/lib/deviceToken";
import { confirmDeviceCode, validateDeviceCode } from "@/lib/deviceCode";

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

  // Reject a bad code before minting anything. Otherwise a mistyped or
  // expired code still leaves a live 90-day token in Redis.
  const precheck = await validateDeviceCode(normalized);
  if (!precheck.success) {
    return NextResponse.json({ error: precheck.error }, { status: 400 });
  }

  // Hold the outgoing token: generateDeviceToken overwrites the settings
  // reference, and once that pointer moves the old value is unreachable.
  const priorToken = settings.deviceToken;

  const deviceToken = await generateDeviceToken(session.user.id, settings.repo);
  const result = await confirmDeviceCode(normalized, deviceToken, settings.repo);

  if (!result.success) {
    // Confirmation lost a race (code expired or was claimed between the
    // precheck and here). Roll the new token back rather than leaving it
    // orphaned, and restore the pointer so the live device stays revocable.
    await revokeDeviceTokenValue(deviceToken);
    await setUserSettings(session.user.id, { ...settings });
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  // Superseded only now that the replacement is committed. Revoking earlier
  // would strand a working device if confirmation failed.
  if (priorToken && priorToken !== deviceToken) {
    await revokeDeviceTokenValue(priorToken);
  }

  return NextResponse.json({ success: true, repo: settings.repo });
}
