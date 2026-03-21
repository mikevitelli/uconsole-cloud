import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

export async function GET() {
  const session = await auth();
  if (!session?.accessToken || !session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const repos: { full_name: string; private: boolean }[] = [];
  let page = 1;

  while (true) {
    const res = await fetch(
      `https://api.github.com/user/repos?per_page=100&sort=updated&page=${page}`,
      {
        headers: {
          Authorization: `token ${session.accessToken}`,
          Accept: "application/vnd.github.v3+json",
          "User-Agent": "uconsole-cloud",
        },
      },
    );

    if (!res.ok) break;

    const data = await res.json();
    if (data.length === 0) break;

    repos.push(
      ...data.map((r: { full_name: string; private: boolean }) => ({
        full_name: r.full_name,
        private: r.private,
      })),
    );

    if (data.length < 100) break;
    if (page >= 10) break;
    page++;
  }

  return NextResponse.json(repos);
}
