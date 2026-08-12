"use client";

/**
 * Backend auth state (client-side session management).
 *
 * The FastAPI backend issues a signed Bearer token; it is stored in
 * localStorage and attached to every API call by the client in lib/api.ts.
 * A per-request check is intentionally skipped here (the backend is the
 * source of truth) — this provider only keeps the UI in sync and handles
 * redirects on 401s.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

const TOKEN_KEY = "backend_token";
const USER_KEY = "backend_user";

export interface AuthUser {
  username: string;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  register: (username: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function readUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Lazy initialisers read the session synchronously so the first render
  // already reflects the persisted state (no setState-in-effect).
  const [token, setToken] = useState<string | null>(() => readToken());
  const [user, setUser] = useState<AuthUser | null>(() => readUser());
  const [ready, setReady] = useState<boolean>(() => !readToken());
  const router = useRouter();

  useEffect(() => {
    const t = window.localStorage.getItem(TOKEN_KEY);
    if (!t) return;
    api
      .me()
      .then((me) => setUser(me.user))
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(USER_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await api.login(username, password);
      window.localStorage.setItem(TOKEN_KEY, res.access_token);
      window.localStorage.setItem(USER_KEY, JSON.stringify(res.user));
      setToken(res.access_token);
      setUser(res.user);
      return res.user;
    },
    []
  );

  const register = useCallback(
    async (username: string, password: string) => {
      await api.register(username, password);
      return login(username, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    // Session reset: tell the backend to drop the loaded (transient) data so
    // the next login starts fresh. Fire-and-forget — local logout proceeds
    // even if the backend is unreachable.
    api.logout().catch(() => undefined);
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value = useMemo(
    () => ({ user, token, ready, login, register, logout }),
    [user, token, ready, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
