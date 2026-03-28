import { NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-helpers";
import { getUserSettings } from "@/lib/redis";
import { getDeviceStatus } from "@/lib/deviceStatus";

export async function GET() {
  const session = await requireAuth();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const result = await getDeviceStatus(settings.repo);
  if (!result) {
    return NextResponse.json({ online: false, status: null });
  }

  return NextResponse.json(
    { online: result.isOnline, ageMinutes: result.ageMinutes, status: result.status },
    {
      headers: {
        "Cache-Control": "s-maxage=30, stale-while-revalidate=120",
      },
    }
  );
}
