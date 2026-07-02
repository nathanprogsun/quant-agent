import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

async function getSessionCookie() {
  const cookieStore = await cookies()
  const session = cookieStore.get('access_token')
  return session?.value ? `access_token=${session.value}` : ''
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ name: string }> },
) {
  try {
    const cookie = await getSessionCookie()
    if (!cookie) {
      return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const { name } = await params
    const body = await request.json()
    const response = await fetch(`${BACKEND_URL}/api/skills/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Cookie: cookie,
      },
      body: JSON.stringify(body),
    })

    const data = await response.json().catch(() => ({ detail: 'Invalid response' }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Skills toggle proxy error:', error)
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 })
  }
}
