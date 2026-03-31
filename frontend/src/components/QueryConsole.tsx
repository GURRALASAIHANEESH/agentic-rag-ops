"use client";

import React, { useRef, useEffect, useCallback, useId } from "react";
import {
  Send, Square, RotateCcw, ChevronDown,
  Thermometer, Search, BookOpen, MessageSquare, Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { ClaimBadge, ConfidenceBadge } from "@/components/ui/Badge";
import { SkeletonQueryResult } from "@/components/ui/Skeleton";
import { useStreaming } from "@/hooks/useStreaming";
import { estimateTokenCost } from "@/lib/streaming";
import type { Citation, ClaimVerification, QuerySettings, LLMProvider, CriticReport } from "@/types";

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

interface QueryConsoleProps {
  workspaceId: string;
  initialQuery?: string;
  onCitationSelect?: (citation: Citation) => void;
  onCitationsChange?: (citations: Citation[]) => void;
  onCriticChange?: (critic: CriticReport | null) => void;
  onQueryLogIdChange?: (id: string | null) => void;
  onQueryStart?: () => void;
}

export function QueryConsole({
  workspaceId,
  initialQuery = "",
  onCitationSelect,
  onCitationsChange,
  onCriticChange,
  onQueryLogIdChange,
  onQueryStart,
}: QueryConsoleProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const answerRef = useRef<HTMLDivElement>(null);
  const settingsId = useId();

  const [query, setQuery] = React.useState(initialQuery);
  const [settings, setSettings] = React.useState(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = React.useState(false);
  const [showReasoning, setShowReasoning] = React.useState(false);

  const { state, submit, cancel, reset } = useStreaming({
    workspaceId,
    topK: settings.top_k,
  });

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => { resizeTextarea(); }, [query, resizeTextarea]);

  // Auto-scroll answer
  useEffect(() => {
    if (state.isStreaming && answerRef.current) {
      answerRef.current.scrollTop = answerRef.current.scrollHeight;
    }
  }, [state.tokens, state.isStreaming]);

  // Ctrl+K focus shortcut
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

  // Lift citations, critic, queryLogId to parent
  useEffect(() => {
    onCitationsChange?.(state.citations);
  }, [state.citations, onCitationsChange]);

  useEffect(() => {
    onCriticChange?.(state.critic ?? null);
  }, [state.critic, onCriticChange]);

  useEffect(() => {
    onQueryLogIdChange?.(state.queryLogId ?? null);
  }, [state.queryLogId, onQueryLogIdChange]);

  // KEY FIX: Enter = new line only. Send button is the ONLY way to submit.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();  // always block — including Shift+Enter submit
        if (!e.shiftKey) {
          // insert newline manually
          const el = textareaRef.current;
          if (!el) return;
          const start = el.selectionStart;
          const end = el.selectionEnd;
          const val = e.currentTarget.value;
          const newVal = val.substring(0, start) + "\n" + val.substring(end);
          setQuery(newVal);
          requestAnimationFrame(() => {
            el.selectionStart = el.selectionEnd = start + 1;
          });
        }
      }
    },
    []
  );

  const handleSubmit = useCallback(async () => {
    if (!query.trim() || state.isStreaming) return;
    onQueryStart?.();
    await submit(query.trim());
  }, [query, state.isStreaming, submit, onQueryStart]);

  const handleReset = useCallback(() => {
    reset();
    setQuery("");
    textareaRef.current?.focus();
  }, [reset]);

  const hasAnswer = Boolean(state.tokens);
  const hasCitations = state.citations.length > 0;

  return (
    <div className="flex flex-col h-full">

      {/* ── Answer area ── */}
      <div ref={answerRef} className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide">

        {!hasAnswer && !state.isStreaming && !state.error && !state.clarification && (
          <EmptyState onExampleClick={(q) => setQuery(q)} />
        )}

        {state.isStreaming && !hasAnswer && <SkeletonQueryResult />}

        {state.clarification && <ClarificationBanner message={state.clarification} />}

        {state.error && (
          <ErrorBanner message={state.error} onRetry={handleSubmit} />
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

        {(hasAnswer || hasCitations) && !state.isStreaming && (
          <MetaBar
            latencyMs={state.latencyMs ?? null}
            provider={settings.provider}
            citationCount={state.citations.length}
            criticScore={state.critic?.overall_score ?? null}
            tokens={state.tokens}
          />
        )}
      </div>

      {/* ── Input area ── */}
      <div className="flex-shrink-0 p-4 border-t border-white/[0.06]">

        {/* Settings panel */}
        {showSettings && (
          <SettingsPanel
            id={settingsId}
            settings={settings}
            onChange={setSettings}
          />
        )}

        {/* Input row */}
        <div className={clsx(
          "flex items-end gap-2 rounded-xl border p-3 input-ring transition-all",
          "bg-white/[0.03] border-white/[0.08]"
        )}>
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents... (Enter for newline, click Send to submit)"
            rows={1}
            disabled={state.isStreaming}
            aria-label="Query input"
            className={clsx(
              "flex-1 resize-none bg-transparent px-1 py-1",
              "text-sm text-white/90 placeholder:text-white/25",
              "outline-none scrollbar-hide leading-relaxed",
              "disabled:opacity-50"
            )}
            style={{ minHeight: "36px", maxHeight: "200px" }}
          />

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {/* Settings toggle */}
            <button
              onClick={() => setShowSettings((v) => !v)}
              aria-label="Query settings"
              className={clsx(
                "p-2 rounded-lg transition-all text-white/40 hover:text-white/70 hover:bg-white/[0.06]",
                showSettings && "text-indigo-400 bg-indigo-500/10"
              )}
            >
              <Thermometer size={15} />
            </button>

            {/* Cancel / Reset / Send */}
            {state.isStreaming ? (
              <button onClick={cancel}
                className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-all"
                aria-label="Cancel">
                <Square size={15} />
              </button>
            ) : hasAnswer ? (
              <button onClick={handleReset}
                className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/[0.06] transition-all"
                aria-label="New query">
                <RotateCcw size={15} />
              </button>
            ) : null}

            <button
              onClick={handleSubmit}
              disabled={!query.trim() || state.isStreaming}
              className={clsx(
                "btn-accent flex items-center gap-1.5 px-3 py-2 text-xs",
                (!query.trim() || state.isStreaming) && "opacity-40 cursor-not-allowed pointer-events-none"
              )}
              aria-label="Send query"
            >
              <Send size={13} />
              Send
            </button>
          </div>
        </div>

        <p className="text-[10px] text-white/20 mt-2 text-center">
          Press <kbd className="px-1 py-0.5 rounded bg-white/[0.06] text-white/30 font-mono text-[10px]">Enter</kbd> for new line
          &nbsp;·&nbsp;
          <kbd className="px-1 py-0.5 rounded bg-white/[0.06] text-white/30 font-mono text-[10px]">Ctrl+K</kbd> to focus
        </p>
      </div>
    </div>
  );
}

// ── AnswerBlock ───────────────────────────────────────────────────────────────

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
  tokens, isStreaming, claims, citations,
  showReasoning, onToggleReasoning, onCitationSelect,
}: AnswerBlockProps) {
  return (
    <div className="glass-panel p-5 space-y-4 animate-fade-in">
      {/* Answer text */}
      <div className={clsx(
        "text-sm text-white/85 leading-relaxed whitespace-pre-wrap",
        isStreaming && "streaming-cursor"
      )}>
        {tokens}
      </div>

      {/* Citations */}
      {citations.length > 0 && (
        <CitationRow citations={citations} onSelect={onCitationSelect} />
      )}

      {/* Reasoning toggle */}
      {claims.length > 0 && (
        <div>
          <button
            onClick={onToggleReasoning}
            className="flex items-center gap-2 text-xs text-white/40 hover:text-white/70 transition-colors"
          >
            <ChevronDown size={13} className={clsx("transition-transform", showReasoning && "rotate-180")} />
            {showReasoning ? "Hide" : "Show"} reasoning & verification
            <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-white/30 text-[10px]">
              {claims.length} claim{claims.length !== 1 ? "s" : ""}
            </span>
          </button>

          {showReasoning && (
            <div className="mt-3 animate-slide-up">
              <ClaimsInline claims={claims} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── ClaimsInline ──────────────────────────────────────────────────────────────

function ClaimsInline({ claims }: { claims: ClaimVerification[] }) {
  return (
    <div className="space-y-2">
      {claims.map((claim, i) => (
        <div key={i} className="flex items-start gap-2.5 text-xs text-white/60 p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.05]">
          <ClaimBadge status={claim.status} />
          <span className="flex-1 leading-relaxed">{claim.claim}</span>
          <ConfidenceBadge score={claim.confidence} />
        </div>
      ))}
    </div>
  );
}

// ── CitationRow ───────────────────────────────────────────────────────────────

function CitationRow({ citations, onSelect }: { citations: Citation[]; onSelect?: (c: Citation) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {citations.map((c, i) => (
        <button
          key={i}
          onClick={() => onSelect?.(c)}
          className={clsx(
            "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg",
            "text-xs text-white/50 font-medium",
            "bg-white/[0.03] border border-white/[0.07]",
            "hover:border-indigo-500/40 hover:text-indigo-300 hover:bg-indigo-500/[0.07]",
            "transition-all duration-150"
          )}
        >
          <BookOpen size={11} className="flex-shrink-0" />
          <span className="truncate max-w-[160px]">{c.filename}</span>
          <span className={clsx(
            "px-1 py-0.5 rounded text-[10px] font-bold",
            c.similarity >= 0.6 ? "bg-emerald-500/15 text-emerald-400" :
              c.similarity >= 0.4 ? "bg-amber-500/15 text-amber-400" :
                "bg-white/[0.06] text-white/30"
          )}>
            {Math.round(c.similarity * 100)}%
          </span>
        </button>
      ))}
    </div>
  );
}

// ── SettingsPanel ─────────────────────────────────────────────────────────────

function SettingsPanel({ id, settings, onChange }: { id: string; settings: QuerySettings; onChange: (s: QuerySettings) => void }) {
  return (
    <div id={id} className="mb-3 p-4 rounded-xl bg-white/[0.03] border border-white/[0.07] space-y-4 animate-slide-up">
      <div className="flex items-center justify-between gap-4">
        {/* Provider */}
        <div className="space-y-1">
          <label className="text-[10px] text-white/30 font-medium uppercase tracking-wider">Model</label>
          <select
            value={settings.provider}
            onChange={(e) => onChange({ ...settings, provider: e.target.value as LLMProvider })}
            className="bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-white/80 outline-none focus:border-indigo-500/40 transition-colors"
          >
            {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>

        {/* Top-K */}
        <div className="flex-1 space-y-1">
          <div className="flex justify-between">
            <label className="text-[10px] text-white/30 font-medium uppercase tracking-wider">Sources (top-K)</label>
            <span className="text-[10px] text-indigo-400 font-bold">{settings.top_k}</span>
          </div>
          <input type="range" min={1} max={20} value={settings.top_k}
            onChange={(e) => onChange({ ...settings, top_k: Number(e.target.value) })}
            className="w-full accent-indigo-500 h-1" />
        </div>

        {/* Temperature */}
        <div className="flex-1 space-y-1">
          <div className="flex justify-between">
            <label className="text-[10px] text-white/30 font-medium uppercase tracking-wider">Temperature</label>
            <span className="text-[10px] text-indigo-400 font-bold">{settings.temperature.toFixed(2)}</span>
          </div>
          <input type="range" min={0} max={1} step={0.05} value={settings.temperature}
            onChange={(e) => onChange({ ...settings, temperature: Number(e.target.value) })}
            className="w-full accent-indigo-500 h-1" />
        </div>
      </div>

      <div className="flex gap-4">
        <Toggle label="Critic agent" checked={settings.run_critic}
          onChange={(v) => onChange({ ...settings, run_critic: v })}
          icon={<Search size={12} />} />
        <Toggle label="Cite sources" checked={settings.cite_sources}
          onChange={(v) => onChange({ ...settings, cite_sources: v })}
          icon={<BookOpen size={12} />} />
      </div>
    </div>
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({ label, checked, onChange, icon }: { label: string; checked: boolean; onChange: (v: boolean) => void; icon?: React.ReactNode }) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex items-center gap-2 cursor-pointer group">
      {icon && <span className="text-white/30 group-hover:text-white/50 transition-colors">{icon}</span>}
      <span className="text-xs text-white/50 group-hover:text-white/70 transition-colors">{label}</span>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative inline-flex h-4 w-7 items-center rounded-full transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60",
          checked ? "bg-indigo-500" : "bg-white/[0.12]"
        )}
      >
        <span className={clsx(
          "inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform duration-150",
          checked ? "translate-x-3.5" : "translate-x-0.5"
        )} />
      </button>
    </label>
  );
}

// ── MetaBar ───────────────────────────────────────────────────────────────────

function MetaBar({ latencyMs, provider, citationCount, criticScore, tokens }: {
  latencyMs: number | null; provider: LLMProvider; citationCount: number; criticScore: number | null; tokens: string;
}) {
  const scoreClass = criticScore === null ? "" : criticScore >= 0.8 ? "high" : criticScore >= 0.6 ? "mid" : "low";
  return (
    <div className="flex items-center gap-3 text-[11px] text-white/30 px-1">
      {latencyMs !== null && (
        <span className="tabular-nums">{latencyMs}ms</span>
      )}
      <span>·</span>
      <span className="text-indigo-400/70">{provider}</span>
      <span>·</span>
      <span>{citationCount} source{citationCount !== 1 ? "s" : ""}</span>
      {criticScore !== null && (
        <>
          <span>·</span>
          <div className={`score-ring ${scoreClass}`}>
            {Math.round(criticScore * 100)}
          </div>
        </>
      )}
      <span className="ml-auto">{estimateTokenCost(tokens, provider)}</span>
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────────────────

function EmptyState({ onExampleClick }: { onExampleClick: (q: string) => void }) {
  const examples = [
    "What is the attention mechanism in Transformers?",
    "How does FAISS handle approximate nearest neighbor search?",
    "What are the differences between pgvector and FAISS?",
  ];
  return (
    <div className="flex flex-col items-center justify-center h-full py-16 space-y-6 animate-fade-in">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
        style={{ background: "linear-gradient(135deg,rgba(99,102,241,0.15),rgba(139,92,246,0.15))", border: "1px solid rgba(99,102,241,0.2)" }}>
        <Sparkles size={24} className="text-indigo-400" />
      </div>
      <div className="text-center">
        <p className="text-white/60 font-medium">Ask anything about your documents</p>
        <p className="text-xs text-white/25 mt-1">Every answer is verified with source citations</p>
      </div>
      <div className="flex flex-col gap-2 w-full max-w-md">
        {examples.map((q) => (
          <button key={q} onClick={() => onExampleClick(q)}
            className={clsx(
              "text-left text-xs text-white/45 px-4 py-3 rounded-xl",
              "border border-white/[0.07] bg-white/[0.02]",
              "hover:border-indigo-500/30 hover:text-white/70 hover:bg-indigo-500/[0.05]",
              "transition-all duration-150"
            )}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── ClarificationBanner ───────────────────────────────────────────────────────

function ClarificationBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] animate-fade-in">
      <MessageSquare size={15} className="text-amber-400 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-xs font-semibold text-amber-300">Query needs clarification</p>
        <p className="text-xs text-white/50 mt-1 leading-relaxed">{message}</p>
      </div>
    </div>
  );
}

// ── ErrorBanner ───────────────────────────────────────────────────────────────

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl border border-red-500/20 bg-red-500/[0.06] animate-fade-in">
      <div className="flex-1">
        <p className="text-xs font-semibold text-red-300">Something went wrong</p>
        <p className="text-xs text-white/50 mt-1 leading-relaxed">{message}</p>
      </div>
      <button onClick={onRetry}
        className="text-xs text-red-400 hover:text-red-300 border border-red-500/20 hover:border-red-500/40 px-2.5 py-1 rounded-lg transition-all">
        Retry
      </button>
    </div>
  );
}
