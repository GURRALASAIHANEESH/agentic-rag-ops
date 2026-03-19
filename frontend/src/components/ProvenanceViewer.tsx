"use client";

import React, { useState, useCallback, useEffect, useRef } from "react";
import {
    FileText, Globe, Database, Copy,
    X, ChevronRight, Search,
} from "lucide-react";
import clsx from "clsx";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/Button";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { retrievalApi } from "@/lib/api";
import type { Citation, ProvenanceRecord } from "@/types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ProvenanceViewerProps {
    citations: Citation[];
    queryLogId: string | null;
    className?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProvenanceViewer({
    citations,
    queryLogId,
    className,
}: ProvenanceViewerProps) {
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
    const [provenance, setProvenance] = useState<ProvenanceRecord | null>(null);
    const [provenanceLoading, setProvenanceLoading] = useState(false);
    const { info } = useToast();

    // Sort citations by similarity descending
    const sorted = [...citations].sort((a, b) => b.similarity - a.similarity);

    const filtered = searchTerm.trim()
        ? sorted.filter(
            (c) =>
                c.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
                c.snippet.toLowerCase().includes(searchTerm.toLowerCase())
        )
        : sorted;

    // Load full provenance when queryLogId is available
    useEffect(() => {
        if (!queryLogId) return;
        setProvenanceLoading(true);
        retrievalApi
            .getProvenance(queryLogId)
            .then(({ data }) => setProvenance(data))
            .catch(() => setProvenance(null))
            .finally(() => setProvenanceLoading(false));
    }, [queryLogId]);

    const handleCopyMarkdown = useCallback(
        (c: Citation) => {
            const md = `[${c.filename}] — *"${c.snippet.slice(0, 80)}..."* (similarity: ${Math.round(c.similarity * 100)}%)`;
            void navigator.clipboard.writeText(md);
            info("Citation copied", "Markdown citation copied to clipboard.");
        },
        [info]
    );

    if (citations.length === 0) {
        return (
            <div className={clsx("flex flex-col items-center justify-center h-full min-h-[160px] gap-2", className)}>
                <Database className="h-8 w-8 text-text-muted/40" aria-hidden="true" />
                <p className="text-xs text-text-muted">No sources retrieved yet.</p>
                <p className="text-2xs text-text-muted/60">Submit a query to see source evidence.</p>
            </div>
        );
    }

    return (
        <div className={clsx("flex flex-col gap-3 h-full min-h-0", className)}>

            {/* Search */}
            <Input
                placeholder="Filter sources..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                leftIcon={<Search className="h-3.5 w-3.5" aria-hidden="true" />}
                aria-label="Filter sources"
            />

            {/* Citation list */}
            <ol
                className="flex flex-col gap-2 overflow-y-auto flex-1 min-h-0 scrollbar-hide"
                aria-label={`${filtered.length} sources`}
            >
                {filtered.map((citation, i) => (
                    <CitationCard
                        key={citation.chunk_id}
                        index={i}
                        citation={citation}
                        searchTerm={searchTerm}
                        onOpen={() => setSelectedCitation(citation)}
                        onCopy={() => handleCopyMarkdown(citation)}
                    />
                ))}
            </ol>

            {/* Audit trail */}
            {provenanceLoading && (
                <SkeletonCard className="shrink-0" />
            )}
            {provenance && !provenanceLoading && (
                <AuditTrail provenance={provenance} />
            )}

            {/* Source detail modal */}
            <SourceModal
                citation={selectedCitation}
                onClose={() => setSelectedCitation(null)}
                searchTerm={searchTerm}
                onCopy={handleCopyMarkdown}
            />
        </div>
    );
}

// ── Citation card ─────────────────────────────────────────────────────────────

interface CitationCardProps {
    index: number;
    citation: Citation;
    searchTerm: string;
    onOpen: () => void;
    onCopy: () => void;
}

