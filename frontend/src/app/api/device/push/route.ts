import { NextRequest, NextResponse } from "next/server";
import { validateDeviceToken } from "@/lib/deviceToken";
import { redis } from "@/lib/redis";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function POST(req: NextRequest) {
  // Extract Bearer token
  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return NextResponse.json(
      { error: "Missing Authorization header" },
      { status: 401 }
    );
  }

  const token = authHeader.slice(7);
  if (!UUID_RE.test(token)) {
    return NextResponse.json(
      { error: "Invalid token format" },
      { status: 401 }
    );
  }

  // Validate token — one Redis lookup
  const device = await validateDeviceToken(token);
  if (!device) {
    return NextResponse.json(
      { error: "Invalid or expired device token" },
      { status: 401 }
    );
  }

  // Parse and validate payload
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (!body.hostname || !body.collectedAt) {
    return NextResponse.json(
      { error: "Missing required fields: hostname, collectedAt" },
      { status: 400 }
    );
  }

  // Capture the device's public IP (after NAT) for same-network detection
  const forwarded = req.headers.get("x-forwarded-for");
  const devicePublicIp = forwarded?.split(",")[0].trim() || null;
  if (devicePublicIp) {
    (body as Record<string, unknown>)._publicIp = devicePublicIp;
  }

  // Write to Redis — no TTL, persists until next push.
  // "Online" status is derived from collectedAt age.
  await redis.set(`device:${device.repo}:status`, body);

  return NextResponse.json({ ok: true });
}
