import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
    try {
        const cookieStore = await cookies();
        const sessionCookie = cookieStore.get("access_token");
        const allCookies = cookieStore.getAll();
        console.log("[/api/v1/auth/me] cookies:", allCookies.map((c) => `${c.name}=${c.value.substring(0, 20)}...`));

        if (!sessionCookie?.value) {
            console.log("[/api/v1/auth/me] No access_token cookie → 401");
            return NextResponse.json(
                { detail: "Not authenticated" },
                { status: 401 }
            );
        }

        console.log("[/api/v1/auth/me] Forwarding to backend with access_token:", sessionCookie.value.substring(0, 20) + "...");
        const response = await fetch(`${BACKEND_URL}/api/v1/auth/me`, {
            headers: {
                Cookie: `access_token=${sessionCookie.value}`,
            },
        });

        console.log("[/api/v1/auth/me] Backend response status:", response.status);
        if (!response.ok) {
            const errBody = await response.text().catch(() => "unreadable");
            console.log("[/api/v1/auth/me] Backend error body:", errBody);
            return NextResponse.json(
                { detail: "Authentication failed" },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error("Me proxy error:", error);
        return NextResponse.json(
            { detail: "Internal server error" },
            { status: 500 }
        );
    }
}
