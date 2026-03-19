// ─────────────────────────────────────────────────────────────
// SSE streaming helper using fetch + ReadableStream.
// Uses eventsource-parser to handle chunked SSE protocol.
// Normalizes backend events into typed StreamEvent objects.
// ─────────────────────────────────────────────────────────────

import { createParser, type ParsedEvent, type ParseEvent } from "eventsource-parser";
import type { StreamEvent, StreamEventType, Citation, CriticReport } from "@/types";


export interface StreamCallbacks {
    onToken: (token: string) => void;
    onCitations: (citations: Citation[]) => void;
    onCritic: (report: CriticReport) => void;
    onClarify: (suggestion: string) => void;
    onDone: (queryLogId: string | null) => void;
    onError: (message: string) => void;
}

// ── Main streaming function ───────────────────────────────────────────────────

export async function streamQuery(
    payload: {
        query: string;
        workspace_id: string;
        top_k?: number;
    },
    callbacks: StreamCallbacks,
    signal?: AbortSignal
): Promise<void> {
    let token = "";
    if (typeof window !== "undefined") {
        token = localStorage.getItem("access_token") || "";
    }

    if (!token) {
        callbacks.onError("Not authenticated");
        return;
    }

    const response = await fetch("/api/query", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ ...payload, stream: true }),
        signal,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Request failed." }));
        callbacks.onError(
            typeof error.detail === "string"
                ? error.detail
                : "Request failed. Please try again."
        );
        return;
    }

    if (!response.body) {
        callbacks.onError("No response body received.");
        return;
    }

    // ── Parse SSE stream ──────────────────────────────────────────────────────
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    const parser = createParser((event: ParseEvent) => {
        if (event.type !== "event") return;

        const rawData = (event as ParsedEvent).data;
        if (!rawData || rawData === "[DONE]") return;

        try {
            const parsed = JSON.parse(rawData) as StreamEvent;
            handleStreamEvent(parsed, callbacks);
        } catch {
            // Malformed JSON chunk — skip silently
        }
    });

    // ── Read chunks from stream ───────────────────────────────────────────────
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            parser.feed(decoder.decode(value, { stream: true }));
        }
    } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
            // User cancelled — not an error
            return;
        }
        callbacks.onError("Stream interrupted. Please retry.");
    } finally {
        reader.releaseLock();
    }
}

// ── Event dispatcher ──────────────────────────────────────────────────────────

function handleStreamEvent(
    event: StreamEvent,
    callbacks: StreamCallbacks
): void {
    switch (event.type as StreamEventType) {
        case "token":
            if (typeof event.data === "string") {
                callbacks.onToken(event.data);
            }
            break;

        case "citations":
            if (Array.isArray(event.data)) {
                callbacks.onCitations(event.data as Citation[]);
            }
            break;

        case "critic":
            if (event.data && typeof event.data === "object") {
                callbacks.onCritic(event.data as CriticReport);
            }
            break;

        case "clarify":
            if (typeof event.data === "string") {
                callbacks.onClarify(event.data);
            }
            break;

        case "done":
            callbacks.onDone(event.query_log_id ?? null);
            break;

        case "error":
            callbacks.onError(
                typeof event.data === "string"
                    ? event.data
                    : "An error occurred during processing."
            );
            break;

        default:
            break;
    }
}

// ── Latency tracker ───────────────────────────────────────────────────────────

export class StreamTimer {
    private _start: number;
    private _firstTokenAt: number | null = null;

    constructor() {
        this._start = performance.now();
    }

    markFirstToken(): void {
        if (!this._firstTokenAt) {
            this._firstTokenAt = performance.now();
        }
    }

    getTTFT(): number | null {
        if (!this._firstTokenAt) return null;
        return Math.round(this._firstTokenAt - this._start);
    }

    getTotalLatency(): number {
        return Math.round(performance.now() - this._start);
    }
}

// ── Token cost estimator ──────────────────────────────────────────────────────
// Rough estimates only — for display purposes in the footer.
// Based on GPT-4o-mini pricing as a reference baseline.

export function estimateTokenCost(text: string, provider: string): string {
    const estimatedTokens = Math.ceil(text.length / 4);

    if (provider === "local") return "Free (local)";
    if (provider === "groq") return "Free (Groq tier)";

    // OpenAI GPT-4o-mini: $0.15 / 1M input tokens
    const costUsd = (estimatedTokens / 1_000_000) * 0.15;
    if (costUsd < 0.001) return "< $0.001";
    return `~$${costUsd.toFixed(4)}`;
}
