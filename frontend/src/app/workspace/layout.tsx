import { redirect } from "next/navigation";

import { Providers } from "@/components/providers";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";

export default async function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const authResult = await getServerSideUser();

  if (authResult.status === "needs_setup") {
    redirect("/setup");
  }

  if (
    authResult.status === "gateway_unavailable" ||
    authResult.status === "config_error"
  ) {
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

  const user =
    authResult.status === "authenticated" ? authResult.user : null;

  return (
    <Providers>
      <AuthProvider initialUser={user}>
        <WorkspaceShell>{children}</WorkspaceShell>
      </AuthProvider>
    </Providers>
  );
}
