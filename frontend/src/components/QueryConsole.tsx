"use client";

import React, { useRef, useEffect, useCallback, useId } from "react";
import {
    Send, Square, RotateCcw, ChevronDown,
    Thermometer, Search, BookOpen, MessageSquare,
} from "lucide-react";
import clsx from "clsx";
import { Button } from "@/components/ui/Button";
import { Badge, ClaimBadge, ConfidenceBadge } from "@/components/ui/Badge";
import { SkeletonQueryResult } from "@/components/ui/Skeleton";
import { useStreaming } from "@/hooks/useStreaming";
import { estimateTokenCost } from "@/lib/streaming";
import type { Citation, ClaimVerification, QuerySettings, LLMProvider } from "@/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const PROVIDERS: { value: LLMProvider; label: string }[] = [
    { value: "local", label: "Local Llama" },
    { value: "groq", label: "Groq" },
    { value: "openai", label: "OpenAI" },
];

const DEFAULT_SETTINGS: QuerySettings = {
    provider: "local",
    top_k: 5,
    run_critic: true,
    cite_sources: true,
    temperature: 0.2,
};

// ── Props ─────────────────────────────────────────────────────────────────────

interface QueryConsoleProps {
    workspaceId: string;
    initialQuery?: string;
    onCitationSelect?: (citation: Citation) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function QueryConsole({
    workspaceId,
    initialQuery = "",
    onCitationSelect,
}: QueryConsoleProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const answerRef = useRef<HTMLDivElement>(null);
    const settingsId = useId();

    const [query, setQuery] = React.useState(initialQuery);
    const [settings, setSettings] = React.useState<QuerySettings>(DEFAULT_SETTINGS);
    const [showSettings, setShowSettings] = React.useState(false);
    const [showReasoning, setShowReasoning] = React.useState(false);

    const { state, submit, cancel, reset } = useStreaming({
        workspaceId,
        topK: settings.top_k,
    });

    // ── Auto-resize textarea ──────────────────────────────────────────────────
    const resizeTextarea = useCallback(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }, []);

    useEffect(() => {
        resizeTextarea();
    }, [query, resizeTextarea]);

    // ── Scroll answer into view as tokens arrive ──────────────────────────────
    useEffect(() => {
        if (state.isStreaming && answerRef.current) {
            answerRef.current.scrollTop = answerRef.current.scrollHeight;
        }
    }, [state.tokens, state.isStreaming]);