function CitationCard({
    index,
    citation,
    searchTerm,
    onOpen,
    onCopy,
}: CitationCardProps) {
    return (
        <li>
            <Card
                noPadding
                className={clsx(
                    "group flex flex-col gap-0 overflow-hidden",
                    "hover:border-accent/30 transition-colors duration-fast"
                )}
            >
                {/* Header row */}
                <div className="flex items-center gap-2 px-3 py-2 border-b border-glass-border">
                    <SourceTypeIcon filename={citation.filename} />
                    <span
                        className="flex-1 text-xs font-medium text-text-primary truncate-1"
                        title={citation.filename}
                    >
                        {citation.filename}
                    </span>
                    <ConfidenceBadge score={citation.similarity} size="sm" />
                    <Badge variant="default" size="sm" className="tabular-nums">
                        #{index + 1}
                    </Badge>
                </div>

                {/* Snippet */}
                <div className="px-3 py-2">
                    <p className="text-xs text-text-secondary leading-relaxed truncate-3">
                        <HighlightedText text={citation.snippet} term={searchTerm} />
                    </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 px-2 pb-2">
                    <Button
                        variant="ghost"
                        size="xs"
                        onClick={onOpen}
                        leftIcon={<ChevronRight className="h-3 w-3" aria-hidden="true" />}
                        aria-label={`View full source: ${citation.filename}`}
                    >
                        View
                    </Button>
                    <Button
                        variant="ghost"
                        size="xs"
                        onClick={onCopy}
                        leftIcon={<Copy className="h-3 w-3" aria-hidden="true" />}
                        aria-label={`Copy citation for ${citation.filename}`}
                    >
                        Cite
                    </Button>
                </div>
            </Card>
        </li>
    );
}

// ── Highlighted text ──────────────────────────────────────────────────────────

function HighlightedText({ text, term }: { text: string; term: string }) {
    if (!term.trim()) return <>{text}</>;

    const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
    const parts = text.split(regex);

    return (
        <>
            {parts.map((part, i) =>
                regex.test(part) ? (
                    <mark
                        key={i}
                        className="bg-accent/20 text-accent rounded-sm px-0.5"
                    >
                        {part}
                    </mark>
                ) : (
                    <React.Fragment key={i}>{part}</React.Fragment>
                )
            )}
        </>
    );
}

// ── Source type icon ──────────────────────────────────────────────────────────

function SourceTypeIcon({ filename }: { filename: string }) {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (ext === "pdf") {
        return <FileText className="h-3.5 w-3.5 text-danger/70 shrink-0" aria-label="PDF document" />;
    }
    if (ext === "txt") {
        return <FileText className="h-3.5 w-3.5 text-text-muted shrink-0" aria-label="Text document" />;
    }
    if (filename.startsWith("http")) {
        return <Globe className="h-3.5 w-3.5 text-accent/70 shrink-0" aria-label="Web source" />;
    }
    return <Database className="h-3.5 w-3.5 text-text-muted shrink-0" aria-label="Database source" />;
}

// ── Source modal ──────────────────────────────────────────────────────────────

interface SourceModalProps {
    citation: Citation | null;
    onClose: () => void;
    searchTerm: string;
    onCopy: (c: Citation) => void;
}

