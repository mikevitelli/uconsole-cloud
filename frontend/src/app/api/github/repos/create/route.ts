import { NextRequest, NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeOtherDeviceTokens,
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

  // Auto-link the new repo, minting before committing. Writing the settings
  // first meant a failed mint left the dashboard pointing at a repo no device
  // is pushing to, and this handler is not retryable — the repository already
  // exists on GitHub, so the retry comes back 409.
  const { token: deviceToken } = await generateDeviceToken(
    session.user.id,
    result.full_name
  );

  await setUserSettings(session.user.id, {
    repo: result.full_name,
    linkedAt: new Date().toISOString(),
    deviceToken,
  });

  // Best-effort for the same reason: the repo exists and the link is committed,
  // so a cleanup outage must not fail the request. Stale tokens stay indexed
  // and the next sweep clears them.
  try {
    await revokeOtherDeviceTokens(session.user.id, deviceToken);
  } catch {
    // Still indexed; the next sweep clears them.
  }

  return NextResponse.json({ repo: result.full_name, deviceToken });
}
