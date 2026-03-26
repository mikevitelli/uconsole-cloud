import { NextRequest, NextResponse } from "next/server";
import { generateDeviceCode } from "@/lib/deviceCode";
import { checkRateLimit } from "@/lib/rateLimit";

export async function POST(request: NextRequest) {
  try {
    const ip =
      request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
      "unknown";
    const { allowed, retryAfterSeconds } = await checkRateLimit(
      `devicecode:${ip}`,
      5,
      60
    );
    if (!allowed) {
      return NextResponse.json(
        { error: "Too many requests. Try again later." },
        {
          status: 429,
          headers: { "Retry-After": String(retryAfterSeconds) },
        }
      );
    }

    const result = await generateDeviceCode();
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { error: "Failed to generate code" },
      { status: 500 }
    );
  }
}
