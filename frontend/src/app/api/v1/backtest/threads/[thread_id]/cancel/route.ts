import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function getSessionCookie() {
  const cookieStore = await cookies();
  const session = cookieStore.get("access_token");
  return session?.value ? `access_token=${session.value}` : "";
}

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ thread_id: string }> },
) {
  const { thread_id } = await params;
  const cookie = await getSessionCookie();
  if (!cookie) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(
    `${BACKEND_URL}/api/v1/backtest/threads/${thread_id}/cancel`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: cookie,
      },
    },
  );
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}