    // ── Keyboard shortcuts ────────────────────────────────────────────────────
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                textareaRef.current?.focus();
            }
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, []);

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                if (!query.trim() || state.isStreaming) return;
                void submit(query.trim());
            }
        },
        [query, state.isStreaming, submit]
    );

    const handleSubmit = useCallback(async () => {
        if (!query.trim() || state.isStreaming) return;
        await submit(query.trim());
    }, [query, state.isStreaming, submit]);

    const handleReset = useCallback(() => {
        reset();
        setQuery("");
        textareaRef.current?.focus();
    }, [reset]);

    const hasAnswer = Boolean(state.tokens);
    const hasCitations = state.citations.length > 0;

    return (
        <div className="flex flex-col h-full min-h-0">

            {/* ── Answer area ────────────────────────────────────────────────────── */}
            <div
                ref={answerRef}
                className="flex-1 overflow-y-auto min-h-0 scrollbar-hide"
                role="region"
                aria-label="Query response"
                aria-live="polite"
                aria-atomic="false"
            >
                {!hasAnswer && !state.isStreaming && !state.error && !state.clarification && (
                    <EmptyState onExampleClick={(q) => setQuery(q)} />
                )}

                {state.isStreaming && !hasAnswer && (
                    <SkeletonQueryResult className="animate-fade-in" />
                )}

                {state.clarification && (
                    <ClarificationBanner message={state.clarification} />
                )}

                {state.error && (
                    <ErrorBanner message={state.error} onRetry={handleReset} />
                )}

                {hasAnswer && (
                    <AnswerBlock
                        tokens={state.tokens}
                        isStreaming={state.isStreaming}
                        claims={state.critic?.claims ?? []}
                        citations={state.citations}
                        showReasoning={showReasoning}
                        onToggleReasoning={() => setShowReasoning((v) => !v)}
                        onCitationSelect={onCitationSelect}
                    />
                )}
            </div>

            {/* ── Footer metadata bar ───────────────────────────────────────────── */}
            {(hasAnswer || hasCitations) && !state.isStreaming && (
                <MetaBar
                    latencyMs={state.latencyMs}
                    provider={settings.provider}
                    citationCount={state.citations.length}
                    criticScore={state.critic?.overall_score ?? null}
                    tokens={state.tokens}
                />
            )}

            {/* ── Input area ────────────────────────────────────────────────────── */}
            <div className="shrink-0 pt-3 border-t border-glass-border">

                {/* Settings panel */}
                {showSettings && (
                    <SettingsPanel
                        id={settingsId}
                        settings={settings}
                        onChange={setSettings}
                    />
                )}

                {/* Input row */}
                <div
                    className={clsx(
                        "relative flex items-end gap-2 p-2 rounded-xl",
                        "bg-bg-2 border border-glass-border",
                        "transition-shadow duration-fast",
                        "focus-within:border-accent/40 focus-within:shadow-[0_0_0_2px_rgba(94,234,212,0.12)]"
                    )}
                >
                    <textarea
                        ref={textareaRef}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask a question about your documents..."
                        rows={1}
                        disabled={state.isStreaming}
                        aria-label="Query input"
                        aria-describedby="query-hint"
                        className={clsx(
                            "flex-1 resize-none bg-transparent px-2 py-1.5",
                            "text-sm text-text-primary placeholder:text-text-muted",
                            "outline-none scrollbar-hide",
                            "disabled:opacity-60"
                        )}
                        style={{ minHeight: "36px", maxHeight: "200px" }}
                    />

                    <div className="flex items-center gap-1 pb-0.5 shrink-0">
                        {/* Settings toggle */}
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setShowSettings((v) => !v)}
                            aria-label="Query settings"
                            aria-expanded={showSettings}
                            aria-controls={settingsId}
                            className={showSettings ? "text-accent" : ""}
                        >
                            <ChevronDown
                                className={clsx(
                                    "h-3.5 w-3.5 transition-transform duration-fast",
                                    showSettings && "rotate-180"
                                )}
                                aria-hidden="true"
                            />
                        </Button>

                        {/* Cancel / Submit */}
                        {state.isStreaming ? (
                            <Button
                                variant="danger"
                                size="icon-sm"
                                onClick={cancel}
                                aria-label="Cancel query"
                            >
                                <Square className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                        ) : hasAnswer ? (
                            <Button
                                variant="ghost"
                                size="icon-sm"
                                onClick={handleReset}
                                aria-label="Clear and start over"
                            >
                                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                        ) : null}

                        <Button
                            variant="primary"
                            size="icon-sm"
                            onClick={handleSubmit}
                            disabled={!query.trim() || state.isStreaming}
                            aria-label="Submit query (Ctrl+Enter)"
                        >
                            <Send className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                    </div>
                </div>

                <p
                    id="query-hint"
                    className="mt-1.5 px-1 text-2xs text-text-muted"
                >
                    <kbd className="font-mono">Ctrl+Enter</kbd> to submit
                    &nbsp;&middot;&nbsp;
                    <kbd className="font-mono">Ctrl+K</kbd> to focus
                </p>
            </div>
        </div>
    );
}

// ── Sub-components ────────────────────────────────────────────────────────────

// Answer block with streaming cursor and inline claim badges

interface AnswerBlockProps {
    tokens: string;
    isStreaming: boolean;
    claims: ClaimVerification[];
    citations: Citation[];
    showReasoning: boolean;
    onToggleReasoning: () => void;
    onCitationSelect?: (c: Citation) => void;
}

function AnswerBlock({
    tokens,
    isStreaming,
    claims,
    citations,
    showReasoning,
    onToggleReasoning,
    onCitationSelect,
}: AnswerBlockProps) {
    return (
        <div className="p-4 animate-fade-in">

            {/* Answer text */}
            <div
                className={clsx(
                    "text-sm text-text-primary leading-relaxed whitespace-pre-wrap",
                    isStreaming && "streaming-cursor"
                )}
            >
                {tokens}
            </div>

            {/* Citations row */}
            {citations.length > 0 && (
                <CitationRow
                    citations={citations}
                    onSelect={onCitationSelect}
                />
            )}

            {/* Expandable reasoning section */}
            {claims.length > 0 && (
                <div className="mt-4">
                    <button
                        onClick={onToggleReasoning}
                        className={clsx(
                            "flex items-center gap-1.5 text-xs text-text-muted",
                            "hover:text-text-secondary transition-colors duration-fast"
                        )}
                        aria-expanded={showReasoning}
                    >
                        <ChevronDown
                            className={clsx(
                                "h-3.5 w-3.5 transition-transform duration-fast",
                                showReasoning && "rotate-180"
                            )}
                            aria-hidden="true"
                        />
                        {showReasoning ? "Hide" : "Show"} reasoning &amp; verification
                        <Badge variant="default" size="sm">
                            {claims.length} claim{claims.length !== 1 ? "s" : ""}
                        </Badge>
                    </button>

                    {showReasoning && (
                        <ClaimsInline claims={claims} />
                    )}
                </div>
            )}
        </div>
    );
}

// Inline claim list

