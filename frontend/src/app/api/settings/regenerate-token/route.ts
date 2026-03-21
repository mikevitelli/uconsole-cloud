import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { getUserSettings } from "@/lib/redis";
import { regenerateDeviceToken } from "@/lib/deviceToken";

export async function POST() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const deviceToken = await regenerateDeviceToken(session.user.id, settings.repo);
  return NextResponse.json({ ok: true, deviceToken });
}
