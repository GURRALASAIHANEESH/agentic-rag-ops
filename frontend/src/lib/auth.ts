// ─────────────────────────────────────────────────────────────
// Auth helpers — JWT storage, session management, guards.
// All storage uses localStorage (client-side only).
// Never store tokens in cookies without httpOnly flag.
// ─────────────────────────────────────────────────────────────

import type { User, TokenResponse } from "@/types";
import { authApi } from "@/lib/api";

const KEYS = {
    ACCESS_TOKEN: "access_token",
    REFRESH_TOKEN: "refresh_token",
    USER: "ragops_user",
    WORKSPACE_ID: "ragops_workspace_id",
} as const;

// ── Token storage ─────────────────────────────────────────────────────────────

export function storeTokens(tokens: TokenResponse): void {
    if (typeof window === "undefined") return;
    localStorage.setItem(KEYS.ACCESS_TOKEN, tokens.access_token);
    localStorage.setItem(KEYS.REFRESH_TOKEN, tokens.refresh_token);
    // Set a lightweight session cookie as a server-readable presence signal
    // for Next.js middleware (Edge runtime can't access localStorage).
    document.cookie = "ragops_session=1; path=/; SameSite=Lax";
}

export function getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(KEYS.ACCESS_TOKEN);
}

export function getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(KEYS.REFRESH_TOKEN);
}

export function clearTokens(): void {
    if (typeof window === "undefined") return;
    Object.values(KEYS).forEach((key) => localStorage.removeItem(key));
    // Clear the session presence cookie so middleware knows user is logged out
    document.cookie = "ragops_session=; path=/; max-age=0; SameSite=Lax";
}

// ── User session ──────────────────────────────────────────────────────────────

export function storeUser(user: User): void {
    if (typeof window === "undefined") return;
    localStorage.setItem(KEYS.USER, JSON.stringify(user));
}

export function getStoredUser(): User | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem(KEYS.USER);
        return raw ? (JSON.parse(raw) as User) : null;
    } catch {
        return null;
    }
}

// ── Workspace persistence ─────────────────────────────────────────────────────

export function storeWorkspaceId(id: string): void {
    if (typeof window === "undefined") return;
    localStorage.setItem(KEYS.WORKSPACE_ID, id);
}

export function getStoredWorkspaceId(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(KEYS.WORKSPACE_ID);
}

// ── Auth state ────────────────────────────────────────────────────────────────

export function isAuthenticated(): boolean {
    return Boolean(getAccessToken());
}

// ── JWT decode (client-side, no verification) ─────────────────────────────────
// Used only to extract expiry for proactive refresh — not for security checks.

export function decodeTokenPayload(token: string): Record<string, unknown> | null {
    try {
        const base64 = token.split(".")[1];
        const decoded = atob(base64.replace(/-/g, "+").replace(/_/g, "/"));
        return JSON.parse(decoded) as Record<string, unknown>;
    } catch {
        return null;
    }
}

export function isTokenExpired(token: string): boolean {
    const payload = decodeTokenPayload(token);
    if (!payload || typeof payload.exp !== "number") return true;
    // Consider token expired 60 seconds before actual expiry to avoid edge cases
    return Date.now() / 1000 > payload.exp - 60;
}

// ── Login / logout ────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<User> {
    const { data: tokens } = await authApi.login(email, password);
    storeTokens(tokens);

    const { data: user } = await authApi.me();
    storeUser(user);
    return user;
}

export async function signup(
    email: string,
    fullName: string,
    password: string
): Promise<User> {
    const { data } = await authApi.signup(email, fullName, password);
    storeTokens(data.tokens);
    storeUser(data.user);
    return data.user;
}

export function logout(): void {
    clearTokens();
    window.location.href = "/login";
}

// ── Proactive token refresh ───────────────────────────────────────────────────
// Call this once on app mount to ensure token is fresh.

export async function refreshIfNeeded(): Promise<void> {
    const access = getAccessToken();
    const refresh = getRefreshToken();

    if (!access || !refresh) return;
    if (!isTokenExpired(access)) return;

    try {
        const { data } = await authApi.refresh(refresh);
        storeTokens(data);
    } catch {
        // Refresh failed — clear session and redirect
        clearTokens();
        window.location.href = "/login";
    }
}
