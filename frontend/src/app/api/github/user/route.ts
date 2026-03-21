import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { fetchGitHubUser } from "@/lib/github";

export async function GET() {
  const session = await auth();
  if (!session?.accessToken || !session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const user = await fetchGitHubUser(session.accessToken);
  if (!user) {
    return NextResponse.json(
      { error: "Failed to fetch GitHub user" },
      { status: 500 }
    );
  }

  return NextResponse.json({ login: user.login });
}
