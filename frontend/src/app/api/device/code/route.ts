import { NextResponse } from "next/server";
import { generateDeviceCode } from "@/lib/deviceCode";

export async function POST() {
  try {
    const result = await generateDeviceCode();
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { error: "Failed to generate code" },
      { status: 500 }
    );
  }
}
