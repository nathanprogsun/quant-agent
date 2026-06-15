import { redirect } from "next/navigation";

import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";

export default async function AuthLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const authResult = await getServerSideUser();

    switch (authResult.status) {
        case "authenticated":
            // 已登录用户访问 login/setup → 重定向到 workspace
            redirect("/workspace");
            break;

        case "needs_setup":
            // Fresh install: allow setup (and login) pages to render.
            break;

        case "unauthenticated":
            // 未登录 → 允许访问 login/setup pages
            break;

        case "gateway_unavailable":
        case "config_error":
            // 后端不可用 → 允许访问，显示错误状态
            break;
    }

    return <AuthProvider initialUser={null}>{children}</AuthProvider>;
}

