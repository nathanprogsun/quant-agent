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
      `${BACKEND_URL}/api/v1/threads/${thread_id}/runs`,
      {
        headers: { Cookie: cookie },
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Failed to fetch runs" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("List runs proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
