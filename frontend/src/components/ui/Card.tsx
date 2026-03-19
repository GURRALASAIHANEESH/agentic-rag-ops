import * as React from "react";
import clsx from "clsx";

// ── Card ──────────────────────────────────────────────────────────────────────

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
    glass?: boolean;
    noPadding?: boolean;
}

function Card({ className, glass = false, noPadding = false, children, ...props }: CardProps) {
    return (
        <div
            className={clsx(
                "rounded-lg border border-glass-border",
                glass
                    ? "glass-panel shadow-panel"
                    : "bg-bg-2 shadow",
                !noPadding && "p-4",
                className
            )}
            {...props}
        >
            {children}
        </div>
    );
}

// ── CardHeader ────────────────────────────────────────────────────────────────

interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
    title: string;
    description?: string;
    action?: React.ReactNode;
}

function CardHeader({ title, description, action, className, ...props }: CardHeaderProps) {
    return (
        <div
            className={clsx(
                "flex items-start justify-between gap-4 pb-3 border-b border-glass-border",
                className
            )}
            {...props}
        >
            <div className="flex flex-col gap-0.5 min-w-0">
                <h3 className="text-sm font-semibold text-text-primary truncate-1">
                    {title}
                </h3>
                {description && (
                    <p className="text-xs text-text-muted truncate-2">{description}</p>
                )}
            </div>
            {action && <div className="shrink-0">{action}</div>}
        </div>
    );
}

// ── CardSection ───────────────────────────────────────────────────────────────

function CardSection({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return (
        <div className={clsx("pt-3", className)} {...props}>
            {children}
        </div>
    );
}

// ── CardFooter ────────────────────────────────────────────────────────────────

function CardFooter({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return (
        <div
            className={clsx(
                "flex items-center justify-between gap-2 pt-3 mt-3",
                "border-t border-glass-border",
                className
            )}
            {...props}
        >
            {children}
        </div>
    );
}

export { Card, CardHeader, CardSection, CardFooter };
