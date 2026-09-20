import { NextRequest, NextResponse } from "next/server";
import { requireAuth, requireAuthWithToken } from "@/lib/api-helpers";
import {
  getUserSettings,
  setUserSettings,
  deleteUserSettings,
} from "@/lib/redis";
import { validateUconsoleRepo } from "@/lib/github";
import {
  generateDeviceToken,
  revokeDeviceToken,
  revokeDeviceTokenValue,
} from "@/lib/deviceToken";

export async function GET() {
  const session = await requireAuth();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const settings = await getUserSettings(session.user.id);
  return NextResponse.json(settings);
}

export async function POST(req: NextRequest) {
  const session = await requireAuthWithToken();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { repo } = await req.json();
  if (!repo || typeof repo !== "string" || !/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(repo.trim())) {
    return NextResponse.json(
      { error: "Invalid repo format. Use owner/repo" },
      { status: 400 }
    );
  }

  const valid = await validateUconsoleRepo(session.accessToken, repo.trim());
  if (!valid) {
    return NextResponse.json(
      { error: "Could not find a valid uconsole backup repo at that path" },
      { status: 400 }
    );
  }

  // Capture the outgoing credential before the write below drops the pointer,
  // or nothing will be able to name it afterwards.
  const prior = (await getUserSettings(session.user.id))?.deviceToken;

  await setUserSettings(session.user.id, {
    repo: repo.trim(),
    linkedAt: new Date().toISOString(),
  });

  const { token: deviceToken } = await generateDeviceToken(
    session.user.id,
    repo.trim()
  );

  // Retire the old credential only now that a usable replacement is committed.
  // Revoking first would disconnect a working device and leave nothing in its
  // place if either step above failed. Best-effort: the link has succeeded, and
  // a cleanup outage must not report it as a failure — the token stays in the
  // per-user index either way, so it remains revocable.
  if (prior && prior !== deviceToken) {
    try {
      await revokeDeviceTokenValue(session.user.id, prior);
    } catch {
      // Still indexed; unlink or a later relink will clear it.
    }
  }

  return NextResponse.json({ ok: true, deviceToken });
}

export async function DELETE() {
  const session = await requireAuth();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  await revokeDeviceToken(session.user.id);
  await deleteUserSettings(session.user.id);
  return NextResponse.json({ ok: true });
}
