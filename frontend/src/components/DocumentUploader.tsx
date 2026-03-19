"use client";

import React, {
    useCallback,
    useRef,
    useState,
    useId,
} from "react";
import {
    UploadCloud, FileText, X, File,
} from "lucide-react";
import clsx from "clsx";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { documentsApi, formatApiError } from "@/lib/api";
import { useDocumentStatus } from "@/hooks/useWorkspace";
import type { DocumentStatus } from "@/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const ACCEPTED_TYPES: Record<string, string> = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
};

const MAX_SIZE_MB = 25;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

// ── Types ─────────────────────────────────────────────────────────────────────

interface FileEntry {
    id: string;
    file: File;
    status: "pending" | "uploading" | "ingesting" | "ready" | "failed";
    uploadProgress: number;
    documentId: string | null;
    errorMessage: string | null;
    chunksCreated: number | null;
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface DocumentUploaderProps {
    workspaceId: string;
    onUploadComplete?: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DocumentUploader({
    workspaceId,
    onUploadComplete,
}: DocumentUploaderProps) {
    const inputId = useId();
    const inputRef = useRef<HTMLInputElement>(null);
    const dropRef = useRef<HTMLDivElement>(null);

    const [files, setFiles] = useState<FileEntry[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const { success, error: toastError } = useToast();

    // ── Validation ──────────────────────────────────────────────────────────
    const validateFile = useCallback((file: File): string | null => {
        if (!Object.keys(ACCEPTED_TYPES).includes(file.type)) {
            return `File type "${file.type}" is not supported. Upload PDF or TXT files.`;
        }
        if (file.size > MAX_SIZE_BYTES) {
            return `File exceeds the ${MAX_SIZE_MB}MB size limit.`;
        }
        if (file.size === 0) {
            return "File is empty.";
        }
        return null;
    }, []);

    // ── Add files ────────────────────────────────────────────────────────────
    const addFiles = useCallback((incoming: FileList | File[]) => {
        const list = Array.from(incoming);
        const entries: FileEntry[] = list.map((file) => {
            const validationError = validateFile(file);
            return {
                id: crypto.randomUUID(),
                file,
                status: validationError ? "failed" : "pending",
                uploadProgress: 0,
                documentId: null,
                errorMessage: validationError,
                chunksCreated: null,
            };
        });
        setFiles((prev) => [...prev, ...entries]);
    }, [validateFile]);

    // ── Upload single file ───────────────────────────────────────────────────
    const uploadFile = useCallback(
        async (entryId: string) => {
            setFiles((prev) =>
                prev.map((f) =>
                    f.id === entryId ? { ...f, status: "uploading", uploadProgress: 0 } : f
                )
            );

            const entry = files.find((f) => f.id === entryId);
            if (!entry || entry.status === "failed") return;

            try {
                const { data: doc } = await documentsApi.uploadWithProgress(
                    workspaceId,
                    entry.file,
                    (pct) => {
                        setFiles((prev) =>
                            prev.map((f) =>
                                f.id === entryId ? { ...f, uploadProgress: pct } : f
                            )
                        );
                    }
                );

                setFiles((prev) =>
                    prev.map((f) =>
                        f.id === entryId
                            ? { ...f, status: "ingesting", documentId: doc.id, uploadProgress: 100 }
                            : f
                    )
                );
            } catch (err) {
                const msg = formatApiError(err);
                setFiles((prev) =>
                    prev.map((f) =>
                        f.id === entryId
                            ? { ...f, status: "failed", errorMessage: msg }
                            : f
                    )
                );
                toastError("Upload failed", msg);
            }
        },
        [files, workspaceId, toastError]
    );

    // ── Upload all pending ───────────────────────────────────────────────────
    const uploadAll = useCallback(async () => {
        const pending = files.filter((f) => f.status === "pending");
        await Promise.all(pending.map((f) => uploadFile(f.id)));
    }, [files, uploadFile]);

    const removeFile = useCallback((id: string) => {
        setFiles((prev) => prev.filter((f) => f.id !== id));
    }, []);

    // ── Drag and drop ────────────────────────────────────────────────────────
    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (dropRef.current && !dropRef.current.contains(e.relatedTarget as Node)) {
            setIsDragging(false);
        }
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragging(false);
            if (e.dataTransfer.files.length > 0) {
                addFiles(e.dataTransfer.files);
            }
        },
        [addFiles]
    );

    const hasPending = files.some((f) => f.status === "pending");
    const hasFiles = files.length > 0;

    const markFileReady = useCallback((id: string, name: string) => {
        setFiles((prev) => prev.map(f => (f.id === id ? { ...f, status: "ready" } : f)));
        success("Document ready", `"${name}" has been ingested.`);
        onUploadComplete?.();
    }, [success, onUploadComplete]);

    return (
        <div className="flex flex-col gap-4">

            {/* Drop zone */}
            <div
                ref={dropRef}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                role="region"
                aria-label="Document upload area. Drag and drop files here."
                className={clsx(
                    "relative flex flex-col items-center justify-center gap-3",
                    "rounded-xl border-2 border-dashed p-8",
                    "transition-all duration-fast cursor-pointer",
                    isDragging
                        ? "border-accent/60 bg-accent/5 scale-[1.01]"
                        : "border-glass-border hover:border-accent/30 hover:bg-glass-hover"
                )}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
                tabIndex={0}
            >
                <input
                    ref={inputRef}
                    id={inputId}
                    type="file"
                    multiple
                    accept={Object.values(ACCEPTED_TYPES).join(",")}
                    className="sr-only"
                    onChange={(e) => e.target.files && addFiles(e.target.files)}
                    aria-label="File upload input"
                />

                <div
                    className={clsx(
                        "p-3 rounded-full transition-colors duration-fast",
                        isDragging ? "bg-accent/15" : "bg-glass"
                    )}
                >
                    <UploadCloud
                        className={clsx(
                            "h-6 w-6 transition-colors duration-fast",
                            isDragging ? "text-accent" : "text-text-muted"
                        )}
                        aria-hidden="true"
                    />
                </div>

                <div className="text-center">
                    <p className="text-sm font-medium text-text-primary">
                        {isDragging ? "Drop files here" : "Drag files or click to upload"}
                    </p>
                    <p className="text-xs text-text-muted mt-1">
                        PDF or TXT &middot; Max {MAX_SIZE_MB}MB per file
                    </p>
                </div>
            </div>

            {/* File list */}
            {hasFiles && (
                <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                        <p className="text-xs text-text-muted">
                            {files.length} file{files.length !== 1 ? "s" : ""}
                        </p>
                        {hasPending && (
                            <Button
                                variant="primary"
                                size="sm"
                                onClick={uploadAll}
                                aria-label="Upload all pending files"
                            >
                                Upload all
                            </Button>
                        )}
                    </div>

                    <ul className="flex flex-col gap-2" aria-label="File upload list">
                        {files.map((entry) => (
                            <FileRow
                                key={entry.id}
                                entry={entry}
                                onRemove={() => removeFile(entry.id)}
                                onRetry={() => uploadFile(entry.id)}
                                onIngestComplete={markFileReady}
                            />
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

// ── File row ──────────────────────────────────────────────────────────────────

interface FileRowProps {
    entry: FileEntry;
    onRemove: () => void;
    onRetry: () => void;
    onIngestComplete: (id: string, name: string) => void;
}

function FileRow({ entry, onRemove, onRetry, onIngestComplete }: FileRowProps) {
    const { status: ingestStatus, chunksCreated } = useDocumentStatus(
        entry.status === "ingesting" ? entry.documentId : null
    );

    const effectiveStatus: DocumentStatus | "uploading" | "ingesting" | "pending" =
        entry.status === "ingesting" && ingestStatus
            ? (ingestStatus as DocumentStatus)
            : entry.status;

    // Notify parent when ingestion completes
    React.useEffect(() => {
        if (ingestStatus === "ready") {
            onIngestComplete(entry.id, entry.file.name);
        }
    }, [ingestStatus, onIngestComplete, entry.id, entry.file.name]);

    const sizeKb = (entry.file.size / 1024).toFixed(1);

    return (
        <li
            className={clsx(
                "flex flex-col gap-2 p-3 rounded-lg border",
                "transition-colors duration-fast",
                effectiveStatus === "ready" && "border-success/30 bg-success/5",
                effectiveStatus === "failed" && "border-danger/30 bg-danger/5",
                effectiveStatus === "pending" && "border-glass-border bg-bg-2",
                (effectiveStatus === "uploading" || effectiveStatus === "processing" || effectiveStatus === "ingesting")
                && "border-accent/30 bg-accent/5"
            )}
        >
            {/* Top row */}
            <div className="flex items-center gap-2.5">
                <FileIcon filename={entry.file.name} />

                <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-text-primary truncate-1">
                        {entry.file.name}
                    </p>
                    <p className="text-2xs text-text-muted">{sizeKb} KB</p>
                </div>

                <StatusBadge
                    status={effectiveStatus}
                    chunksCreated={chunksCreated ?? entry.chunksCreated}
                />

                <div className="flex items-center gap-1 shrink-0">
                    {effectiveStatus === "failed" && (
                        <Button
                            variant="ghost"
                            size="xs"
                            onClick={onRetry}
                            aria-label="Retry upload"
                        >
                            Retry
                        </Button>
                    )}
                    {(effectiveStatus === "pending" || effectiveStatus === "failed") && (
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={onRemove}
                            aria-label={`Remove ${entry.file.name}`}
                        >
                            <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                    )}
                </div>
            </div>

            {/* Upload progress bar */}
            {effectiveStatus === "uploading" && (
                <div className="flex flex-col gap-1">
                    <div
                        className="h-1 rounded-full bg-glass-border overflow-hidden"
                        role="progressbar"
                        aria-valuenow={entry.uploadProgress}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Uploading: ${entry.uploadProgress}%`}
                    >
                        <div
                            className="h-full bg-accent rounded-full transition-all duration-medium"
                            style={{ width: `${entry.uploadProgress}%` }}
                        />
                    </div>
                    <p className="text-2xs text-text-muted tabular-nums">
                        Uploading... {entry.uploadProgress}%
                    </p>
                </div>
            )}

            {/* Ingestion progress */}
            {(effectiveStatus === "processing" || effectiveStatus === "ingesting") && (
                <div className="flex items-center gap-2">
                    <div className="flex-1 h-1 rounded-full bg-glass-border overflow-hidden">
                        <div className="h-full bg-accent/60 rounded-full animate-pulse w-full" />
                    </div>
                    <p className="text-2xs text-text-muted shrink-0">Chunking...</p>
                </div>
            )}

            {/* Error message */}
            {effectiveStatus === "failed" && entry.errorMessage && (
                <p className="text-xs text-danger" role="alert">
                    {entry.errorMessage}
                </p>
            )}

            {/* Chunk count on success */}
            {effectiveStatus === "ready" && chunksCreated !== null && (
                <p className="text-2xs text-success">
                    {chunksCreated} chunk{chunksCreated !== 1 ? "s" : ""} indexed
                </p>
            )}
        </li>
    );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({
    status,
    chunksCreated,
}: {
    status: string;
    chunksCreated: number | null;
}) {
    if (status === "ready") {
        return (
            <Badge variant="success" size="sm" dot>
                Ready{chunksCreated !== null ? ` · ${chunksCreated}` : ""}
            </Badge>
        );
    }
    if (status === "failed") {
        return <Badge variant="danger" size="sm" dot>Failed</Badge>;
    }
    if (status === "uploading") {
        return <Badge variant="accent" size="sm" dot>Uploading</Badge>;
    }
    if (status === "processing" || status === "ingesting") {
        return <Badge variant="accent" size="sm" dot>Processing</Badge>;
    }
    return <Badge variant="default" size="sm">Pending</Badge>;
}

// ── File icon ─────────────────────────────────────────────────────────────────

function FileIcon({ filename }: { filename: string }) {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (ext === "pdf") {
        return (
            <div className="h-8 w-8 rounded-md bg-danger/10 border border-danger/20 flex items-center justify-center shrink-0">
                <FileText className="h-4 w-4 text-danger/70" aria-hidden="true" />
            </div>
        );
    }
    return (
        <div className="h-8 w-8 rounded-md bg-glass border border-glass-border flex items-center justify-center shrink-0">
            <File className="h-4 w-4 text-text-muted" aria-hidden="true" />
        </div>
    );
}
