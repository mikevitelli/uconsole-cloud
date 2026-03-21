import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { getUserSettings } from "@/lib/redis";
import { getDeviceStatus } from "@/lib/deviceStatus";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const status = await getDeviceStatus(settings.repo);
  if (!status) {
    return NextResponse.json({ online: false, status: null });
  }

  const collectedAt = new Date(status.collectedAt).getTime();
  const ageMinutes = Math.floor((Date.now() - collectedAt) / 60000);

  return NextResponse.json(
    { online: true, ageMinutes, status },
    {
      headers: {
        "Cache-Control": "s-maxage=30, stale-while-revalidate=120",
      },
    }
  );
}
