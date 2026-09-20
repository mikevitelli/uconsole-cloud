import { NextRequest, NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { getUserSettings, setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeDeviceTokenValue,
} from "@/lib/deviceToken";
import { createBootstrapRepo } from "@/lib/github";

const NAME_RE = /^[a-zA-Z0-9_.-]+$/;

export async function POST(req: NextRequest) {
  const session = await requireAuthWithToken();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const isPrivate = body.private !== false;

  if (!name || !NAME_RE.test(name) || name.length > 100) {
    return NextResponse.json(
      { error: "Invalid repository name" },
      { status: 400 }
    );
  }

  const result = await createBootstrapRepo(session.accessToken, name, isPrivate);

  if ("error" in result) {
    const status = result.error.includes("already exists") ? 409 : 500;
    return NextResponse.json({ error: result.error }, { status });
  }

  // Auto-link the new repo. Capture the outgoing credential before the write
  // below drops the pointer, or nothing can name it afterwards.
  const prior = (await getUserSettings(session.user.id))?.deviceToken;

  await setUserSettings(session.user.id, {
    repo: result.full_name,
    linkedAt: new Date().toISOString(),
  });
  const { token: deviceToken } = await generateDeviceToken(
    session.user.id,
    result.full_name
  );

  // Retire the old credential only after the replacement is committed. The
  // repository already exists on GitHub at this point, so a failure here is not
  // retryable — it comes back 409 — and must not disconnect the device too.
  if (prior && prior !== deviceToken) {
    try {
      await revokeDeviceTokenValue(session.user.id, prior);
    } catch {
      // Still indexed; unlink or a later relink will clear it.
    }
  }

  return NextResponse.json({ repo: result.full_name, deviceToken });
}
