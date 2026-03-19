"use client";

export { useWorkspace } from "@/contexts/WorkspaceContext";

import { useCallback, useState, useEffect } from "react";
import { useWorkspace as useWorkspaceContext } from "@/contexts/WorkspaceContext";
import { documentsApi, retrievalApi } from "@/lib/api";
import type { Document, QueryHistoryItem } from "@/types";

// ── useWorkspaceDocuments ─────────────────────────────────────────────────────

interface UseWorkspaceDocumentsReturn {
    documents: Document[];
    isLoading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    deleteDocument: (id: string) => Promise<void>;
}

export function useWorkspaceDocuments(): UseWorkspaceDocumentsReturn {
    const { active } = useWorkspaceContext();
    const [documents, setDocuments] = useState<Document[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        if (!active) return;
        setIsLoading(true);
        setError(null);
        try {
            const { data } = await documentsApi.list(active.id);
            setDocuments(data.documents);
        } catch {
            setError("Failed to load documents.");
        } finally {
            setIsLoading(false);
        }
    }, [active]);

    useEffect(() => { void refresh(); }, [refresh]);

    const deleteDocument = useCallback(async (id: string) => {
        await documentsApi.delete(id);
        setDocuments((prev) => prev.filter((d) => d.id !== id));
    }, []);

    return { documents, isLoading, error, refresh, deleteDocument };
}

// ── useQueryHistory ───────────────────────────────────────────────────────────

interface UseQueryHistoryReturn {
    history: QueryHistoryItem[];
    isLoading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
}

export function useQueryHistory(limit = 20): UseQueryHistoryReturn {
    const { active } = useWorkspaceContext();
    const [history, setHistory] = useState<QueryHistoryItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        if (!active) return;
        setIsLoading(true);
        setError(null);
        try {
            const { data } = await retrievalApi.getHistory(active.id, limit);
            setHistory(data);
        } catch {
            setError("Failed to load query history.");
        } finally {
            setIsLoading(false);
        }
    }, [active, limit]);

    useEffect(() => { void refresh(); }, [refresh]);

    return { history, isLoading, error, refresh };
}

// ── useDocumentStatus ─────────────────────────────────────────────────────────

interface UseDocumentStatusReturn {
    status: string | null;
    chunksCreated: number | null;
    message: string | null;
    isPolling: boolean;
}

export function useDocumentStatus(documentId: string | null): UseDocumentStatusReturn {
    const [status, setStatus] = useState<string | null>(null);
    const [chunksCreated, setChunksCreated] = useState<number | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [isPolling, setIsPolling] = useState(false);

    useEffect(() => {
        if (!documentId) return;

        const TERMINAL = new Set(["ready", "failed"]);
        const MAX_POLLS = 30; // 60 seconds max
        let pollCount = 0;
        let intervalId: ReturnType<typeof setInterval>;

        const poll = async () => {
            pollCount++;
            if (pollCount >= MAX_POLLS) {
                clearInterval(intervalId);
                setIsPolling(false);
                setStatus("error");
                setMessage("Ingestion timed out. Check backend logs.");
                return;
            }

            try {
                const { data } = await documentsApi.getStatus(documentId);
                setStatus(data.status);
                setChunksCreated(data.chunks_created);
                setMessage(data.message);
                if (TERMINAL.has(data.status)) {
                    clearInterval(intervalId);
                    setIsPolling(false);
                }
            } catch {
                clearInterval(intervalId);
                setIsPolling(false);
                setStatus("failed");
                setMessage("Could not retrieve document status.");
            }
        };

        setIsPolling(true);
        void poll();
        intervalId = setInterval(poll, 2000);

        return () => {
            clearInterval(intervalId);
            setIsPolling(false);
        };
    }, [documentId]);

    return { status, chunksCreated, message, isPolling };
}
