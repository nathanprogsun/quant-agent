import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function getSessionCookie() {
  const cookieStore = await cookies();
  const session = cookieStore.get("access_token");
  return session?.value ? `access_token=${session.value}` : "";
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ thread_id: string }> }
) {
  try {
    const { thread_id } = await params;
    const cookie = await getSessionCookie();

    const response = await fetch(
      `${BACKEND_URL}/api/v1/threads/${thread_id}/history`,
      {
        headers: { Cookie: cookie },
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Failed to fetch thread history" },
        { status: response.status }
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error("Get thread history proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}

// POST support for LangGraph SDK state history fetch
export async function POST(
  request: Request,
  { params }: { params: Promise<{ thread_id: string }> }
) {
  try {
    const { thread_id } = await params;
    const cookie = await getSessionCookie();
    const body = await request.json().catch(() => ({}));

    const response = await fetch(
      `${BACKEND_URL}/api/v1/threads/${thread_id}/history`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: cookie,
        },
        body: JSON.stringify(body),
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Failed to fetch thread history" },
        { status: response.status }
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error("Get thread history proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
