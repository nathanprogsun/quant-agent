import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/v1/auth/setup-status`, {
            method: "GET",
            headers: { "Content-Type": "application/json" },
        });

        if (!response.ok) {
            const error = await response.json();
            return NextResponse.json(error, { status: response.status });
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error("Setup status proxy error:", error);
        return NextResponse.json(
            { detail: "Internal server error" },
            { status: 500 }
        );
    }
}
