import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ── Route definitions ─────────────────────────────────────────────────────────

// Auth pages — redirect away if already logged in
const AUTH_ONLY_PATHS = new Set(["/login", "/signup"]);

// ── Middleware ────────────────────────────────────────────────────────────────
// IMPORTANT: Edge runtime cannot access localStorage. Tokens live there.
//
// Strategy: on login/signup success, the client sets a lightweight
// non-httpOnly cookie "ragops_session=1" as a server-readable signal.
// Middleware reads this cookie for presence checks only.
// Real security is enforced by FastAPI JWT validation on every API call.
//
// For protected routes WITHOUT the cookie, we allow through and let
// the client-side AuthContext handle the redirect — this prevents false
// logouts on hard refresh before the cookie propagates.

export function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Pass through Next.js internals and static files unconditionally
    if (
        pathname.startsWith("/_next") ||
        pathname.startsWith("/api") ||
        pathname.startsWith("/static") ||
        pathname.includes(".")
    ) {
        return NextResponse.next();
    }

    const sessionCookie = request.cookies.get("ragops_session")?.value;
    const isLoggedIn = Boolean(sessionCookie);

    // Redirect logged-in users away from login/signup
    if (isLoggedIn && AUTH_ONLY_PATHS.has(pathname)) {
        return NextResponse.redirect(new URL("/query", request.url));
    }

    // For protected routes: allow through — client AuthContext handles redirect.
    // Avoiding server-side hard-redirects prevents infinite loops when the
    // session cookie hasn't propagated yet (e.g. immediately after login).

    // Attach security headers to all responses
    const response = NextResponse.next();

    response.headers.set("X-Content-Type-Options", "nosniff");
    response.headers.set("X-Frame-Options", "DENY");
    response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

    return response;
}

export const config = {
    // Run middleware on all routes except static files
    matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
