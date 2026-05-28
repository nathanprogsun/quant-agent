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
  { params }: { params: Promise<{ thread_id: string; run_id: string }> }
) {
  try {
    const { thread_id, run_id } = await params;
    const cookie = await getSessionCookie();

    const response = await fetch(
      `${BACKEND_URL}/api/v1/threads/${thread_id}/runs/${run_id}/cancel`,
      {
        method: "POST",
        headers: { Cookie: cookie },
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Failed to cancel run" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Cancel run proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
