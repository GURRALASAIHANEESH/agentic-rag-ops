"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/contexts/AuthContext";
import { formatApiError } from "@/lib/api";

export default function LoginPage() {
    const router = useRouter();
    const { login } = useAuth();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPw, setShowPw] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.trim() || !password) return;

        setLoading(true);
        setError(null);
        try {
            await login(email.trim(), password);
            router.replace("/query");
        } catch (err) {
            setError(formatApiError(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <AuthShell
            title="Welcome back"
            subtitle="Sign in to your RAG Ops account"
        >
            <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
                <Input
                    type="email"
                    label="Email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    autoFocus
                    required
                    aria-required="true"
                />
                <Input
                    type={showPw ? "text" : "password"}
                    label="Password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                    aria-required="true"
                    rightSlot={
                        <button
                            type="button"
                            onClick={() => setShowPw((v) => !v)}
                            className="text-text-muted hover:text-text-secondary transition-colors p-1"
                            aria-label={showPw ? "Hide password" : "Show password"}
                        >
                            {showPw
                                ? <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
                                : <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                            }
                        </button>
                    }
                />

                {error && (
                    <p className="text-xs text-danger" role="alert">{error}</p>
                )}

                <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    loading={loading}
                    className="mt-1 w-full"
                >
                    Sign in
                </Button>
            </form>

            <p className="text-xs text-text-muted text-center mt-4">
                Don&apos;t have an account?{" "}
                <Link
                    href="/signup"
                    className="text-accent hover:underline focus-visible:outline-none focus-visible:underline"
                >
                    Create one
                </Link>
            </p>
        </AuthShell>
    );
}

// ── Auth shell ────────────────────────────────────────────────────────────────

function AuthShell({
    title,
    subtitle,
    children,
}: {
    title: string;
    subtitle: string;
    children: React.ReactNode;
}) {
    return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-bg-1">
            {/* Background grid */}
            <div
                className="fixed inset-0 pointer-events-none"
                aria-hidden="true"
                style={{
                    backgroundImage:
                        "radial-gradient(rgba(94,234,212,0.04) 1px, transparent 1px)",
                    backgroundSize: "32px 32px",
                }}
            />

            <div className="w-full max-w-sm relative z-raised">
                {/* Logo */}
                <div className="text-center mb-8">
                    <span className="text-2xl font-bold text-gradient">RAG Ops</span>
                    <p className="text-xs text-text-muted mt-1">
                        Agentic Retrieval Platform
                    </p>
                </div>

                <div className="glass-panel p-6 rounded-xl shadow-panel">
                    <div className="mb-5">
                        <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
                        <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>
                    </div>
                    {children}
                </div>
            </div>
        </div>
    );
}
