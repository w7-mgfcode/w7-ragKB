import type { AuthUser, AuthSession } from "../types/database.types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

// ---------------------------------------------------------------------------
// In-memory token storage (never persisted to localStorage)
// ---------------------------------------------------------------------------

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

// ---------------------------------------------------------------------------
// AuthError
// ---------------------------------------------------------------------------

export class AuthError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown) {
    super(
      typeof data === "object" && data && "detail" in data
        ? String((data as Record<string, unknown>).detail)
        : `HTTP ${status}`
    );
    this.name = "AuthError";
    this.status = status;
    this.data = data;
  }
}

// ---------------------------------------------------------------------------
// Auth API calls
// ---------------------------------------------------------------------------

export async function login(
  email: string,
  password: string
): Promise<AuthSession> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new AuthError(res.status, await res.json());
  const data: AuthSession = await res.json();
  accessToken = data.access_token;
  return data;
}

export async function register(
  email: string,
  password: string
): Promise<AuthSession> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new AuthError(res.status, await res.json());
  const data: AuthSession = await res.json();
  accessToken = data.access_token;
  return data;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    credentials: "include",
  });
  accessToken = null;
}

export async function refreshToken(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return false;
  const data = await res.json();
  accessToken = data.access_token;
  return true;
}

export async function resetPassword(email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new AuthError(res.status, await res.json());
}

export async function confirmResetPassword(
  token: string,
  newPassword: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/reset-password/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) throw new AuthError(res.status, await res.json());
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    credentials: "include",
  });
  if (!res.ok) throw new AuthError(res.status, await res.json());
  return res.json();
}

// ---------------------------------------------------------------------------
// Authenticated fetch wrapper with auto-refresh on 401
// ---------------------------------------------------------------------------

export async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const buildHeaders = (): HeadersInit => ({
    ...options.headers,
    Authorization: `Bearer ${accessToken}`,
  });

  let res = await fetch(url, {
    ...options,
    headers: buildHeaders(),
    credentials: "include",
  });

  if (res.status === 401) {
    const refreshed = await refreshToken();
    if (!refreshed) throw new AuthError(401, { detail: "Session expired" });
    res = await fetch(url, {
      ...options,
      headers: buildHeaders(),
      credentials: "include",
    });
  }

  return res;
}
