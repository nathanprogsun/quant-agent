import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

async function getSessionCookie() {
  const cookieStore = await cookies()
  const session = cookieStore.get('access_token')
  return session?.value ? `access_token=${session.value}` : ''
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const cookie = await getSessionCookie()
    if (!cookie) {
      return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const response = await fetch(`${BACKEND_URL}/api/v1/backtest/${id}/stream`, {
      headers: {
        Cookie: cookie,
      },
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backtest stream proxy error:', response.status, errorText)
      return NextResponse.json(
        { detail: `Backend error: ${response.status}` },
        { status: response.status },
      )
    }

    const reader = response.body?.getReader()
    if (!reader) {
      return NextResponse.json({ detail: 'Failed to read stream' }, { status: 500 })
    }

    const stream = new ReadableStream({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            controller.enqueue(value)
          }
        } catch (error) {
          console.error('Backtest stream error:', error)
        } finally {
          controller.close()
          reader.releaseLock()
        }
      },
    })

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  } catch (error) {
    console.error('Backtest stream proxy error:', error)
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 })
  }
}
