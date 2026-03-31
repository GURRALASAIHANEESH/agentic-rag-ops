"use client";
import React, { useState } from "react";
import { Plus, FolderOpen, Clock, Check, X, Loader2 } from "lucide-react";
import clsx from "clsx";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { Workspace } from "@/types";

export default function WorkspacePage() {
  const { workspaces, active, switchWorkspace, createWorkspace } = useWorkspace();
  const [showForm, setShowForm]   = useState(false);
  const [name, setName]           = useState("");
  const [desc, setDesc]           = useState("");
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createWorkspace(name.trim(), desc.trim());
      setName("");
      setDesc("");
      setShowForm(false);
    } catch (err: any) {
      setError(err?.message ?? "Failed to create workspace");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === "Escape") { setShowForm(false); setName(""); setDesc(""); }
  };

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Workspaces</h1>
          <p className="text-sm text-white/40 mt-0.5">
            {workspaces.length} workspace{workspaces.length !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => { setShowForm((v) => !v); setError(null); }}
          className={clsx(
            "btn-accent flex items-center gap-2 text-sm",
            showForm && "opacity-70"
          )}
        >
          {showForm ? <X size={14} /> : <Plus size={14} />}
          {showForm ? "Cancel" : "New Workspace"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate}
          className="glass-panel p-5 space-y-4 animate-slide-up">
          <p className="text-sm font-medium text-white/80">Create workspace</p>

          <div className="space-y-1">
            <label className="text-xs text-white/40 font-medium uppercase tracking-wider">Name *</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. Research Papers"
              className={clsx(
                "w-full px-3 py-2.5 rounded-lg text-sm text-white/90",
                "bg-white/[0.04] border border-white/[0.08]",
                "placeholder:text-white/25 outline-none",
                "focus:border-indigo-500/50 transition-colors"
              )}
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-white/40 font-medium uppercase tracking-wider">Description</label>
            <input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Optional description"
              className={clsx(
                "w-full px-3 py-2.5 rounded-lg text-sm text-white/90",
                "bg-white/[0.04] border border-white/[0.08]",
                "placeholder:text-white/25 outline-none",
                "focus:border-indigo-500/50 transition-colors"
              )}
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/[0.08] border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex gap-2 justify-end">
            <button type="button"
              onClick={() => { setShowForm(false); setName(""); setDesc(""); }}
              className="px-4 py-2 rounded-lg text-sm text-white/50 hover:text-white/70 hover:bg-white/[0.05] transition-all">
              Cancel
            </button>
            <button type="submit" disabled={!name.trim() || loading}
              className={clsx(
                "btn-accent flex items-center gap-2 text-sm",
                (!name.trim() || loading) && "opacity-50 pointer-events-none"
              )}>
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              {loading ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      )}

      {/* Workspace list */}
      {workspaces.length === 0 && !showForm ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4 text-center">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)" }}>
            <FolderOpen size={24} className="text-indigo-400" />
          </div>
          <p className="text-white/50 font-medium">No workspaces yet</p>
          <p className="text-sm text-white/25">Create one to start uploading documents</p>
        </div>
      ) : (
        <div className="space-y-2">
          {workspaces.map((ws: Workspace) => (
            <button key={ws.id} onClick={() => switchWorkspace(ws)}
              className={clsx(
                "w-full text-left p-4 rounded-xl border transition-all duration-150 group",
                active?.id === ws.id
                  ? "border-indigo-500/30 bg-indigo-500/[0.07]"
                  : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]"
              )}>
              <div className="flex items-center gap-3">
                <div className={clsx(
                  "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
                  active?.id === ws.id
                    ? "bg-indigo-500/20 text-indigo-400"
                    : "bg-white/[0.05] text-white/30 group-hover:text-white/50"
                )}>
                  <FolderOpen size={15} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white/85 truncate">{ws.name}</p>
                    {active?.id === ws.id && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-400">
                        Active
                      </span>
                    )}
                  </div>
                  {ws.description && (
                    <p className="text-xs text-white/30 truncate mt-0.5">{ws.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 text-[11px] text-white/25 flex-shrink-0">
                  <Clock size={11} />
                  {new Date(ws.created_at).toLocaleDateString()}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