function ClaimsInline({ claims }: { claims: ClaimVerification[] }) {
    return (
        <ol
            className="mt-3 flex flex-col gap-2"
            aria-label="Claim verification results"
        >
            {claims.map((claim, i) => (
                <li
                    key={i}
                    className={clsx(
                        "flex items-start gap-2 p-2.5 rounded-md text-xs",
                        "border-l-2",
                        claim.status === "verified" && "border-success bg-success/5",
                        claim.status === "partial" && "border-warn bg-warn/5",
                        claim.status === "unverified" && "border-danger bg-danger/5"
                    )}
                >
                    <ClaimBadge status={claim.status} className="mt-0.5 shrink-0" />
                    <span className="text-text-secondary leading-relaxed flex-1">
                        {claim.claim}
                    </span>
                    <ConfidenceBadge score={claim.confidence} className="shrink-0 mt-0.5" />
                </li>
            ))}
        </ol>
    );
}

// Citation chips

function CitationRow({
    citations,
    onSelect,
}: {
    citations: Citation[];
    onSelect?: (c: Citation) => void;
}) {
    return (
        <div
            className="mt-3 flex flex-wrap gap-1.5"
            role="list"
            aria-label="Sources"
        >
            {citations.map((c, i) => (
                <button
                    key={c.chunk_id}
                    role="listitem"
                    onClick={() => onSelect?.(c)}
                    className={clsx(
                        "inline-flex items-center gap-1.5 px-2 py-1 rounded-md",
                        "text-2xs text-text-secondary font-medium",
                        "bg-glass border border-glass-border",
                        "hover:border-accent/40 hover:text-accent hover:bg-accent/5",
                        "transition-all duration-fast",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                    )}
                    aria-label={`Source ${i + 1}: ${c.filename}, similarity ${Math.round(c.similarity * 100)}%`}
                >
                    <BookOpen className="h-3 w-3" aria-hidden="true" />
                    <span className="truncate max-w-[120px]">{c.filename}</span>
                    <span className="text-text-muted tabular-nums">
                        {Math.round(c.similarity * 100)}%
                    </span>
                </button>
            ))}
        </div>
    );
}

// Settings panel

function SettingsPanel({
    id,
    settings,
    onChange,
}: {
    id: string;
    settings: QuerySettings;
    onChange: (s: QuerySettings) => void;
}) {
    return (
        <div
            id={id}
            className={clsx(
                "mb-3 p-3 rounded-lg border border-glass-border bg-bg-2",
                "grid grid-cols-2 gap-3 animate-fade-in"
            )}
            role="group"
            aria-label="Query settings"
        >
            {/* Provider selector */}
            <div className="flex flex-col gap-1">
                <label className="text-2xs text-text-muted font-medium uppercase tracking-wide">
                    Model
                </label>
                <select
                    value={settings.provider}
                    onChange={(e) =>
                        onChange({ ...settings, provider: e.target.value as LLMProvider })
                    }
                    className={clsx(
                        "bg-bg-1 border border-glass-border rounded-md px-2 py-1.5",
                        "text-xs text-text-primary outline-none",
                        "focus:border-accent/40",
                        "transition-colors duration-fast"
                    )}
                    aria-label="LLM provider"
                >
                    {PROVIDERS.map((p) => (
                        <option key={p.value} value={p.value}>
                            {p.label}
                        </option>
                    ))}
                </select>
            </div>

            {/* Top-K */}
            <div className="flex flex-col gap-1">
                <label className="text-2xs text-text-muted font-medium uppercase tracking-wide">
                    Sources (top-K)
                </label>
                <div className="flex items-center gap-2">
                    <input
                        type="range"
                        min={1}
                        max={10}
                        value={settings.top_k}
                        onChange={(e) =>
                            onChange({ ...settings, top_k: Number(e.target.value) })
                        }
                        className="flex-1 accent-accent h-1.5"
                        aria-label={`Top K sources: ${settings.top_k}`}
                    />
                    <span className="text-xs text-text-secondary tabular-nums w-4 text-right">
                        {settings.top_k}
                    </span>
                </div>
            </div>

            {/* Temperature */}
            <div className="flex flex-col gap-1">
                <label className="text-2xs text-text-muted font-medium uppercase tracking-wide flex items-center gap-1">
                    <Thermometer className="h-3 w-3" aria-hidden="true" />
                    Temperature
                </label>
                <div className="flex items-center gap-2">
                    <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={settings.temperature}
                        onChange={(e) =>
                            onChange({ ...settings, temperature: Number(e.target.value) })
                        }
                        className="flex-1 accent-accent h-1.5"
                        aria-label={`Temperature: ${settings.temperature}`}
                    />
                    <span className="text-xs text-text-secondary tabular-nums w-6 text-right">
                        {settings.temperature.toFixed(2)}
                    </span>
                </div>
            </div>

            {/* Toggles */}
            <div className="flex flex-col gap-2 justify-center">
                <Toggle
                    label="Run critic"
                    checked={settings.run_critic}
                    onChange={(v) => onChange({ ...settings, run_critic: v })}
                    icon={<Search className="h-3 w-3" />}
                />
                <Toggle
                    label="Cite sources"
                    checked={settings.cite_sources}
                    onChange={(v) => onChange({ ...settings, cite_sources: v })}
                    icon={<MessageSquare className="h-3 w-3" />}
                />
            </div>
        </div>
    );
}

