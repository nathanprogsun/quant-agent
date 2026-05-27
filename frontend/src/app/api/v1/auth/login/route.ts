import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
    try {
        const body = await request.json();

        const response = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const error = await response.json();
            return NextResponse.json(error, { status: response.status });
        }

        const data = await response.json();

        // 转发后端设置的 cookie
        const nextResponse = NextResponse.json(data);
        const setCookie = response.headers.get("set-cookie");
        if (setCookie) {
            // Rewrite secure cookies to non-secure for local dev (http://localhost)
            const rewritten = setCookie.replace(/;\s*Secure/gi, "");
            nextResponse.headers.set("set-cookie", rewritten);
            console.log("[login] set-cookie (original):", setCookie);
            console.log("[login] set-cookie (rewritten):", rewritten);
        } else {
            console.log("[login] WARNING: backend returned no set-cookie header");
        }

        return nextResponse;
    } catch (error) {
        console.error("Login proxy error:", error);
        return NextResponse.json(
            { detail: "Internal server error" },
            { status: 500 }
        );
    }
}
