"use client";

  import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useState,
  } from "react";

  import type { AuthResult, User } from "./types";

  // ── Context Types ───────────────────────────────────────────────────────────

  interface AuthContextValue {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    logout: () => void;
    refresh: () => Promise<void>;
    /** Fetch /me immediately (e.g. after login modal success). */
    syncAuth: () => Promise<void>;
  }

  const AuthContext = createContext<AuthContextValue | null>(null);

  // ── Visibility Change Throttle ──────────────────────────────────────────────

  const REFRESH_THROTTLE_MS = 60_000;

  // ── Provider ────────────────────────────────────────────────────────────────

  interface AuthProviderProps {
    initialUser: User | null;
    children: React.ReactNode;
  }

  export function AuthProvider({ initialUser, children }: AuthProviderProps) {
    const [user, setUser] = useState<User | null>(initialUser);
    const [isLoading, setIsLoading] = useState(false);
    const [lastRefresh, setLastRefresh] = useState(() => Date.now());

    const syncAuth = useCallback(async () => {
      setIsLoading(true);
      try {
        const response = await fetch("/api/v1/auth/me", {
          credentials: "include",
        });

        if (response.ok) {
          const data: AuthResult = await response.json();
          setUser(data.status === "authenticated" ? data.user : null);
        } else if (response.status === 401) {
          setUser(null);
        }
      } catch {
        // Silent fail — network errors don't clear user state
      } finally {
        setLastRefresh(Date.now());
        setIsLoading(false);
      }
    }, []);

    const refresh = useCallback(async () => {
      const now = Date.now();
      if (now - lastRefresh < REFRESH_THROTTLE_MS) return;
      await syncAuth();
    }, [lastRefresh, syncAuth]);

    const logout = useCallback(() => {
      setUser(null);
      fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
      }).catch(() => {});
    }, []);

    // Auto-refresh on visibility change
    useEffect(() => {
      function handleVisibilityChange() {
        if (document.visibilityState === "visible") {
          refresh();
        }
      }
  
      document.addEventListener("visibilitychange", handleVisibilityChange);
      return () =>
        document.removeEventListener("visibilitychange", handleVisibilityChange);
    }, [refresh]);

    return (
      <AuthContext.Provider
        value={{
          user,
          isAuthenticated: user !== null,
          isLoading,
          logout,
          refresh,
          syncAuth,
        }}
      >
        {children}
      </AuthContext.Provider>
    );
  }

  // ── Hook ────────────────────────────────────────────────────────────────────

  export function useAuth(): AuthContextValue {
    const context = useContext(AuthContext);
    if (!context) {
      throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
  }
