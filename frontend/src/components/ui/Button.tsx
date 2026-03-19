"use client";

import * as React from "react";
import { Slot, Slottable } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import clsx from "clsx";

const buttonVariants = cva(
    // Base styles applied to every button
    [
        "inline-flex items-center justify-center gap-2",
        "font-medium text-sm rounded-md",
        "transition-all duration-fast",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-1 focus-visible:ring-offset-bg-1",
        "disabled:pointer-events-none disabled:opacity-40",
        "select-none shrink-0",
    ],
    {
        variants: {
            variant: {
                primary: [
                    "bg-accent text-bg-1 font-semibold",
                    "hover:bg-accent-hover",
                    "active:scale-[0.98]",
                    "shadow-sm",
                ],
                secondary: [
                    "bg-glass border border-glass-border text-text-primary",
                    "hover:bg-glass-hover hover:border-border-strong",
                    "active:scale-[0.98]",
                ],
                ghost: [
                    "text-text-secondary",
                    "hover:bg-glass-hover hover:text-text-primary",
                    "active:scale-[0.98]",
                ],
                danger: [
                    "bg-danger/10 border border-danger/30 text-danger",
                    "hover:bg-danger/20 hover:border-danger/50",
                    "active:scale-[0.98]",
                ],
                outline: [
                    "border border-glass-border text-text-secondary",
                    "hover:border-border-strong hover:text-text-primary hover:bg-glass",
                    "active:scale-[0.98]",
                ],
            },
            size: {
                xs: "h-6 px-2 text-xs gap-1.5 rounded",
                sm: "h-7 px-2.5 text-xs gap-1.5",
                md: "h-8 px-3 text-sm",
                lg: "h-9 px-4 text-sm",
                xl: "h-10 px-5 text-base",
                icon: "h-8 w-8 p-0",
                "icon-sm": "h-7 w-7 p-0",
                "icon-lg": "h-9 w-9 p-0",
            },
        },
        defaultVariants: {
            variant: "secondary",
            size: "md",
        },
    }
);

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
    asChild?: boolean;
    loading?: boolean;
    leftIcon?: React.ReactNode;
    rightIcon?: React.ReactNode;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    (
        {
            className,
            variant,
            size,
            asChild = false,
            loading = false,
            disabled,
            leftIcon,
            rightIcon,
            children,
            ...props
        },
        ref
    ) => {
        const Comp = asChild ? Slot : "button";

        return (
            <Comp
                ref={ref}
                className={clsx(buttonVariants({ variant, size }), className)}
                disabled={disabled || loading}
                aria-busy={loading}
                {...props}
            >
                {loading ? (
                    <LoadingSpinner size={size} />
                ) : (
                    leftIcon
                )}
                <Slottable>{children}</Slottable>
                {!loading && rightIcon}
            </Comp>
        );
    }
);

Button.displayName = "Button";

// ── Loading spinner ───────────────────────────────────────────────────────────

function LoadingSpinner({ size }: { size?: string | null }) {
    const dim = size === "xs" || size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5";
    return (
        <svg
            className={clsx(dim, "animate-spin")}
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
        >
            <circle
                className="opacity-25"
                cx="12" cy="12" r="10"
                stroke="currentColor" strokeWidth="4"
            />
            <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
            />
        </svg>
    );
}

export { Button, buttonVariants };
