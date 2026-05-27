import { redirect } from "next/navigation";

import { Providers } from "@/components/providers";
import { ThreadList } from "@/components/workspace/ThreadList";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";

export default async function WorkspaceLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const authResult = await getServerSideUser();

    switch (authResult.status) {
        case "authenticated":
            break;

        case "needs_setup":
            redirect("/setup");
            break;

        case "unauthenticated":
            redirect("/login");
            break;

        case "gateway_unavailable":
        case "config_error":
            // 后端不可用时显示错误页面
            return (
                <div className="flex min-h-screen items-center justify-center">
                    <div className="text-center">
                        <h1 className="text-2xl font-bold">Service Unavailable</h1>
                        <p className="mt-2 text-gray-500">
                            {authResult.status === "config_error"
                                ? authResult.message
                                : "Unable to connect to the server. Please try again later."}
                        </p>
                    </div>
                </div>
            );
    }

    return (
        <Providers>
            <AuthProvider initialUser={authResult.user}>
                <div className="flex h-screen">
                    <aside className="w-64 border-r bg-gray-50 p-4">
                        <h2 className="text-lg font-semibold">Workspace</h2>
                        <nav className="mt-4 space-y-2">
                            <a href="/workspace" className="block hover:text-blue-600">
                                Chats
                            </a>
                        </nav>
                        <div className="mt-4">
                            <ThreadList />
                        </div>
                    </aside>
                    <main className="flex-1 overflow-auto">{children}</main>
                </div>
            </AuthProvider>
        </Providers>
    );
}

