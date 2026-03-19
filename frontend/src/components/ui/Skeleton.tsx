import * as React from "react";
import clsx from "clsx";

// ── Base skeleton ─────────────────────────────────────────────────────────────

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
    width?: string;
    height?: string;
}

function Skeleton({ className, width, height, style, ...props }: SkeletonProps) {
    return (
        <div
            className={clsx("skeleton", className)}
            style={{ width, height, ...style }}
            aria-hidden="true"
            {...props}
        />
    );
}

// ── Skeleton text block ───────────────────────────────────────────────────────

function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
    return (
        <div className={clsx("flex flex-col gap-2", className)} aria-hidden="true">
            {Array.from({ length: lines }).map((_, i) => (
                <Skeleton
                    key={i}
                    className="h-3 rounded"
                    style={{
                        // Vary widths so it looks like real text
                        width: i === lines - 1 ? "65%" : i % 2 === 0 ? "100%" : "88%",
                    }}
                />
            ))}
        </div>
    );
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard({ className }: { className?: string }) {
    return (
        <div
            className={clsx(
                "rounded-lg border border-glass-border bg-bg-2 p-4 flex flex-col gap-3",
                className
            )}
            aria-hidden="true"
        >
            <div className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded-md shrink-0" />
                <div className="flex flex-col gap-1.5 flex-1">
                    <Skeleton className="h-3 w-2/3 rounded" />
                    <Skeleton className="h-2.5 w-1/3 rounded" />
                </div>
            </div>
            <SkeletonText lines={2} />
        </div>
    );
}

// ── Skeleton query result ─────────────────────────────────────────────────────

function SkeletonQueryResult({ className }: { className?: string }) {
    return (
        <div
            className={clsx("flex flex-col gap-4 p-4", className)}
            aria-hidden="true"
            aria-label="Loading response..."
        >
            <SkeletonText lines={4} />
            <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded" />
                <Skeleton className="h-5 w-20 rounded" />
                <Skeleton className="h-5 w-14 rounded" />
            </div>
        </div>
    );
}

export { Skeleton, SkeletonText, SkeletonCard, SkeletonQueryResult };
