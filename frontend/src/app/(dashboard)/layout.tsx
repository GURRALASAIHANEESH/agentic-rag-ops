"use client";
import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  MessageSquare, Upload, FolderOpen, LayoutDashboard,
  LogOut, Cpu, ChevronRight,
} from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

const NAV_ITEMS = [
  { href: "/",         icon: LayoutDashboard, label: "Dashboard" },
  { href: "/query",    icon: MessageSquare,   label: "Query" },
  { href: "/upload",   icon: Upload,          label: "Upload" },
  { href: "/workspace",icon: FolderOpen,      label: "Workspaces" },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading } = useAuth();
  const { active } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [user, isLoading, router]);

  if (isLoading || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <span className="text-sm text-white/40">Loading...</span>
        </div>
      </div>
    );
  }

  const initials = user.email?.slice(0, 2).toUpperCase() ?? "U";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ── */}
      <aside className="w-56 flex-shrink-0 flex flex-col border-r border-white/[0.06]"
        style={{ background: "rgba(8,13,26,0.95)" }}>

        {/* Logo */}
        <div className="flex items-center gap-2.5 px-4 py-5 border-b border-white/[0.06]">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center animate-pulse-glow"
            style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}>
            <Cpu size={14} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white leading-none">RAG Ops</p>
            <p className="text-[10px] text-white/30 mt-0.5">Intelligence Platform</p>
          </div>
        </div>

        {/* Workspace badge */}
        {active && (
          <div className="mx-3 mt-3 px-3 py-2 rounded-lg border border-indigo-500/20"
            style={{ background: "rgba(99,102,241,0.06)" }}>
            <p className="text-[10px] text-indigo-400/70 font-medium uppercase tracking-wider">Workspace</p>
            <p className="text-xs text-white/80 font-medium truncate-1 mt-0.5">{active.name}</p>
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-2 mt-4 space-y-0.5">
          {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
            const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={clsx("nav-item group", isActive && "active")}>
                <Icon size={16} className="flex-shrink-0" />
                <span className="flex-1">{label}</span>
                {isActive && <ChevronRight size={12} className="opacity-50" />}
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-white/[0.06]">
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-white/[0.04] transition-colors group">
            <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold text-white"
              style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}>
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-white/80 font-medium truncate-1">{user.email}</p>
              <p className="text-[10px] text-white/30">Free tier</p>
            </div>
            <button onClick={logout}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-white/[0.08]"
              title="Sign out">
              <LogOut size={13} className="text-white/50" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
