"use client";

import React from "react";
import { Plus, FolderOpen, Clock } from "lucide-react";
import clsx from "clsx";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { Workspace } from "@/types";

export default function WorkspacePage() {
    const { workspaces, active, switchWorkspace } = useWorkspace();

    return (
        <div className="max-w-3xl mx-auto p-6 flex flex-col gap-6">

            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-text-primary">Workspaces</h2>
                    <p className="text-xs text-text-muted mt-0.5">
                        {workspaces.length} workspace{workspaces.length !== 1 ? "s" : ""}
                    </p>
                </div>
                <Button
                    variant="primary"
                    size="sm"
                    leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
                    asChild
                >
                    <a href="#create">New workspace</a>
                </Button>
            </div>

            {/* Workspace grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {workspaces.map((ws) => (
                    <WorkspaceCard
                        key={ws.id}
                        workspace={ws}
                        isActive={ws.id === active?.id}
                        onSelect={() => switchWorkspace(ws)}
                    />
                ))}

                {workspaces.length === 0 && (
                    <div className="col-span-2 flex flex-col items-center gap-3 py-12 text-center">
                        <FolderOpen className="h-8 w-8 text-text-muted/40" aria-hidden="true" />
                        <p className="text-sm text-text-muted">No workspaces yet.</p>
                        <Button
                            variant="secondary"
                            size="sm"
                            asChild
                        >
                            <a href="#create">Create your first workspace</a>
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Workspace card ────────────────────────────────────────────────────────────

function WorkspaceCard({
    workspace,
    isActive,
    onSelect,
}: {
    workspace: Workspace;
    isActive: boolean;
    onSelect: () => void;
}) {
    return (
        <button
            onClick={onSelect}
            className={clsx(
                "flex flex-col gap-2 p-4 rounded-lg border text-left w-full",
                "transition-all duration-fast",
                isActive
                    ? "border-accent/40 bg-accent/5 shadow-glow"
                    : "border-glass-border bg-bg-2 hover:border-accent/30 hover:bg-glass-hover"
            )}
            aria-pressed={isActive}
            aria-label={`${workspace.name}${isActive ? " (active)" : ""}`}
        >
            <div className="flex items-center gap-2">
                <div className={clsx(
                    "h-7 w-7 rounded-md flex items-center justify-center shrink-0",
                    isActive ? "bg-accent/20 border border-accent/30" : "bg-glass border border-glass-border"
                )}>
                    <FolderOpen
                        className={clsx("h-3.5 w-3.5", isActive ? "text-accent" : "text-text-muted")}
                        aria-hidden="true"
                    />
                </div>
                <span className="flex-1 text-sm font-medium text-text-primary truncate-1">
                    {workspace.name}
                </span>
                {isActive && (
                    <Badge variant="accent" size="sm" dot>Active</Badge>
                )}
            </div>

            {workspace.description && (
                <p className="text-xs text-text-muted truncate-2 text-left">
                    {workspace.description}
                </p>
            )}

            <div className="flex items-center gap-1.5 text-2xs text-text-muted">
                <Clock className="h-3 w-3" aria-hidden="true" />
                <span>Created {new Date(workspace.created_at).toLocaleDateString()}</span>
            </div>
        </button>
    );
}
