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

    // Fetch thread state from backend
    const response = await fetch(
      `${BACKEND_URL}/api/v1/threads/${thread_id}`,
      {
        headers: { Cookie: cookie },
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Thread not found" },
        { status: response.status }
      );
    }

    // Return empty messages array - history is not persisted in this backend
    // The LangGraph SDK expects { messages: [...] } format
    return NextResponse.json({ messages: [] });
  } catch (error) {
    console.error("Get thread history proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
