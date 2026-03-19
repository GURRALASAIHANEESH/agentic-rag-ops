"use client";

import React from "react";
import Link from "next/link";
import {
    MessageSquare, Upload, Clock, TrendingUp,
    ArrowRight, FileText, Zap,
} from "lucide-react";
import clsx from "clsx";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useQueryHistory, useWorkspaceDocuments } from "@/hooks/useWorkspace";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
    const { user } = useAuth();
    const { active } = useWorkspace();
    const { history, isLoading: historyLoading } = useQueryHistory(5);
    const { documents, isLoading: docsLoading } = useWorkspaceDocuments();

    const greeting = getGreeting();

    return (
        <div className="max-w-4xl mx-auto p-6 flex flex-col gap-6">

            {/* ── Welcome row ─────────────────────────────────────────────────── */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-xl font-semibold text-text-primary">
                        {greeting}, {user?.full_name?.split(" ")[0] ?? "there"}
                    </h2>
                    <p className="text-sm text-text-muted mt-0.5">
                        {active
                            ? `Working in workspace "${active.name}"`
                            : "Select a workspace to get started"}
                    </p>
                </div>
                <Button variant="primary" size="sm" asChild>
                    <Link href="/dashboard/query">
                        New query
                        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                    </Link>
                </Button>
            </div>

            {/* ── Quick actions ────────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <QuickActionCard
                    href="/dashboard/query"
                    icon={<MessageSquare className="h-5 w-5 text-accent" aria-hidden="true" />}
                    title="Query documents"
                    description="Ask questions with streaming AI responses and source citations."
                    accent
                />
                <QuickActionCard
                    href="/dashboard/upload"
                    icon={<Upload className="h-5 w-5 text-text-muted" aria-hidden="true" />}
                    title="Upload documents"
                    description="Ingest PDFs and text files into your active workspace."
                />
            </div>

            {/* ── Stats row ────────────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <StatCard
                    label="Documents"
                    value={docsLoading ? "—" : String(documents.length)}
                    icon={<FileText className="h-4 w-4 text-text-muted" aria-hidden="true" />}
                />
                <StatCard
                    label="Queries"
                    value={historyLoading ? "—" : String(history.length)}
                    icon={<MessageSquare className="h-4 w-4 text-text-muted" aria-hidden="true" />}
                />
                <StatCard
                    label="Avg latency"
                    value={
                        history.length > 0
                            ? `${Math.round(
                                history
                                    .filter((h) => h.latency_ms)
                                    .reduce((a, b) => a + (b.latency_ms ?? 0), 0) /
                                history.filter((h) => h.latency_ms).length
                            )}ms`
                            : "—"
                    }
                    icon={<Zap className="h-4 w-4 text-text-muted" aria-hidden="true" />}
                />
            </div>

            {/* ── Recent queries ───────────────────────────────────────────────── */}
            <Card>
                <CardHeader
                    title="Recent queries"
                    description="Last 5 queries in this workspace"
                    action={
                        <Button variant="ghost" size="xs" asChild>
                            <Link href="/dashboard/query">View all</Link>
                        </Button>
                    }
                />
                <div className="pt-3 flex flex-col gap-2">
                    {historyLoading && (
                        <>
                            <SkeletonCard />
                            <SkeletonCard />
                        </>
                    )}

                    {!historyLoading && history.length === 0 && (
                        <EmptyHistoryState />
                    )}

                    {!historyLoading &&
                        history.map((item) => (
                            <RecentQueryRow key={item.id} item={item} />
                        ))}
                </div>
            </Card>

            {/* ── Recent documents ─────────────────────────────────────────────── */}
            <Card>
                <CardHeader
                    title="Recent documents"
                    description={`${documents.length} document${documents.length !== 1 ? "s" : ""} ingested`}
                    action={
                        <Button variant="ghost" size="xs" asChild>
                            <Link href="/dashboard/upload">Manage</Link>
                        </Button>
                    }
                />
                <div className="pt-3 flex flex-col gap-2">
                    {docsLoading && <SkeletonCard />}

                    {!docsLoading && documents.length === 0 && (
                        <p className="text-xs text-text-muted py-3 text-center">
                            No documents yet.{" "}
                            <Link href="/dashboard/upload" className="text-accent hover:underline">
                                Upload one
                            </Link>
                        </p>
                    )}

                    {!docsLoading &&
                        documents.slice(0, 4).map((doc) => (
                            <div
                                key={doc.id}
                                className={clsx(
                                    "flex items-center gap-3 px-3 py-2 rounded-md",
                                    "border border-glass-border hover:bg-glass-hover",
                                    "transition-colors duration-fast"
                                )}
                            >
                                <FileText className="h-4 w-4 text-danger/60 shrink-0" aria-hidden="true" />
                                <span className="flex-1 text-xs text-text-primary truncate-1">
                                    {doc.filename}
                                </span>
                                <Badge
                                    variant={doc.status === "ready" ? "success" : doc.status === "failed" ? "danger" : "default"}
                                    size="sm"
                                    dot
                                >
                                    {doc.status}
                                </Badge>
                            </div>
                        ))}
                </div>
            </Card>
        </div>
    );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function QuickActionCard({
    href,
    icon,
    title,
    description,
    accent = false,
}: {
    href: string;
    icon: React.ReactNode;
    title: string;
    description: string;
    accent?: boolean;
}) {
    return (
        <Link
            href={href}
            className={clsx(
                "flex flex-col gap-3 p-4 rounded-lg border",
                "transition-all duration-fast group",
                accent
                    ? "border-accent/30 bg-accent/5 hover:border-accent/50 hover:bg-accent/8"
                    : "border-glass-border bg-bg-2 hover:border-accent/20 hover:bg-glass-hover"
            )}
        >
            <div className={clsx(
                "h-9 w-9 rounded-lg flex items-center justify-center",
                accent ? "bg-accent/15" : "bg-glass border border-glass-border"
            )}>
                {icon}
            </div>
            <div>
                <p className="text-sm font-medium text-text-primary group-hover:text-accent transition-colors duration-fast">
                    {title}
                </p>
                <p className="text-xs text-text-muted mt-0.5 leading-relaxed">
                    {description}
                </p>
            </div>
        </Link>
    );
}

function StatCard({
    label,
    value,
    icon,
}: {
    label: string;
    value: string;
    icon: React.ReactNode;
}) {
    return (
        <div className="flex flex-col gap-2 p-3 rounded-lg border border-glass-border bg-bg-2">
            <div className="flex items-center justify-between">
                {icon}
                <TrendingUp className="h-3 w-3 text-text-muted/40" aria-hidden="true" />
            </div>
            <div>
                <p className="text-lg font-semibold text-text-primary tabular-nums">
                    {value}
                </p>
                <p className="text-2xs text-text-muted">{label}</p>
            </div>
        </div>
    );
}

function RecentQueryRow({ item }: { item: ReturnType<typeof useQueryHistory>["history"][number] }) {
    return (
        <Link
            href="/dashboard/query"
            className={clsx(
                "flex items-start gap-3 px-3 py-2.5 rounded-md",
                "border border-glass-border hover:bg-glass-hover hover:border-accent/20",
                "transition-all duration-fast group"
            )}
            aria-label={`Query: ${item.query}`}
        >
            <MessageSquare
                className="h-3.5 w-3.5 text-text-muted mt-0.5 shrink-0 group-hover:text-accent transition-colors"
                aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
                <p className="text-xs text-text-primary truncate-1">{item.query}</p>
                {item.answer_preview && (
                    <p className="text-2xs text-text-muted truncate-1 mt-0.5">
                        {item.answer_preview}
                    </p>
                )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
                {item.critic_score !== null && (
                    <ConfidenceBadge score={item.critic_score} size="sm" />
                )}
                {item.latency_ms && (
                    <span className="text-2xs text-text-muted tabular-nums flex items-center gap-1">
                        <Clock className="h-3 w-3" aria-hidden="true" />
                        {item.latency_ms}ms
                    </span>
                )}
            </div>
        </Link>
    );
}

function EmptyHistoryState() {
    return (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
            <MessageSquare className="h-6 w-6 text-text-muted/40" aria-hidden="true" />
            <p className="text-xs text-text-muted">No queries yet.</p>
            <Button variant="secondary" size="sm" asChild>
                <Link href="/dashboard/query">Ask your first question</Link>
            </Button>
        </div>
    );
}

// ── Greeting helper ───────────────────────────────────────────────────────────

function getGreeting(): string {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
}
