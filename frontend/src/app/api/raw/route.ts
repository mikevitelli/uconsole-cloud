import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { getUserSettings } from "@/lib/redis";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.accessToken || !session.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const path = req.nextUrl.searchParams.get("path");
  if (!path) {
    return NextResponse.json(
      { error: "Missing path parameter" },
      { status: 400 }
    );
  }

  const url = `https://raw.githubusercontent.com/${settings.repo}/main/${path}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `token ${session.accessToken}`,
      "User-Agent": "uconsole-dashboard",
    },
  });

  if (!res.ok) {
    return NextResponse.json(
      { error: `GitHub returned ${res.status}` },
      { status: res.status }
    );
  }

  const body = await res.text();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "s-maxage=60, stale-while-revalidate=300",
    },
  });
}
