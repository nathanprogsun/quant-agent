import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function getSessionCookie() {
  const cookieStore = await cookies();
  const session = cookieStore.get("access_token");
  return session?.value ? `access_token=${session.value}` : "";
}

async function proxyJson(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const cookie = await getSessionCookie();
  return fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Cookie: cookie,
    },
  });
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ thread_id: string }> }
) {
  try {
    const { thread_id } = await params;

    const response = await proxyJson(`/api/v1/threads/${thread_id}/history`);

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

export async function POST(
  request: Request,
  { params }: { params: Promise<{ thread_id: string }> }
) {
  try {
    const { thread_id } = await params;
    const body = await request.json();

    const response = await proxyJson(`/api/v1/threads/${thread_id}/history`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: "Failed to fetch thread history",
      }));
      return NextResponse.json(error, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error("Post thread history proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
