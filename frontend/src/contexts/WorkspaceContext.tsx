"use client";

import React, {
    createContext,
    useContext,
    useEffect,
    useReducer,
    useCallback,
} from "react";
import type { Workspace } from "@/types";
import { authApi } from "@/lib/api";
import { storeWorkspaceId, getStoredWorkspaceId } from "@/lib/auth";
import { useAuth } from "@/contexts/AuthContext";

// ── State ─────────────────────────────────────────────────────────────────────

interface WorkspaceState {
    workspaces: Workspace[];
    active: Workspace | null;
    isLoading: boolean;
    error: string | null;
}

type WorkspaceAction =
    | { type: "SET_WORKSPACES"; payload: Workspace[] }
    | { type: "SET_ACTIVE"; payload: Workspace }
    | { type: "ADD_WORKSPACE"; payload: Workspace }
    | { type: "SET_LOADING"; payload: boolean }
    | { type: "SET_ERROR"; payload: string | null }
    | { type: "CLEAR" };

function workspaceReducer(
    state: WorkspaceState,
    action: WorkspaceAction
): WorkspaceState {
    switch (action.type) {
        case "SET_WORKSPACES":
            return { ...state, workspaces: action.payload, isLoading: false };
        case "SET_ACTIVE":
            return { ...state, active: action.payload };
        case "ADD_WORKSPACE":
            return {
                ...state,
                workspaces: [...state.workspaces, action.payload],
                active: action.payload,
            };
        case "SET_LOADING":
            return { ...state, isLoading: action.payload };
        case "SET_ERROR":
            return { ...state, error: action.payload, isLoading: false };
        case "CLEAR":
            return { workspaces: [], active: null, isLoading: false, error: null };
        default:
            return state;
    }
}

// ── Context ───────────────────────────────────────────────────────────────────

interface WorkspaceContextValue extends WorkspaceState {
    switchWorkspace: (workspace: Workspace) => void;
    createWorkspace: (name: string, description?: string) => Promise<Workspace>;
    refreshWorkspaces: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
    const { isAuthenticated } = useAuth();
    const [state, dispatch] = useReducer(workspaceReducer, {
        workspaces: [],
        active: null,
        isLoading: false,
        error: null,
    });

    const refreshWorkspaces = useCallback(async () => {
        dispatch({ type: "SET_LOADING", payload: true });
        try {
            const { data } = await authApi.listWorkspaces();
            dispatch({ type: "SET_WORKSPACES", payload: data });

            const storedId = getStoredWorkspaceId();
            const restored = data.find((w) => w.id === storedId) ?? data[0] ?? null;
            if (restored) {
                dispatch({ type: "SET_ACTIVE", payload: restored });
            }
        } catch {
            dispatch({ type: "SET_ERROR", payload: "Failed to load workspaces." });
        }
    }, []);

    useEffect(() => {
        if (isAuthenticated) {
            void refreshWorkspaces();
        } else {
            dispatch({ type: "CLEAR" });
        }
    }, [isAuthenticated, refreshWorkspaces]);

    const switchWorkspace = useCallback((workspace: Workspace) => {
        dispatch({ type: "SET_ACTIVE", payload: workspace });
        storeWorkspaceId(workspace.id);
    }, []);

    const createWorkspace = useCallback(
        async (name: string, description?: string): Promise<Workspace> => {
            const { data } = await authApi.createWorkspace(name, description);
            dispatch({ type: "ADD_WORKSPACE", payload: data });
            storeWorkspaceId(data.id);
            return data;
        },
        []
    );

    return (
        <WorkspaceContext.Provider
            value={{ ...state, switchWorkspace, createWorkspace, refreshWorkspaces }}
        >
            {children}
        </WorkspaceContext.Provider>
    );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useWorkspace(): WorkspaceContextValue {
    const ctx = useContext(WorkspaceContext);
    if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
    return ctx;
}