function SourceModal({ citation, onClose, searchTerm, onCopy }: SourceModalProps) {
    const snippetRef = useRef<HTMLDivElement>(null);

    // Jump to snippet on open
    useEffect(() => {
        if (citation && snippetRef.current) {
            setTimeout(() => {
                snippetRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
            }, 100);
        }
    }, [citation]);

    return (
        <Dialog.Root open={Boolean(citation)} onOpenChange={(open) => !open && onClose()}>
            <Dialog.Portal>
                <Dialog.Overlay
                    className={clsx(
                        "fixed inset-0 z-modal bg-bg-1/80",
                        "backdrop-blur-sm",
                        "data-[state=open]:animate-fade-in",
                        "data-[state=closed]:animate-fade-out"
                    )}
                />
                <Dialog.Content
                    className={clsx(
                        "fixed left-1/2 top-1/2 z-modal",
                        "-translate-x-1/2 -translate-y-1/2",
                        "w-[min(640px,calc(100vw-2rem))]",
                        "max-h-[80vh] flex flex-col",
                        "glass-panel shadow-lg",
                        "data-[state=open]:animate-fade-in",
                        "data-[state=closed]:animate-fade-out",
                        "focus:outline-none"
                    )}
                    aria-label={citation ? `Source: ${citation.filename}` : "Source detail"}
                >
                    {citation && (
                        <>
                            {/* Modal header */}
                            <div className="flex items-center gap-3 px-5 py-4 border-b border-glass-border shrink-0">
                                <SourceTypeIcon filename={citation.filename} />
                                <Dialog.Title className="flex-1 text-sm font-semibold text-text-primary truncate-1">
                                    {citation.filename}
                                </Dialog.Title>
                                <ConfidenceBadge score={citation.similarity} size="md" />
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    onClick={() => onCopy(citation)}
                                    aria-label="Copy citation"
                                    title="Copy markdown citation"
                                >
                                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                                </Button>
                                <Dialog.Close asChild>
                                    <Button variant="ghost" size="icon-sm" aria-label="Close modal">
                                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                                    </Button>
                                </Dialog.Close>
                            </div>

                            {/* Modal body */}
                            <div className="flex-1 overflow-y-auto p-5 scrollbar-hide">
                                {/* Metadata row */}
                                <div className="flex flex-wrap items-center gap-2 mb-4">
                                    <Badge variant="default" size="md">
                                        Chunk {citation.chunk_index + 1}
                                    </Badge>
                                    <Badge variant="accent" size="md">
                                        {Math.round(citation.similarity * 100)}% match
                                    </Badge>
                                </div>

                                {/* Snippet with highlight */}
                                <div
                                    ref={snippetRef}
                                    className={clsx(
                                        "p-4 rounded-lg border-l-2 border-accent/40",
                                        "bg-accent/5 text-sm text-text-primary leading-relaxed"
                                    )}
                                    aria-label="Matched snippet"
                                >
                                    <HighlightedText text={citation.snippet} term={searchTerm} />
                                </div>

                                {/* Chunk metadata */}
                                <div className="mt-4 grid grid-cols-2 gap-3">
                                    <MetaItem label="Chunk ID" value={citation.chunk_id.slice(0, 12) + "..."} />
                                    <MetaItem label="Document ID" value={citation.document_id.slice(0, 12) + "..."} />
                                </div>
                            </div>

                            {/* Modal footer */}
                            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-glass-border shrink-0">
                                <Dialog.Close asChild>
                                    <Button variant="secondary" size="sm">
                                        Close
                                    </Button>
                                </Dialog.Close>
                            </div>
                        </>
                    )}
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}

function MetaItem({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex flex-col gap-0.5">
            <span className="text-2xs text-text-muted">{label}</span>
            <span className="text-xs text-text-secondary font-mono">{value}</span>
        </div>
    );
}

// ── Audit trail ───────────────────────────────────────────────────────────────

function AuditTrail({ provenance }: { provenance: ProvenanceRecord }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="shrink-0 border-t border-glass-border pt-3">
            <button
                onClick={() => setExpanded((v) => !v)}
                className={clsx(
                    "flex items-center gap-1.5 text-xs text-text-muted w-full",
                    "hover:text-text-secondary transition-colors duration-fast"
                )}
                aria-expanded={expanded}
            >
                <Database className="h-3.5 w-3.5" aria-hidden="true" />
                Audit trail
                <Badge variant="default" size="sm" className="ml-1">
                    {provenance.audit_trail.length}
                </Badge>
                <ChevronRight
                    className={clsx(
                        "h-3.5 w-3.5 ml-auto transition-transform duration-fast",
                        expanded && "rotate-90"
                    )}
                    aria-hidden="true"
                />
            </button>

            {expanded && (
                <ol className="mt-2 flex flex-col gap-1 animate-fade-in" aria-label="Audit events">
                    {provenance.audit_trail.map((event, i) => (
                        <li
                            key={i}
                            className="flex items-center gap-2 text-2xs text-text-muted px-2 py-1 rounded hover:bg-glass-hover"
                        >
                            <span
                                className="h-1.5 w-1.5 rounded-full bg-accent/50 shrink-0"
                                aria-hidden="true"
                            />
                            <span className="font-medium text-text-secondary">{event.event_type}</span>
                            <span className="ml-auto tabular-nums">
                                {new Date(event.timestamp).toLocaleTimeString()}
                            </span>
                        </li>
                    ))}
                </ol>
            )}
        </div>
    );
}
