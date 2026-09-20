import { NextRequest, NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeOtherDeviceTokens,
  withDeviceTokenLock,
  DeviceTokenBusyError,
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

  // Auto-link the new repo under the lock, minting before committing. Writing
  // the settings first meant a failed mint left the dashboard pointing at a
  // repo no device is pushing to, and this handler is not retryable — the
  // repository already exists on GitHub, so the retry comes back 409.
  let deviceToken: string;
  try {
    deviceToken = await withDeviceTokenLock(session.user.id, async () => {
      const { token } = await generateDeviceToken(
        session.user.id,
        result.full_name
      );

      await setUserSettings(session.user.id, {
        repo: result.full_name,
        linkedAt: new Date().toISOString(),
        deviceToken: token,
      });

      // Best-effort for the same reason: the repo exists and the link is
      // committed, so a cleanup outage must not fail the request. Stale tokens
      // stay indexed and the next sweep clears them.
      try {
        await revokeOtherDeviceTokens(session.user.id, token);
      } catch {
        // Still indexed; the next sweep clears them.
      }

      return token;
    });
  } catch (err) {
    if (err instanceof DeviceTokenBusyError) {
      return NextResponse.json(
        { error: "Another device change is in progress. Try again." },
        { status: 409 }
      );
    }
    throw err;
  }

  return NextResponse.json({ repo: result.full_name, deviceToken });
}
