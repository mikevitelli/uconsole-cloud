import { NextRequest, NextResponse } from "next/server";
import { validateDeviceToken } from "@/lib/deviceToken";
import { redis } from "@/lib/redis";
import { checkRateLimit } from "@/lib/rateLimit";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
// RFC 1123-ish hostname charset. Permissive enough for typical device
// hostnames (kebab and underscore allowed) without being a free-for-all.
const HOSTNAME_RE = /^[a-zA-Z0-9._-]+$/;

// 32 KB is a generous ceiling — real push-status.sh payloads are
// ~1-2 KB. Keeps a leaked token from bloating Redis with arbitrary JSON.
const MAX_BODY_BYTES = 32 * 1024;
// 30 pushes/min lets the default 60s interval breathe (the device timer
// drifts slightly) while capping abuse to ~one write every 2s.
const PUSH_RATE_LIMIT = 30;
const PUSH_RATE_WINDOW = 60;

function isValidTelemetry(
  body: unknown
): body is { hostname: string; collectedAt: string } {
  if (!body || typeof body !== "object") return false;
  const b = body as Record<string, unknown>;
  if (typeof b.hostname !== "string") return false;
  if (b.hostname.length === 0 || b.hostname.length > 64) return false;
  if (!HOSTNAME_RE.test(b.hostname)) return false;
  if (typeof b.collectedAt !== "string") return false;
  if (b.collectedAt.length > 64) return false;
  if (Number.isNaN(Date.parse(b.collectedAt))) return false;
  return true;
}

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

  // Rate-limit per token. A leaked token is an inevitability we can't
  // detect; capping write rate keeps it from being weaponized into a
  // Redis bloat / DoS / log-spam channel.
  const rl = await checkRateLimit(
    `device-push:${token}`,
    PUSH_RATE_LIMIT,
    PUSH_RATE_WINDOW
  );
  if (!rl.allowed) {
    return NextResponse.json(
      { error: "Rate limit exceeded" },
      {
        status: 429,
        headers: { "Retry-After": String(rl.retryAfterSeconds ?? PUSH_RATE_WINDOW) },
      }
    );
  }

  // Pre-parse size cap via Content-Length. Some clients omit it; the
  // post-parse check below is the real gate.
  const declaredLen = parseInt(req.headers.get("content-length") || "0", 10);
  if (declaredLen > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "Payload too large" }, { status: 413 });
  }

  // Parse and validate payload
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  // Real size check on the serialized body — Content-Length can lie.
  const serialized = JSON.stringify(body ?? null);
  if (serialized.length > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "Payload too large" }, { status: 413 });
  }

  if (!isValidTelemetry(body)) {
    return NextResponse.json(
      { error: "Invalid telemetry: hostname and collectedAt required" },
      { status: 400 }
    );
  }

  const out = body as Record<string, unknown>;

  // Capture the device's public IP (after NAT) for same-network detection
  const forwarded = req.headers.get("x-forwarded-for");
  const devicePublicIp = forwarded?.split(",")[0].trim() || null;
  if (devicePublicIp) {
    out._publicIp = devicePublicIp;
  }

  // Write to Redis — no TTL, persists until next push.
  // "Online" status is derived from collectedAt age.
  await redis.set(`device:${device.repo}:status`, out);

  return NextResponse.json({ ok: true });
}
