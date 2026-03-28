import { NextRequest, NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { getUserSettings } from "@/lib/redis";

export async function GET(req: NextRequest) {
  const session = await requireAuthWithToken();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const path = req.nextUrl.searchParams.get("path") || "";
  if (path && !/^[\w\-./]+$/.test(path)) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  if (path.includes("..")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  const url = `https://api.github.com/repos/${settings.repo}${path ? "/" + path : ""}`;

  const res = await fetch(url, {
    headers: {
      Authorization: `token ${session.accessToken}`,
      Accept: "application/vnd.github.v3+json",
      "User-Agent": "uconsole-cloud",
    },
  });

  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "s-maxage=60, stale-while-revalidate=300",
    },
  });
}
