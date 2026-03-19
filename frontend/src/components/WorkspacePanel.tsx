"use client";

import React, { useState, useCallback } from "react";
import {
    Plus, ChevronDown, Check,
    FolderOpen, Settings, Users,
} from "lucide-react";
import clsx from "clsx";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { formatApiError } from "@/lib/api";
import type { Workspace, WorkspaceRole } from "@/types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface WorkspacePanelProps {
    className?: string;
    collapsed?: boolean;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function WorkspacePanel({
    className,
    collapsed = false,
}: WorkspacePanelProps) {
    const {
        workspaces,
        active,
        switchWorkspace,
        createWorkspace,
    } = useWorkspace();

    const [showDropdown, setShowDropdown] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);

    const handleSwitch = useCallback(
        (ws: Workspace) => {
            switchWorkspace(ws);
            setShowDropdown(false);
        },
        [switchWorkspace]
    );

    const handleCreateNew = useCallback(() => {
        setShowDropdown(false);
        setShowCreateModal(true);
    }, []);

    const handleCloseDropdown = useCallback(() => {
        setShowDropdown(false);
    }, []);

    const handleCloseModal = useCallback(() => {
        setShowCreateModal(false);
    }, []);

    if (collapsed) {
        return (
            <div className={clsx("flex flex-col items-center gap-2 py-2", className)}>
                <button
                    onClick={() => setShowDropdown((v) => !v)}
                    className={clsx(
                        "h-8 w-8 rounded-md flex items-center justify-center",
                        "bg-glass border border-glass-border",
                        "hover:border-accent/30 hover:bg-glass-hover",
                        "transition-all duration-fast",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                    )}
                    aria-label={`Active workspace: ${active?.name ?? "None"}. Click to switch.`}
                    aria-expanded={showDropdown}
                    aria-haspopup="listbox"
                >
                    <FolderOpen className="h-4 w-4 text-text-muted" aria-hidden="true" />
                </button>
            </div>
        );
    }

    return (
        <div className={clsx("flex flex-col gap-1", className)}>
            {/* Workspace selector */}
            <div className="relative">
                <button
                    onClick={() => setShowDropdown((v) => !v)}
                    className={clsx(
                        "w-full flex items-center gap-2 px-3 py-2 rounded-lg",
                        "bg-glass border border-glass-border",
                        "hover:border-accent/30 hover:bg-glass-hover",
                        "transition-all duration-fast",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                    )}
                    aria-label="Switch workspace"
                    aria-expanded={showDropdown}
                    aria-haspopup="listbox"
                >
                    <FolderOpen className="h-4 w-4 text-text-muted shrink-0" aria-hidden="true" />
                    <span className="flex-1 text-sm text-text-primary truncate-1 text-left">
                        {active?.name ?? "Select workspace"}
                    </span>
                    <ChevronDown
                        className={clsx(
                            "h-3.5 w-3.5 text-text-muted shrink-0",
                            "transition-transform duration-fast",
                            showDropdown && "rotate-180"
                        )}
                        aria-hidden="true"
                    />
                </button>

                {/* Dropdown */}
                {showDropdown && (
                    <WorkspaceDropdown
                        workspaces={workspaces}
                        activeId={active?.id ?? null}
                        onSelect={handleSwitch}
                        onCreateNew={handleCreateNew}
                        onClose={handleCloseDropdown}
                    />
                )}
            </div>

            {/* Active workspace details */}
            {active && (
                <WorkspaceDetails workspace={active} />
            )}

            {/* Create workspace modal */}
            <CreateWorkspaceModal
                open={showCreateModal}
                onClose={handleCloseModal}
                onCreate={createWorkspace}
            />
        </div>
    );
}

// ── Workspace dropdown ────────────────────────────────────────────────────────

interface WorkspaceDropdownProps {
    workspaces: Workspace[];
    activeId: string | null;
    onSelect: (ws: Workspace) => void;
    onCreateNew: () => void;
    onClose: () => void;
}

function WorkspaceDropdown({
    workspaces,
    activeId,
    onSelect,
    onCreateNew,
    onClose,
}: WorkspaceDropdownProps) {
    // Close on outside click
    const ref = React.useRef<HTMLDivElement>(null);
    React.useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                onClose();
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [onClose]);

    return (
        <div
            ref={ref}
            role="listbox"
            aria-label="Workspace list"
            className={clsx(
                "absolute top-full left-0 right-0 z-overlay mt-1",
                "glass-panel shadow-lg rounded-lg overflow-hidden",
                "animate-fade-in"
            )}
        >
            <div className="py-1 max-h-[240px] overflow-y-auto scrollbar-hide">
                {workspaces.length === 0 && (
                    <p className="px-3 py-2 text-xs text-text-muted">
                        No workspaces yet.
                    </p>
                )}

                {workspaces.map((ws) => (
                    <button
                        key={ws.id}
                        role="option"
                        aria-selected={ws.id === activeId}
                        onClick={() => onSelect(ws)}
                        className={clsx(
                            "w-full flex items-center gap-2.5 px-3 py-2 text-left",
                            "text-sm transition-colors duration-fast",
                            ws.id === activeId
                                ? "text-accent bg-accent/8"
                                : "text-text-secondary hover:text-text-primary hover:bg-glass-hover"
                        )}
                    >
                        <FolderOpen className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        <span className="flex-1 truncate-1">{ws.name}</span>
                        {ws.id === activeId && (
                            <Check className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
                        )}
                    </button>
                ))}
            </div>

            <div className="border-t border-glass-border py-1">
                <button
                    onClick={onCreateNew}
                    className={clsx(
                        "w-full flex items-center gap-2.5 px-3 py-2 text-left",
                        "text-sm text-text-muted hover:text-text-primary hover:bg-glass-hover",
                        "transition-colors duration-fast"
                    )}
                >
                    <Plus className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    New workspace
                </button>
            </div>
        </div>
    );
}