// Toggle switch

function Toggle({
    label,
    checked,
    onChange,
    icon,
}: {
    label: string;
    checked: boolean;
    onChange: (v: boolean) => void;
    icon?: React.ReactNode;
}) {
    const id = useId();
    return (
        <div className="flex items-center justify-between gap-2">
            <label
                htmlFor={id}
                className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer"
            >
                {icon && <span className="text-text-muted" aria-hidden="true">{icon}</span>}
                {label}
            </label>
            <button
                id={id}
                role="switch"
                aria-checked={checked}
                onClick={() => onChange(!checked)}
                className={clsx(
                    "relative inline-flex h-4 w-7 items-center rounded-full",
                    "transition-colors duration-fast focus-visible:outline-none",
                    "focus-visible:ring-2 focus-visible:ring-accent/60",
                    checked ? "bg-accent" : "bg-glass-border"
                )}
            >
                <span
                    className={clsx(
                        "inline-block h-3 w-3 rounded-full bg-bg-1",
                        "transform transition-transform duration-fast shadow-sm",
                        checked ? "translate-x-3.5" : "translate-x-0.5"
                    )}
                    aria-hidden="true"
                />
            </button>
        </div>
    );
}

// Meta bar

function MetaBar({
    latencyMs,
    provider,
    citationCount,
    criticScore,
    tokens,
}: {
    latencyMs: number | null;
    provider: LLMProvider;
    citationCount: number;
    criticScore: number | null;
    tokens: string;
}) {
    return (
        <div
            className="flex items-center gap-3 px-1 py-2 text-2xs text-text-muted tabular-nums"
            aria-label="Response metadata"
        >
            {latencyMs !== null && (
                <span>{latencyMs}ms</span>
            )}
            <span className="text-text-muted/50">&middot;</span>
            <span>{provider}</span>
            <span className="text-text-muted/50">&middot;</span>
            <span>{citationCount} source{citationCount !== 1 ? "s" : ""}</span>
            {criticScore !== null && (
                <>
                    <span className="text-text-muted/50">&middot;</span>
                    <ConfidenceBadge score={criticScore} size="sm" />
                </>
            )}
            <span className="ml-auto">
                {estimateTokenCost(tokens, provider)}
            </span>
        </div>
    );
}

// Empty state

function EmptyState({ onExampleClick }: { onExampleClick: (q: string) => void }) {
    const examples = [
        "What is the attention mechanism in Transformers?",
        "How does FAISS handle approximate nearest neighbor search?",
        "What are the differences between pgvector and FAISS?",
    ];

    return (
        <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-4 p-6 text-center animate-fade-in">
            <p className="text-sm text-text-muted">
                Ask a question about your documents.
            </p>
            <div className="flex flex-col gap-2 w-full max-w-sm">
                {examples.map((q) => (
                    <button
                        key={q}
                        onClick={() => onExampleClick(q)}
                        className={clsx(
                            "text-left text-xs text-text-secondary px-3 py-2 rounded-md",
                            "border border-glass-border bg-glass",
                            "hover:border-accent/30 hover:text-text-primary hover:bg-accent/5",
                            "transition-all duration-fast",
                            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                        )}
                    >
                        {q}
                    </button>
                ))}
            </div>
        </div>
    );
}

// Clarification banner

function ClarificationBanner({ message }: { message: string }) {
    return (
        <div
            className="m-4 p-3 rounded-lg border border-warn/30 bg-warn/5 animate-fade-in"
            role="status"
            aria-label="Clarification needed"
        >
            <p className="text-xs font-medium text-warn mb-1">
                Query needs clarification
            </p>
            <p className="text-sm text-text-secondary">{message}</p>
        </div>
    );
}

// Error banner

function ErrorBanner({
    message,
    onRetry,
}: {
    message: string;
    onRetry: () => void;
}) {
    return (
        <div
            className="m-4 p-3 rounded-lg border border-danger/30 bg-danger/5 animate-fade-in"
            role="alert"
        >
            <p className="text-xs font-medium text-danger mb-1">
                Something went wrong
            </p>
            <p className="text-sm text-text-secondary mb-2">{message}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
                Try again
            </Button>
        </div>
    );
}
