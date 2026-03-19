"use client";

import * as React from "react";
import clsx from "clsx";

// ── Text Input ────────────────────────────────────────────────────────────────

export interface InputProps
    extends React.InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    hint?: string;
    error?: string;
    leftIcon?: React.ReactNode;
    rightSlot?: React.ReactNode;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
    (
        {
            className,
            label,
            hint,
            error,
            leftIcon,
            rightSlot,
            id,
            type = "text",
            disabled,
            ...props
        },
        ref
    ) => {
        const fallbackId = React.useId();
        const inputId = id ?? fallbackId;
        const hintId = `${inputId}-hint`;
        const errorId = `${inputId}-error`;

        return (
            <div className="flex flex-col gap-1.5 w-full">
                {label && (
                    <label
                        htmlFor={inputId}
                        className="text-xs font-medium text-text-secondary"
                    >
                        {label}
                    </label>
                )}

                <div
                    className={clsx(
                        "relative flex items-center w-full",
                        "bg-bg-2 rounded-md border",
                        "transition-all duration-fast",
                        error
                            ? "border-danger/50 focus-within:border-danger focus-within:shadow-[0_0_0_2px_rgba(239,68,68,0.25)]"
                            : "border-glass-border focus-within:border-accent/40 focus-within:shadow-[0_0_0_2px_rgba(94,234,212,0.15)]",
                        disabled && "opacity-50 cursor-not-allowed"
                    )}
                >
                    {leftIcon && (
                        <span className="pl-3 text-text-muted shrink-0" aria-hidden="true">
                            {leftIcon}
                        </span>
                    )}

                    <input
                        ref={ref}
                        id={inputId}
                        type={type}
                        disabled={disabled}
                        aria-invalid={Boolean(error)}
                        aria-describedby={
                            error ? errorId : hint ? hintId : undefined
                        }
                        className={clsx(
                            "w-full bg-transparent px-3 py-2 text-sm text-text-primary",
                            "placeholder:text-text-muted",
                            "outline-none",
                            "disabled:cursor-not-allowed",
                            leftIcon && "pl-1.5",
                            rightSlot && "pr-1.5",
                            className
                        )}
                        {...props}
                    />

                    {rightSlot && (
                        <span className="pr-2 shrink-0">{rightSlot}</span>
                    )}
                </div>

                {error && (
                    <p id={errorId} className="text-xs text-danger" role="alert">
                        {error}
                    </p>
                )}

                {hint && !error && (
                    <p id={hintId} className="text-xs text-text-muted">
                        {hint}
                    </p>
                )}
            </div>
        );
    }
);

Input.displayName = "Input";

// ── Textarea ──────────────────────────────────────────────────────────────────

export interface TextareaProps
    extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
    label?: string;
    hint?: string;
    error?: string;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
    ({ className, label, hint, error, id, disabled, ...props }, ref) => {
        const fallbackId = React.useId();
        const textareaId = id ?? fallbackId;
        const errorId = `${textareaId}-error`;

        return (
            <div className="flex flex-col gap-1.5 w-full">
                {label && (
                    <label
                        htmlFor={textareaId}
                        className="text-xs font-medium text-text-secondary"
                    >
                        {label}
                    </label>
                )}

                <textarea
                    ref={ref}
                    id={textareaId}
                    disabled={disabled}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? errorId : undefined}
                    className={clsx(
                        "w-full bg-bg-2 rounded-md border px-3 py-2",
                        "text-sm text-text-primary placeholder:text-text-muted",
                        "resize-none outline-none",
                        "transition-all duration-fast",
                        error
                            ? "border-danger/50 focus:border-danger focus:shadow-[0_0_0_2px_rgba(239,68,68,0.25)]"
                            : "border-glass-border focus:border-accent/40 focus:shadow-[0_0_0_2px_rgba(94,234,212,0.15)]",
                        disabled && "opacity-50 cursor-not-allowed",
                        className
                    )}
                    {...props}
                />

                {error && (
                    <p id={errorId} className="text-xs text-danger" role="alert">
                        {error}
                    </p>
                )}

                {hint && !error && (
                    <p className="text-xs text-text-muted">{hint}</p>
                )}
            </div>
        );
    }
);

Textarea.displayName = "Textarea";

export { Input, Textarea };