// ── Workspace details card ────────────────────────────────────────────────────

function WorkspaceDetails({ workspace }: { workspace: Workspace }) {
    return (
        <Card noPadding className="overflow-hidden animate-fade-in">
            <div className="px-3 py-2.5 flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-text-primary truncate-1">
                        {workspace.name}
                    </span>
                    <RoleBadge role="owner" />
                </div>

                {workspace.description && (
                    <p className="text-2xs text-text-muted truncate-2">
                        {workspace.description}
                    </p>
                )}

                <p className="text-2xs text-text-muted tabular-nums">
                    Created {new Date(workspace.created_at).toLocaleDateString()}
                </p>
            </div>

            <div className="border-t border-glass-border flex">
                <button
                    className={clsx(
                        "flex-1 flex items-center justify-center gap-1.5 py-2",
                        "text-2xs text-text-muted hover:text-text-secondary hover:bg-glass-hover",
                        "transition-colors duration-fast"
                    )}
                    aria-label="Workspace settings"
                >
                    <Settings className="h-3 w-3" aria-hidden="true" />
                    Settings
                </button>
                <span className="w-px bg-glass-border" aria-hidden="true" />
                <button
                    className={clsx(
                        "flex-1 flex items-center justify-center gap-1.5 py-2",
                        "text-2xs text-text-muted hover:text-text-secondary hover:bg-glass-hover",
                        "transition-colors duration-fast"
                    )}
                    aria-label="Workspace members"
                >
                    <Users className="h-3 w-3" aria-hidden="true" />
                    Members
                </button>
            </div>
        </Card>
    );
}

// ── Role badge ────────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: WorkspaceRole }) {
    const map: Record<WorkspaceRole, { variant: "accent" | "default" | "muted"; label: string }> = {
        owner: { variant: "accent", label: "Owner" },
        editor: { variant: "default", label: "Editor" },
        viewer: { variant: "muted", label: "Viewer" },
    };
    const { variant, label } = map[role];
    return <Badge variant={variant} size="sm">{label}</Badge>;
}

// ── Create workspace modal ────────────────────────────────────────────────────

interface CreateWorkspaceModalProps {
    open: boolean;
    onClose: () => void;
    onCreate: (name: string, description?: string) => Promise<Workspace>;
}

function CreateWorkspaceModal({
    open,
    onClose,
    onCreate,
}: CreateWorkspaceModalProps) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const { success } = useToast();

    const handleSubmit = useCallback(
        async (e: React.FormEvent) => {
            e.preventDefault();
            if (!name.trim()) {
                setError("Workspace name is required.");
                return;
            }
            setLoading(true);
            setError(null);
            try {
                await onCreate(name.trim(), description.trim() || undefined);
                success("Workspace created", `"${name}" is ready to use.`);
                setName("");
                setDescription("");
                onClose();
            } catch (err) {
                setError(formatApiError(err));
            } finally {
                setLoading(false);
            }
        },
        [name, description, onCreate, success, onClose]
    );

    const handleOpenChange = useCallback((open: boolean) => {
        if (!open) {
            setName("");
            setDescription("");
            setError(null);
            onClose();
        }
    }, [onClose]);

    return (
        <Dialog.Root open={open} onOpenChange={handleOpenChange}>
            <Dialog.Portal>
                <Dialog.Overlay
                    className={clsx(
                        "fixed inset-0 z-modal bg-bg-1/80 backdrop-blur-sm",
                        "data-[state=open]:animate-fade-in",
                        "data-[state=closed]:animate-fade-out"
                    )}
                />
                <Dialog.Content
                    className={clsx(
                        "fixed left-1/2 top-1/2 z-modal",
                        "-translate-x-1/2 -translate-y-1/2",
                        "w-[min(420px,calc(100vw-2rem))]",
                        "glass-panel shadow-lg rounded-xl p-5",
                        "data-[state=open]:animate-fade-in",
                        "data-[state=closed]:animate-fade-out",
                        "focus:outline-none"
                    )}
                >
                    <Dialog.Title className="text-base font-semibold text-text-primary mb-1">
                        New workspace
                    </Dialog.Title>
                    <Dialog.Description className="text-xs text-text-muted mb-4">
                        Workspaces keep documents and query history isolated.
                    </Dialog.Description>

                    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
                        <Input
                            label="Name"
                            placeholder="e.g. Research Papers"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            error={error ?? undefined}
                            autoFocus
                            maxLength={80}
                            aria-required="true"
                        />
                        <Input
                            label="Description (optional)"
                            placeholder="What is this workspace for?"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            maxLength={200}
                        />

                        <div className="flex items-center justify-end gap-2 pt-1">
                            <Dialog.Close asChild>
                                <Button variant="secondary" size="sm" type="button">
                                    Cancel
                                </Button>
                            </Dialog.Close>
                            <Button
                                variant="primary"
                                size="sm"
                                type="submit"
                                loading={loading}
                                disabled={!name.trim()}
                            >
                                Create workspace
                            </Button>
                        </div>
                    </form>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
