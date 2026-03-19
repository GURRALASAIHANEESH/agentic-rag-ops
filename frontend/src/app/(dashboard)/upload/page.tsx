"use client";

import React from "react";
import { DocumentUploader } from "@/components/DocumentUploader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useWorkspaceDocuments } from "@/hooks/useWorkspace";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { FileText, Clock } from "lucide-react";
import clsx from "clsx";

export default function UploadPage() {
    const { active } = useWorkspace();
    const { documents, isLoading, refresh } = useWorkspaceDocuments();

    if (!active) {
        return (
            <div className="flex items-center justify-center h-full">
                <p className="text-sm text-text-muted">Select a workspace to upload documents.</p>
            </div>
        );
    }

    return (
        <div className="max-w-3xl mx-auto p-6 flex flex-col gap-6">

            {/* Upload card */}
            <Card>
                <CardHeader
                    title="Upload Documents"
                    description={`Ingest files into workspace "${active.name}"`}
                />
                <div className="pt-4">
                    <DocumentUploader
                        workspaceId={active.id}
                        onUploadComplete={refresh}
                    />
                </div>
            </Card>

            {/* Ingested documents list */}
            <Card>
                <CardHeader
                    title="Ingested Documents"
                    description={`${documents.length} document${documents.length !== 1 ? "s" : ""} in this workspace`}
                />
                <div className="pt-3 flex flex-col gap-2">
                    {isLoading && (
                        <>
                            <SkeletonCard />
                            <SkeletonCard />
                        </>
                    )}

                    {!isLoading && documents.length === 0 && (
                        <p className="text-xs text-text-muted py-4 text-center">
                            No documents yet. Upload a file above.
                        </p>
                    )}

                    {!isLoading && documents.map((doc) => (
                        <div
                            key={doc.id}
                            className={clsx(
                                "flex items-center gap-3 px-3 py-2.5 rounded-md",
                                "border border-glass-border hover:bg-glass-hover",
                                "transition-colors duration-fast"
                            )}
                        >
                            <div className="h-8 w-8 rounded-md bg-danger/10 border border-danger/20 flex items-center justify-center shrink-0">
                                <FileText className="h-4 w-4 text-danger/70" aria-hidden="true" />
                            </div>

                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-text-primary truncate-1">
                                    {doc.filename}
                                </p>
                                <p className="text-2xs text-text-muted">
                                    {(doc.file_size_bytes / 1024).toFixed(1)} KB
                                    {doc.page_count ? ` · ${doc.page_count} pages` : ""}
                                </p>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                                <DocStatusBadge status={doc.status} />
                                <span className="text-2xs text-text-muted flex items-center gap-1 tabular-nums">
                                    <Clock className="h-3 w-3" aria-hidden="true" />
                                    {new Date(doc.created_at).toLocaleDateString()}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    );
}

function DocStatusBadge({ status }: { status: string }) {
    const map: Record<string, { variant: "success" | "warn" | "danger" | "accent" | "default"; label: string }> = {
        ready: { variant: "success", label: "Ready" },
        processing: { variant: "accent", label: "Processing" },
        pending: { variant: "default", label: "Pending" },
        failed: { variant: "danger", label: "Failed" },
    };
    const { variant, label } = map[status] ?? { variant: "default", label: status };
    return <Badge variant={variant} size="sm" dot>{label}</Badge>;
}
