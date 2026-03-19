import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import clsx from "clsx";

const badgeVariants = cva(
    "inline-flex items-center gap-1 font-medium rounded shrink-0 tabular-nums",
    {
        variants: {
            variant: {
                default: "bg-glass border border-glass-border text-text-secondary",
                accent: "bg-accent/10 border border-accent/20 text-accent",
                success: "bg-success/10 border border-success/20 text-success",
                warn: "bg-warn/10 border border-warn/20 text-warn",
                danger: "bg-danger/10 border border-danger/20 text-danger",
                partial: "bg-amber-500/10 border border-amber-500/20 text-amber-400",
                muted: "bg-transparent text-text-muted",
            },
            size: {
                sm: "text-2xs px-1.5 py-0.5",
                md: "text-xs px-2 py-0.5",
                lg: "text-sm px-2.5 py-1",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "sm",
        },
    }
);

export interface BadgeProps
    extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
    dot?: boolean;
    children?: React.ReactNode;
    className?: string;
}

function Badge({ className, variant, size, dot = false, children, ...props }: BadgeProps) {
    return (
        <span
            className={clsx(badgeVariants({ variant, size }), className)}
            {...props}
        >
            {dot && (
                <span
                    className={clsx(
                        "inline-block h-1.5 w-1.5 rounded-full shrink-0",
                        variant === "success" && "bg-success",
                        variant === "warn" && "bg-warn",
                        variant === "danger" && "bg-danger",
                        variant === "accent" && "bg-accent",
                        variant === "partial" && "bg-amber-400",
                        (!variant || variant === "default" || variant === "muted") && "bg-text-muted"
                    )}
                    aria-hidden="true"
                />
            )}
            {children}
        </span>
    );
}

// ── Confidence badge — renders a numeric score with appropriate color ──────────

interface ConfidenceBadgeProps {
    score: number;   // 0.0 – 1.0
    size?: "sm" | "md" | "lg";
    className?: string;
}

function ConfidenceBadge({ score, size = "sm", className }: ConfidenceBadgeProps) {
    const pct = Math.round(score * 100);
    const variant =
        pct >= 75 ? "success" :
            pct >= 45 ? "warn" :
                "danger";

    return (
        <Badge variant={variant} size={size} dot className={className}>
            {pct}%
        </Badge>
    );
}

// ── Claim status badge ─────────────────────────────────────────────────────────

interface ClaimBadgeProps {
    status: "verified" | "partial" | "unverified";
    size?: "sm" | "md" | "lg";
    className?: string;
}

function ClaimBadge({ status, size = "sm", className }: ClaimBadgeProps) {
    const map = {
        verified: { variant: "success" as const, label: "Verified" },
        partial: { variant: "partial" as const, label: "Partial" },
        unverified: { variant: "danger" as const, label: "Unverified" },
    };
    const { variant, label } = map[status];
    return (
        <Badge variant={variant} size={size} dot className={className}>
            {label}
        </Badge>
    );
}

export { Badge, badgeVariants, ConfidenceBadge, ClaimBadge };
