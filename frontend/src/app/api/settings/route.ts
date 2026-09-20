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
  revokeOtherDeviceTokens,
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

  // Mint before committing anything. Writing the new repo first and minting
  // after meant a failed mint returned an error having already moved the
  // dashboard to a repo the device knows nothing about, with the old
  // credential still live and still pushing to the old one.
  const { token: deviceToken } = await generateDeviceToken(
    session.user.id,
    repo.trim()
  );

  // Repo and pointer in a single write. generateDeviceToken put the pointer on
  // the previous settings; carrying it here is what keeps the new credential
  // named after the repo changes.
  await setUserSettings(session.user.id, {
    repo: repo.trim(),
    linkedAt: new Date().toISOString(),
    deviceToken,
  });

  // Every other credential is stale now that the replacement is committed.
  // Sweeping the index rather than the one value this request displaced also
  // retries a cleanup an earlier relink failed to finish.
  //
  // Best-effort: the link has succeeded, so a cleanup outage must not report it
  // as a failure. The stale tokens stay indexed, so the next relink, regenerate
  // or unlink sweeps them.
  try {
    await revokeOtherDeviceTokens(session.user.id, deviceToken);
  } catch {
    // Still indexed; the next sweep clears them.
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
