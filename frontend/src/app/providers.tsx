"use client";

import React, { useEffect } from "react";
import { ToastProvider } from "@/components/ui/Toast";
import { AuthProvider } from "@/contexts/AuthContext";
import { WorkspaceProvider } from "@/contexts/WorkspaceContext";
import { refreshIfNeeded } from "@/lib/auth";

// ── Root provider tree ────────────────────────────────────────────────────────
// Order matters: AuthProvider must wrap WorkspaceProvider.

export function Providers({ children }: { children: React.ReactNode }) {
    // Proactively refresh JWT on mount — prevents stale token on page reload
    useEffect(() => {
        void refreshIfNeeded();
    }, []);

    return (
        <AuthProvider>
            <WorkspaceProvider>
                <ToastProvider>
                    {children}
                </ToastProvider>
            </WorkspaceProvider>
        </AuthProvider>
    );
}
