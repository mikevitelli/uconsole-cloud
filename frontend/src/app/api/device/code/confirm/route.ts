import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-helpers";
import { getUserSettings } from "@/lib/redis";
import { generateDeviceToken } from "@/lib/deviceToken";
import { confirmDeviceCode } from "@/lib/deviceCode";

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

  const deviceToken = await generateDeviceToken(session.user.id, settings.repo);
  const result = await confirmDeviceCode(normalized, deviceToken, settings.repo);

  if (!result.success) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  return NextResponse.json({ success: true, repo: settings.repo });
}
