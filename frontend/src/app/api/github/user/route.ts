import { NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { fetchGitHubUser } from "@/lib/github";

export async function GET() {
  const session = await requireAuthWithToken();
  if (!session) {
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
