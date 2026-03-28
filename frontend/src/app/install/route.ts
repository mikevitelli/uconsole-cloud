import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";

export async function GET() {
  const script = await readFile(
    join(process.cwd(), "public", "install.sh"),
    "utf-8"
  );
  return new NextResponse(script, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
