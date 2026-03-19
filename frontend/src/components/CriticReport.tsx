"use client";

import React, { useState } from "react";
import { ChevronDown, RotateCcw, Flag, Search } from "lucide-react";
import clsx from "clsx";
import { Badge, ClaimBadge, ConfidenceBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import type { CriticReport as CriticReportType, ClaimVerification } from "@/types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface CriticReportProps {
    report: CriticReportType;
    onRerunRetrieval?: () => void;
    onFlagReview?: (claim: ClaimVerification) => void;
    className?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CriticReport({
    report,
    onRerunRetrieval,
    onFlagReview,
    className,
}: CriticReportProps) {
    const [expandedClaim, setExpandedClaim] = useState<number | null>(null);

    const toggleClaim = (i: number) =>
        setExpandedClaim((prev) => (prev === i ? null : i));

    const total = report.claims.length;

    return (
        <Card className={clsx("flex flex-col gap-0 overflow-hidden", className)} noPadding>
            <CardHeader
                title="Critic Verification"
                description={`${total} claim${total !== 1 ? "s" : ""} analyzed`}
                action={
                    <div className="flex items-center gap-1.5">
                        <ConfidenceBadge score={report.overall_score} size="md" />
                        {onRerunRetrieval && (
                            <Button
                                variant="ghost"
                                size="icon-sm"
                                onClick={onRerunRetrieval}
                                aria-label="Re-run retrieval"
                                title="Re-run retrieval"
                            >
                                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                        )}
                    </div>
                }
                className="px-4 pt-4 pb-3"
            />

            {/* Score summary bar */}
            <ScoreSummary report={report} />

            {/* Claims list */}
            <ol
                className="flex flex-col divide-y divide-glass-border overflow-y-auto max-h-[420px] scrollbar-hide"
                aria-label="Claim verification list"
            >
                {report.claims.map((claim, i) => (
                    <ClaimRow
                        key={i}
                        index={i}
                        claim={claim}
                        isExpanded={expandedClaim === i}
                        onToggle={() => toggleClaim(i)}
                        onFlag={onFlagReview ? () => onFlagReview(claim) : undefined}
                    />
                ))}
            </ol>

            {total === 0 && (
                <p className="px-4 py-6 text-xs text-text-muted text-center">
                    No claims were analyzed.
                </p>
            )}
        </Card>
    );
}

// ── Score summary ─────────────────────────────────────────────────────────────

function ScoreSummary({ report }: { report: CriticReportType }) {
    const total = report.claims.length || 1;
    const verifiedPct = (report.verified_count / total) * 100;
    const partialPct = (report.partial_count / total) * 100;
    const unverifiedPct = (report.unverified_count / total) * 100;

    return (
        <div className="px-4 py-3 border-b border-glass-border flex flex-col gap-2">
            {/* Stacked progress bar */}
            <div
                className="flex h-1.5 rounded-full overflow-hidden bg-glass-border"
                role="img"
                aria-label={`${Math.round(verifiedPct)}% verified, ${Math.round(partialPct)}% partial, ${Math.round(unverifiedPct)}% unverified`}
            >
                <span
                    className="bg-success transition-all duration-slow"
                    style={{ width: `${verifiedPct}%` }}
                />
                <span
                    className="bg-warn transition-all duration-slow"
                    style={{ width: `${partialPct}%` }}
                />
                <span
                    className="bg-danger transition-all duration-slow"
                    style={{ width: `${unverifiedPct}%` }}
                />
            </div>

            {/* Legend */}
            <div className="flex items-center gap-3 text-2xs text-text-muted">
                <LegendItem color="bg-success" label="Verified" count={report.verified_count} />
                <LegendItem color="bg-warn" label="Partial" count={report.partial_count} />
                <LegendItem color="bg-danger" label="Unverified" count={report.unverified_count} />
            </div>
        </div>
    );
}

function LegendItem({
    color,
    label,
    count,
}: {
    color: string;
    label: string;
    count: number;
}) {
    return (
        <div className="flex items-center gap-1">
            <span className={clsx("h-2 w-2 rounded-full", color)} aria-hidden="true" />
            <span>{count} {label}</span>
        </div>
    );
}

// ── Claim row ─────────────────────────────────────────────────────────────────

interface ClaimRowProps {
    index: number;
    claim: ClaimVerification;
    isExpanded: boolean;
    onToggle: () => void;
    onFlag?: () => void;
}

function ClaimRow({ index, claim, isExpanded, onToggle, onFlag }: ClaimRowProps) {
    return (
        <li>
            <button
                onClick={onToggle}
                className={clsx(
                    "w-full flex items-start gap-2.5 px-4 py-3 text-left",
                    "hover:bg-glass-hover transition-colors duration-fast",
                    "focus-visible:outline-none focus-visible:bg-glass-hover"
                )}
                aria-expanded={isExpanded}
                aria-label={`Claim ${index + 1}: ${claim.claim}. Status: ${claim.status}`}
            >
                {/* Status strip */}
                <span
                    className={clsx(
                        "mt-0.5 shrink-0 w-0.5 self-stretch rounded-full",
                        claim.status === "verified" && "bg-success",
                        claim.status === "partial" && "bg-warn",
                        claim.status === "unverified" && "bg-danger"
                    )}
                    aria-hidden="true"
                />

                <div className="flex flex-col gap-1 flex-1 min-w-0">
                    <p className="text-xs text-text-primary leading-relaxed">
                        {claim.claim}
                    </p>

                    <div className="flex items-center gap-2">
                        <ClaimBadge status={claim.status} />
                        <ConfidenceBadge score={claim.confidence} />
                        {claim.supporting_chunk_ids.length > 0 && (
                            <Badge variant="default" size="sm">
                                {claim.supporting_chunk_ids.length} source{claim.supporting_chunk_ids.length !== 1 ? "s" : ""}
                            </Badge>
                        )}
                    </div>
                </div>

                <ChevronDown
                    className={clsx(
                        "h-3.5 w-3.5 text-text-muted mt-0.5 shrink-0",
                        "transition-transform duration-fast",
                        isExpanded && "rotate-180"
                    )}
                    aria-hidden="true"
                />
            </button>

            {/* Expanded detail */}
            {isExpanded && (
                <ClaimDetail claim={claim} onFlag={onFlag} />
            )}
        </li>
    );
}

// ── Claim detail (expanded) ───────────────────────────────────────────────────

function ClaimDetail({
    claim,
    onFlag,
}: {
    claim: ClaimVerification;
    onFlag?: () => void;
}) {
    return (
        <div
            className="px-4 pb-3 pt-1 border-t border-glass-border/50 bg-glass/50 animate-fade-in"
            role="region"
            aria-label="Claim detail"
        >
            {/* Confidence meter */}
            <div className="flex items-center gap-2 mb-3">
                <span className="text-2xs text-text-muted w-16">Confidence</span>
                <div
                    className="flex-1 h-1 bg-glass-border rounded-full overflow-hidden"
                    role="progressbar"
                    aria-valuenow={Math.round(claim.confidence * 100)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                >
                    <div
                        className={clsx(
                            "h-full rounded-full transition-all duration-slow",
                            claim.status === "verified" && "bg-success",
                            claim.status === "partial" && "bg-warn",
                            claim.status === "unverified" && "bg-danger"
                        )}
                        style={{ width: `${claim.confidence * 100}%` }}
                    />
                </div>
                <span className="text-2xs text-text-muted tabular-nums w-8 text-right">
                    {Math.round(claim.confidence * 100)}%
                </span>
            </div>

            {/* Supporting sources */}
            {claim.supporting_chunk_ids.length > 0 && (
                <div className="mb-3">
                    <p className="text-2xs text-text-muted mb-1.5">Supporting chunks</p>
                    <div className="flex flex-wrap gap-1">
                        {claim.supporting_chunk_ids.map((id) => (
                            <Badge key={id} variant="accent" size="sm">
                                {id.slice(0, 8)}&hellip;
                            </Badge>
                        ))}
                    </div>
                </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2">
                <Button
                    variant="ghost"
                    size="xs"
                    leftIcon={<Search className="h-3 w-3" aria-hidden="true" />}
                    aria-label="Inspect claim sources"
                >
                    Inspect
                </Button>
                {onFlag && (
                    <Button
                        variant="ghost"
                        size="xs"
                        leftIcon={<Flag className="h-3 w-3" aria-hidden="true" />}
                        onClick={onFlag}
                        aria-label="Flag claim for review"
                    >
                        Flag
                    </Button>
                )}
            </div>
        </div>
    );
}
