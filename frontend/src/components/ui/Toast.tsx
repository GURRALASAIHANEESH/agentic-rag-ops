"use client";

import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { X, CheckCircle, AlertTriangle, XCircle, Info } from "lucide-react";
import clsx from "clsx";

// ── Types ─────────────────────────────────────────────────────────────────────

export type ToastVariant = "success" | "error" | "warn" | "info";

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

// ── Context ───────────────────────────────────────────────────────────────────

interface ToastContextValue {
  toast: (item: Omit<ToastItem, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  warn: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);

  const addToast = React.useCallback((item: Omit<ToastItem, "id">) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...item, id }]);
  }, []);

  const removeToast = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback(
    (item: Omit<ToastItem, "id">) => addToast(item),
    [addToast]
  );
  const success = React.useCallback(
    (title: string, description?: string) =>
      addToast({ title, description, variant: "success" }),
    [addToast]
  );
  const error = React.useCallback(
    (title: string, description?: string) =>
      addToast({ title, description, variant: "error", duration: 6000 }),
    [addToast]
  );
  const warn = React.useCallback(
    (title: string, description?: string) =>
      addToast({ title, description, variant: "warn" }),
    [addToast]
  );
  const info = React.useCallback(
    (title: string, description?: string) =>
      addToast({ title, description, variant: "info" }),
    [addToast]
  );

  return (
    <ToastContext.Provider value={{ toast, success, error, warn, info }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}

        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            item={t}
            onClose={() => removeToast(t.id)}
          />
        ))}

        <ToastPrimitive.Viewport
          className={clsx(
            "fixed bottom-4 right-4 z-toast",
            "flex flex-col gap-2 w-[360px] max-w-[calc(100vw-2rem)]",
            "outline-none"
          )}
        />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

// ── Toast item ────────────────────────────────────────────────────────────────

const VARIANT_STYLES: Record<ToastVariant, { icon: React.ReactNode; bar: string }> = {
  success: {
    icon: <CheckCircle className="h-4 w-4 text-success shrink-0" aria-hidden="true" />,
    bar: "bg-success",
  },
  error: {
    icon: <XCircle className="h-4 w-4 text-danger shrink-0" aria-hidden="true" />,
    bar: "bg-danger",
  },
  warn: {
    icon: <AlertTriangle className="h-4 w-4 text-warn shrink-0" aria-hidden="true" />,
    bar: "bg-warn",
  },
  info: {
    icon: <Info className="h-4 w-4 text-accent shrink-0" aria-hidden="true" />,
    bar: "bg-accent",
  },
};

function ToastItem({
  item,
  onClose,
}: {
  item: ToastItem;
  onClose: () => void;
}) {
  const variant = item.variant ?? "info";
  const { icon, bar } = VARIANT_STYLES[variant];

  return (
    <ToastPrimitive.Root
      duration={item.duration ?? 4000}
      onOpenChange={(open) => !open && onClose()}
      className={clsx(
        "relative overflow-hidden",
        "flex items-start gap-3 p-3 pr-8 rounded-lg",
        "glass-panel shadow-lg border border-glass-border",
        "data-[state=open]:animate-fade-in",
        "data-[state=closed]:animate-fade-out",
        "data-[swipe=move]:translate-x-[--radix-toast-swipe-move-x]",
        "data-[swipe=end]:animate-fade-out"
      )}
    >
      {/* Colored left bar */}
      <span
        className={clsx("absolute left-0 top-0 bottom-0 w-0.5 rounded-l-lg", bar)}
        aria-hidden="true"
      />

      {icon}

      <div className="flex flex-col gap-0.5 min-w-0">
        <ToastPrimitive.Title className="text-sm font-medium text-text-primary">
          {item.title}
        </ToastPrimitive.Title>
        {item.description && (
          <ToastPrimitive.Description className="text-xs text-text-secondary">
            {item.description}
          </ToastPrimitive.Description>
        )}
      </div>

      <ToastPrimitive.Close
        onClick={onClose}
        className={clsx(
          "absolute top-2.5 right-2.5",
          "text-text-muted hover:text-text-primary",
          "transition-colors duration-fast",
          "focus-visible:outline-none focus-visible:text-text-primary"
        )}
        aria-label="Dismiss notification"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
