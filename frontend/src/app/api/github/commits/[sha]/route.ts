import { NextResponse } from "next/server";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { getUserSettings } from "@/lib/redis";
import { fetchCommitDetail } from "@/lib/github";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ sha: string }> }
) {
  const session = await requireAuthWithToken();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) {
    return NextResponse.json({ error: "No repo linked" }, { status: 400 });
  }

  const { sha } = await params;
  if (!/^[0-9a-f]{7,40}$/i.test(sha)) {
    return NextResponse.json({ error: "Invalid SHA" }, { status: 400 });
  }
  const detail = await fetchCommitDetail(
    session.accessToken,
    settings.repo,
    sha
  );

  if (!detail) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  return NextResponse.json(detail, {
    headers: {
      "Cache-Control": "s-maxage=300, stale-while-revalidate=600",
    },
  });
}
