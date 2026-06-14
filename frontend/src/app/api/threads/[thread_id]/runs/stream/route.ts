import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function getSessionCookie() {
  const cookieStore = await cookies();
  const session = cookieStore.get("access_token");
  return session?.value ? `access_token=${session.value}` : "";
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ thread_id: string }> }
) {
  try {
    const { thread_id } = await params;
    const cookie = await getSessionCookie();

    const body = await request.json();

    const response = await fetch(
      `${BACKEND_URL}/api/v1/threads/${thread_id}/runs/stream`,
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
      const errorText = await response.text();
      console.error("Stream proxy error:", response.status, errorText);
      return NextResponse.json(
        { detail: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    // Proxy SSE stream
    const reader = response.body?.getReader();
    if (!reader) {
      return NextResponse.json(
        { detail: "Failed to read stream" },
        { status: 500 }
      );
    }

    const stream = new ReadableStream({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            controller.enqueue(value);
          }
        } catch (error) {
          console.error("Stream error:", error);
        } finally {
          controller.close();
          reader.releaseLock();
        }
      },
    });

    const responseHeaders: Record<string, string> = {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    };

    const contentLocation = response.headers.get("Content-Location");
    if (contentLocation) {
      responseHeaders["Content-Location"] = contentLocation;
    }

    return new Response(stream, {
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Run stream proxy error:", error);
    return NextResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    );
  }
}
