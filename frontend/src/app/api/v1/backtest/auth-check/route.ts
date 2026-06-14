import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

async function forwardAuthCheck() {
  const cookieStore = await cookies()
  const sessionCookie = cookieStore.get('access_token')
  if (!sessionCookie?.value) {
    return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })
  }

  const response = await fetch(`${BACKEND_URL}/api/v1/backtest/auth-check`, {
    headers: {
      Cookie: `access_token=${sessionCookie.value}`,
    },
  })

  const data = await response.json().catch(() => ({ detail: 'Invalid response' }))
  return NextResponse.json(data, { status: response.status })
}

export async function GET() {
  try {
    return await forwardAuthCheck()
  } catch (error) {
    console.error('Backtest auth-check proxy error:', error)
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 })
  }
}

export async function POST() {
  try {
    return await forwardAuthCheck()
  } catch (error) {
    console.error('Backtest auth-check proxy error:', error)
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 })
  }
}
