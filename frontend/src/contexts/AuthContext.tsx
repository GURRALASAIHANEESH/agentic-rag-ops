"use client";

import React, {
    createContext,
    useContext,
    useEffect,
    useReducer,
    useCallback,
} from "react";
import type { User } from "@/types";
import {
    getStoredUser,
    storeUser,
    storeTokens,
    clearTokens,
    isAuthenticated,
} from "@/lib/auth";
import { authApi } from "@/lib/api";

// ── State ─────────────────────────────────────────────────────────────────────

interface AuthState {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
}

type AuthAction =
    | { type: "SET_USER"; payload: User }
    | { type: "CLEAR" }
    | { type: "SET_LOADING"; payload: boolean };

function authReducer(state: AuthState, action: AuthAction): AuthState {
    switch (action.type) {
        case "SET_USER":
            return { user: action.payload, isAuthenticated: true, isLoading: false };
        case "CLEAR":
            return { user: null, isAuthenticated: false, isLoading: false };
        case "SET_LOADING":
            return { ...state, isLoading: action.payload };
        default:
            return state;
    }
}

// ── Context ───────────────────────────────────────────────────────────────────

interface AuthContextValue extends AuthState {
    login: (email: string, password: string) => Promise<void>;
    signup: (email: string, fullName: string, password: string) => Promise<void>;
    logout: () => void;
    refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [state, dispatch] = useReducer(authReducer, {
        user: null,
        isAuthenticated: false,
        isLoading: true,
    });

    // Rehydrate from localStorage on mount
    useEffect(() => {
        const stored = getStoredUser();
        if (stored && isAuthenticated()) {
            dispatch({ type: "SET_USER", payload: stored });
        } else {
            dispatch({ type: "SET_LOADING", payload: false });
        }
    }, []);

    const refreshUser = useCallback(async () => {
        try {
            const { data } = await authApi.me();
            storeUser(data);
            dispatch({ type: "SET_USER", payload: data });
        } catch {
            dispatch({ type: "CLEAR" });
        }
    }, []);

    const login = useCallback(async (email: string, password: string) => {
        dispatch({ type: "SET_LOADING", payload: true });
        const { data: tokens } = await authApi.login(email, password);
        storeTokens(tokens);
        const { data: user } = await authApi.me();
        storeUser(user);
        dispatch({ type: "SET_USER", payload: user });
    }, []);

    const signup = useCallback(
        async (email: string, fullName: string, password: string) => {
            dispatch({ type: "SET_LOADING", payload: true });
            const { data } = await authApi.signup(email, fullName, password);
            storeTokens(data.tokens);
            storeUser(data.user);
            dispatch({ type: "SET_USER", payload: data.user });
        },
        []
    );

    const logout = useCallback(() => {
        clearTokens();
        dispatch({ type: "CLEAR" });
        window.location.href = "/login";
    }, []);

    return (
        <AuthContext.Provider
            value={{ ...state, login, signup, logout, refreshUser }}
        >
            {children}
        </AuthContext.Provider>
    );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
