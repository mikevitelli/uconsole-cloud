import { NextResponse } from "next/server";
import { redis } from "@/lib/redis";

export async function GET() {
  const checks: Record<string, "ok" | "error"> = {};

  // Redis connectivity
  try {
    await redis.ping();
    checks.redis = "ok";
  } catch {
    checks.redis = "error";
  }

  const healthy = Object.values(checks).every((v) => v === "ok");

  return NextResponse.json(
    { status: healthy ? "healthy" : "degraded", checks },
    { status: healthy ? 200 : 503 }
  );
}
