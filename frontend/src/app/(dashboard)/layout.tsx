"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
    MessageSquare, Upload, FolderOpen, LayoutDashboard, LogOut,
} from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

// ── Navigation items ──────────────────────────────────────────────────────────

const NAV_ITEMS = [
    { href: "/",         icon: LayoutDashboard, label: "Dashboard" },
    { href: "/query",    icon: MessageSquare,   label: "Query" },
    { href: "/upload",   icon: Upload,          label: "Upload" },
    { href: "/workspace",icon: FolderOpen,      label: "Workspaces" },
] as const;

// ── Layout ────────────────────────────────────────────────────────────────────

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const { user, logout, isLoading } = useAuth();
    const { active } = useWorkspace();
    const router = useRouter();
    const pathname = usePathname();

    // Client-side auth guard — backend validates JWT on every API call
    React.useEffect(() => {
        if (!isLoading && !user) {
            router.replace("/login");
        }
    }, [user, isLoading, router]);

    // Show spinner while auth state resolves
    if (isLoading || !user) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-bg-1">
                <div
                    role="status"
                    aria-label="Loading"
                    className="h-6 w-6 rounded-full border-2 border-accent border-t-transparent animate-spin"
                />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-bg-1 flex">

            {/* ── Sidebar ──────────────────────────────────────────────────── */}
            <aside
                className="w-56 shrink-0 border-r border-glass-border bg-bg-2 flex flex-col"
                aria-label="Main navigation"
            >
                {/* Logo */}
                <div className="p-4 border-b border-glass-border">
                    <span className="text-sm font-bold text-gradient">RAG Ops</span>
                    <p className="text-2xs text-text-muted mt-0.5">Agentic Retrieval Platform</p>
                </div>

                {/* Active workspace pill */}
                {active && (
                    <div className="px-4 py-2 border-b border-glass-border">
                        <p className="text-2xs text-text-muted uppercase tracking-wide mb-1">Workspace</p>
                        <p className="text-xs text-accent font-medium truncate">{active.name}</p>
                    </div>
                )}

                {/* Nav links */}
                <nav className="flex-1 p-3 flex flex-col gap-0.5">
                    {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
                        const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
                        return (
                            <Link
                                key={href}
                                href={href}
                                className={clsx(
                                    "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm",
                                    "transition-colors duration-fast",
                                    isActive
                                        ? "bg-accent/10 text-accent border border-accent/20"
                                        : "text-text-muted hover:text-text-primary hover:bg-glass-hover"
                                )}
                                aria-current={isActive ? "page" : undefined}
                            >
                                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                                {label}
                            </Link>
                        );
                    })}
                </nav>

                {/* User section */}
                <div className="p-3 border-t border-glass-border">
                    <div className="flex items-center gap-2 px-3 py-1 mb-1">
                        <div className="h-6 w-6 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
                            <span className="text-2xs text-accent font-semibold">
                                {user.full_name?.[0]?.toUpperCase() ?? "U"}
                            </span>
                        </div>
                        <div className="min-w-0">
                            <p className="text-xs font-medium text-text-primary truncate">{user.full_name}</p>
                            <p className="text-2xs text-text-muted truncate">{user.email}</p>
                        </div>
                    </div>
                    <button
                        onClick={logout}
                        className={clsx(
                            "flex items-center gap-2 w-full px-3 py-1.5 rounded-md",
                            "text-xs text-text-muted hover:text-danger hover:bg-danger/5",
                            "transition-colors duration-fast"
                        )}
                        aria-label="Sign out"
                    >
                        <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                        Sign out
                    </button>
                </div>
            </aside>

            {/* ── Main content ─────────────────────────────────────────────── */}
            <main className="flex-1 min-w-0 overflow-auto">
                {children}
            </main>
        </div>
    );
}
