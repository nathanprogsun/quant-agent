import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

async function getSessionCookie() {
  const cookieStore = await cookies()
  const session = cookieStore.get('access_token')
  return session?.value ? `access_token=${session.value}` : ''
}

export async function GET() {
  try {
    const cookie = await getSessionCookie()
    if (!cookie) {
      return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const response = await fetch(`${BACKEND_URL}/api/skills/disclosure`, {
      headers: { Cookie: cookie },
    })

    const data = await response.json().catch(() => ({ detail: 'Invalid response' }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Skills disclosure proxy error:', error)
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 })
  }
}
