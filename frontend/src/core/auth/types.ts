import { z } from "zod";

// ── User Schema ─────────────────────────────────────────────────────────────

export const userSchema = z.object({
  id: z.uuid(),
  email: z.email(),
  username: z.string().nullable(),
  full_name: z.string().nullable(),
  is_active: z.boolean(),
  is_superuser: z.boolean(),
});

export type User = z.infer<typeof userSchema>;

// ── Auth Result (Tagged Union) ──────────────────────────────────────────────

export type AuthResult =
  | { status: "authenticated"; user: User }
  | { status: "unauthenticated" }
  | { status: "needs_setup" }
  | { status: "gateway_unavailable" }
  | { status: "config_error"; message: string };

// ── Auth Error Parsing ──────────────────────────────────────────────────────

export function parseAuthError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "An unknown error occurred";
}
