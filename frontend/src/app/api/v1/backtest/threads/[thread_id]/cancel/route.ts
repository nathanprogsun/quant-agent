import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ thread_id: string }> },
) {
  const { thread_id } = await params;
  const response = await fetch(
    `${BACKEND_URL}/api/v1/backtest/threads/${thread_id}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  );
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}