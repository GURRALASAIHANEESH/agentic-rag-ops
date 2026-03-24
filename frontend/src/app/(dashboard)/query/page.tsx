"use client";

import React, { useState } from "react";
import dynamic from "next/dynamic";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import clsx from "clsx";
import { QueryConsole } from "@/components/QueryConsole";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { Citation, CriticReport as CriticReportType } from "@/types";

// ── Lazy-load heavy right-panel components ────────────────────────────────────

const ProvenanceViewer = dynamic(
    () => import("@/components/ProvenanceViewer").then((m) => ({ default: m.ProvenanceViewer })),
    { loading: () => <SkeletonCard />, ssr: false }
);

const CriticReport = dynamic(
    () => import("@/components/CriticReport").then((m) => ({ default: m.CriticReport })),
    { loading: () => <SkeletonCard />, ssr: false }
);

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QueryPage() {
    const { active } = useWorkspace();
    const [rightPanelOpen, setRightPanelOpen] = useState(true);
    const [activeCitations, setActiveCitations] = useState<Citation[]>([]);
    const [queryLogId, setQueryLogId] = useState<string | null>(null);
    const [criticData, setCriticData] = useState<CriticReportType | null>(null);

    // suppress lint — these are wired to QueryConsole callbacks below
    void setQueryLogId;
    void setCriticData;

    if (!active) {
        return <NoWorkspaceBanner />;
    }

    return (
        <div className="flex h-full min-h-0">

            {/* ── Left: Query console ──────────────────────────────────────────── */}
            <div
                className={clsx(
                    "flex flex-col min-w-0 flex-1 p-4",
                    rightPanelOpen && "border-r border-glass-border"
                )}
            >
                <div className="flex items-center justify-end mb-3 shrink-0">
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setRightPanelOpen((v) => !v)}
                        aria-label={rightPanelOpen ? "Collapse evidence panel" : "Expand evidence panel"}
                    >
                        {rightPanelOpen
                            ? <PanelRightClose className="h-4 w-4" aria-hidden="true" />
                            : <PanelRightOpen className="h-4 w-4" aria-hidden="true" />
                        }
                    </Button>
                </div>

                <QueryConsole
                    workspaceId={active.id}
                    onCitationSelect={(c) => {
                        setActiveCitations((prev) =>
                            prev.find((x) => x.chunk_id === c.chunk_id) ? prev : [...prev, c]
                        );
                    }}
                />
            </div>

            {/* ── Right: Provenance + Critic ───────────────────────────────────── */}
            {rightPanelOpen && (
                <aside
                    className={clsx(
                        "flex flex-col shrink-0 h-full",
                        "w-panel overflow-y-auto scrollbar-hide",
                        "animate-slide-in-right bg-bg-2/40"
                    )}
                    aria-label="Evidence panel"
                >
                    <div className="flex flex-col gap-4 p-4">
                        <section aria-labelledby="provenance-heading">
                            <h2
                                id="provenance-heading"
                                className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3"
                            >
                                Sources
                            </h2>
                            <ProvenanceViewer
                                citations={activeCitations}
                                queryLogId={queryLogId}
                            />
                        </section>

                        {criticData && (
                            <section aria-labelledby="critic-heading">
                                <h2
                                    id="critic-heading"
                                    className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3"
                                >
                                    Verification
                                </h2>
                                <CriticReport report={criticData} />
                            </section>
                        )}
                    </div>
                </aside>
            )}
        </div>
    );
}

function NoWorkspaceBanner() {
    return (
        <div className="flex flex-col items-center justify-center h-full gap-3 p-8 text-center">
            <p className="text-sm font-medium text-text-primary">No workspace selected</p>
            <p className="text-xs text-text-muted max-w-xs">
                Select or create a workspace from the sidebar to start querying.
            </p>
            <Button variant="primary" size="sm" asChild>
                <a href="/workspace" className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors">Go to workspaces</a>
            </Button>
        </div>
    );
}
