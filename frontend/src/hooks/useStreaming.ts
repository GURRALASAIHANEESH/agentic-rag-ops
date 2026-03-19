"use client";

import { useCallback, useRef, useReducer } from "react";
import type { Citation, CriticReport, StreamingState } from "@/types";
import { INITIAL_STREAMING_STATE } from "@/types";
import { streamQuery, StreamTimer } from "@/lib/streaming";

// ── Reducer ───────────────────────────────────────────────────────────────────

type StreamAction =
    | { type: "START" }
    | { type: "APPEND_TOKEN"; payload: string }
    | { type: "SET_CITATIONS"; payload: Citation[] }
    | { type: "SET_CRITIC"; payload: CriticReport }
    | { type: "SET_CLARIFY"; payload: string }
    | { type: "SET_ERROR"; payload: string }
    | { type: "DONE"; payload: { queryLogId: string | null; latencyMs: number } }
    | { type: "RESET" };

function streamReducer(state: StreamingState, action: StreamAction): StreamingState {
    switch (action.type) {
        case "START":
            return { ...INITIAL_STREAMING_STATE, isStreaming: true };
        case "APPEND_TOKEN":
            return { ...state, tokens: state.tokens + action.payload };
        case "SET_CITATIONS":
            return { ...state, citations: action.payload };
        case "SET_CRITIC":
            return { ...state, critic: action.payload };
        case "SET_CLARIFY":
            return { ...state, clarification: action.payload, isStreaming: false };
        case "SET_ERROR":
            return { ...state, error: action.payload, isStreaming: false };
        case "DONE":
            return {
                ...state,
                isStreaming: false,
                queryLogId: action.payload.queryLogId,
                latencyMs: action.payload.latencyMs,
            };
        case "RESET":
            return INITIAL_STREAMING_STATE;
        default:
            return state;
    }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

interface UseStreamingOptions {
    workspaceId: string;
    topK?: number;
}

interface UseStreamingReturn {
    state: StreamingState;
    submit: (query: string) => Promise<void>;
    cancel: () => void;
    reset: () => void;
}

export function useStreaming({
    workspaceId,
    topK = 5,
}: UseStreamingOptions): UseStreamingReturn {
    const [state, dispatch] = useReducer(streamReducer, INITIAL_STREAMING_STATE);
    const abortRef = useRef<AbortController | null>(null);
    const timerRef = useRef<StreamTimer | null>(null);

    const cancel = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = null;
        dispatch({
            type: "DONE",
            payload: {
                queryLogId: null,
                latencyMs: timerRef.current?.getTotalLatency() ?? 0,
            },
        });
    }, []);

    const reset = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = null;
        timerRef.current = null;
        dispatch({ type: "RESET" });
    }, []);

    const submit = useCallback(
        async (query: string) => {
            if (!workspaceId || !query.trim()) return;

            abortRef.current?.abort();
            const controller = new AbortController();
            abortRef.current = controller;
            timerRef.current = new StreamTimer();

            dispatch({ type: "START" });

            let firstToken = true;

            await streamQuery(
                { query: query.trim(), workspace_id: workspaceId, top_k: topK },
                {
                    onToken: (token) => {
                        if (firstToken) {
                            timerRef.current?.markFirstToken();
                            firstToken = false;
                        }
                        dispatch({ type: "APPEND_TOKEN", payload: token });
                    },
                    onCitations: (citations) => {
                        dispatch({ type: "SET_CITATIONS", payload: citations });
                    },
                    onCritic: (report) => {
                        dispatch({ type: "SET_CRITIC", payload: report });
                    },
                    onClarify: (suggestion) => {
                        dispatch({ type: "SET_CLARIFY", payload: suggestion });
                    },
                    onDone: (queryLogId) => {
                        dispatch({
                            type: "DONE",
                            payload: {
                                queryLogId,
                                latencyMs: timerRef.current?.getTotalLatency() ?? 0,
                            },
                        });
                    },
                    onError: (message) => {
                        dispatch({ type: "SET_ERROR", payload: message });
                    },
                },
                controller.signal
            );
        },
        [workspaceId, topK]
    );

    return { state, submit, cancel, reset };
}
