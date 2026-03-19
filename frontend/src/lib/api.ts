// ─────────────────────────────────────────────────────────────
// Typed API client — all backend calls go through here.
// Never call fetch/axios directly from components.
// ─────────────────────────────────────────────────────────────

import axios, { AxiosInstance, AxiosError } from "axios";
import type {
    SignupResponse,
    TokenResponse,
    User,
    Workspace,
    Document,
    IngestionStatus,
    QueryHistoryItem,
    ProvenanceRecord,
    Citation,
} from "@/types";

const BASE_URL =
    typeof window === "undefined"
        ? (process.env.INTERNAL_API_URL ?? "http://localhost:8000")  // server-side SSR only
        : "";   // browser: ALWAYS use relative URLs through Next.js rewrite proxy

// ── Axios instance ────────────────────────────────────────────────────────────

const http: AxiosInstance = axios.create({
    baseURL: BASE_URL,
    headers: { "Content-Type": "application/json" },
    timeout: 30_000,
});

// ── Request interceptor: attach Bearer token ──────────────────────────────────

http.interceptors.request.use((config) => {
    if (typeof window !== "undefined") {
        const token = localStorage.getItem("access_token");
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
    }
    return config;
});

// ── Response interceptor: normalize errors ────────────────────────────────────

http.interceptors.response.use(
    (res) => res,
    async (error: AxiosError) => {
        const status = error.response?.status;

        // Auto-refresh on 401 — try once then redirect to login
        if (status === 401 && typeof window !== "undefined") {
            const refreshToken = localStorage.getItem("refresh_token");
            if (refreshToken) {
                try {
                    const { data } = await axios.post<TokenResponse>(
                        `${BASE_URL}/api/auth/refresh`,
                        { refresh_token: refreshToken }
                    );
                    localStorage.setItem("access_token", data.access_token);
                    localStorage.setItem("refresh_token", data.refresh_token);

                    // Retry the original request with new token
                    if (error.config) {
                        error.config.headers.Authorization = `Bearer ${data.access_token}`;
                        return http(error.config);
                    }
                } catch {
                    localStorage.clear();
                    window.location.href = "/login";
                }
            } else {
                window.location.href = "/login";
            }
        }

        return Promise.reject(error);
    }
);

// ── Error formatter ───────────────────────────────────────────────────────────

export function formatApiError(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
            return detail.map((d: { msg: string }) => d.msg).join(", ");
        }
        if (error.response?.status === 413) return "File is too large.";
        if (error.response?.status === 415) return "File type not supported.";
        if (error.response?.status === 429) return "Too many requests. Please wait.";
        if (error.response?.status === 500) return "Server error. Please try again.";
        return error.message;
    }
    return "An unexpected error occurred.";
}

// ── Auth API ──────────────────────────────────────────────────────────────────

export const authApi = {
    signup: (email: string, full_name: string, password: string) =>
        http.post<SignupResponse>("/api/auth/signup", { email, full_name, password }),

    login: (email: string, password: string) =>
        http.post<TokenResponse>("/api/auth/login", { email, password }),

    refresh: (refresh_token: string) =>
        http.post<TokenResponse>("/api/auth/refresh", { refresh_token }),

    me: () =>
        http.get<User>("/api/auth/me"),

    createWorkspace: (name: string, description?: string) =>
        http.post<Workspace>("/api/auth/workspaces", { name, description }),

    listWorkspaces: () =>
        http.get<Workspace[]>("/api/auth/workspaces"),
};

// ── Documents API ─────────────────────────────────────────────────────────────

export const documentsApi = {
    upload: (workspaceId: string, file: File) => {
        const form = new FormData();
        form.append("file", file);
        return http.post<Document>(`/api/documents/upload?workspace_id=${workspaceId}`, form, {
            headers: { "Content-Type": "multipart/form-data" },
            // Report upload progress for the progress bar
            onUploadProgress: undefined,
        });
    },

    uploadWithProgress: (
        workspaceId: string,
        file: File,
        onProgress: (percent: number) => void
    ) => {
        const form = new FormData();
        form.append("file", file);
        return http.post<Document>(
            `/api/documents/upload?workspace_id=${workspaceId}`,
            form,
            {
                headers: { "Content-Type": "multipart/form-data" },
                onUploadProgress: (event) => {
                    if (event.total) {
                        onProgress(Math.round((event.loaded / event.total) * 100));
                    }
                },
            }
        );
    },

    list: (workspaceId: string) =>
        http.get<{ documents: Document[]; total: number }>(
            `/api/documents/?workspace_id=${workspaceId}`
        ),

    getStatus: (documentId: string) =>
        http.get<IngestionStatus>(`/api/documents/${documentId}/status`),

    delete: (documentId: string) =>
        http.delete(`/api/documents/${documentId}`),
};

// ── Retrieval API ─────────────────────────────────────────────────────────────

export const retrievalApi = {
    search: (workspaceId: string, query: string, topK = 5) =>
        http.post<Citation[]>("/api/retrieval/search", null, {
            params: { workspace_id: workspaceId, query, top_k: topK },
        }),

    getHistory: (workspaceId: string, limit = 20) =>
        http.get<QueryHistoryItem[]>("/api/retrieval/history", {
            params: { workspace_id: workspaceId, limit },
        }),

    getProvenance: (queryLogId: string) =>
        http.get<ProvenanceRecord>(`/api/retrieval/history/${queryLogId}/provenance`),
};

// ── Query API (sync only — streaming handled by streaming.ts) ─────────────────

export const queryApi = {
    sync: (payload: {
        query: string;
        workspace_id: string;
        top_k?: number;
    }) =>
        http.post("/api/query/sync", { ...payload, stream: false }),
};
