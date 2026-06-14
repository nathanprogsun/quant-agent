import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
    try {
        const body = await request.json();

        const response = await fetch(`${BACKEND_URL}/api/v1/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const error = await response.json();
            return NextResponse.json(error, { status: response.status });
        }

        const data = await response.json();
        const nextResponse = NextResponse.json(data);
        const setCookie = response.headers.get("set-cookie");
        if (setCookie) {
            const rewritten = setCookie.replace(/;\s*Secure/gi, "");
            nextResponse.headers.set("set-cookie", rewritten);
        }

        return nextResponse;
    } catch (error) {
        console.error("Register proxy error:", error);
        return NextResponse.json(
            { detail: "Internal server error" },
            { status: 500 }
        );
    }
}
