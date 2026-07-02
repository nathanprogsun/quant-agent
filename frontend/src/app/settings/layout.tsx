import { redirect } from "next/navigation";

import { Providers } from "@/components/providers";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const authResult = await getServerSideUser();

  switch (authResult.status) {
    case "unauthenticated":
      redirect("/login");
      break;
    case "needs_setup":
      redirect("/setup");
      break;
    case "authenticated":
      break;
    case "gateway_unavailable":
    case "config_error":
      // Fail closed: if we cannot confirm the user is authenticated,
      // do not render protected children. Send to login; the page there
      // can surface the backend-down reason via its own error state.
      redirect("/login");
      break;
  }

  const user =
    authResult.status === "authenticated" ? authResult.user : null;

  return (
    <Providers>
      <AuthProvider initialUser={user}>{children}</AuthProvider>
    </Providers>
  );
}
