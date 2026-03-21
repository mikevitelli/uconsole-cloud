import { NextRequest, NextResponse } from "next/server";
import { pollDeviceCode } from "@/lib/deviceCode";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ secret: string }> }
) {
  const { secret } = await params;

  if (!UUID_RE.test(secret)) {
    return NextResponse.json({ error: "Invalid secret" }, { status: 400 });
  }

  const data = await pollDeviceCode(secret);
  if (!data) {
    return NextResponse.json({ error: "Not found or expired" }, { status: 404 });
  }

  if (data.status === "confirmed") {
    return NextResponse.json({
      status: "confirmed",
      deviceToken: data.deviceToken,
      repo: data.repo,
    });
  }

  return NextResponse.json({ status: "pending" });
}
