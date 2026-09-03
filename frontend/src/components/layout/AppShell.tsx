"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Brain,
  BarChart3,
  Lightbulb,
  Search,
  Target,
  FolderOpen,
  BookOpen,
  Layers,
  FileText,
  Database,
  Activity,
  Settings,
  Menu,
  X,
  ChevronLeft,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { healthCheck } from "@/lib/api/client";
import { SearchPalette } from "@/components/common/SearchPalette";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  group?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "AI Analyst", href: "/", icon: <Brain className="w-4 h-4" />, group: "intelligence" },
  { label: "Overview", href: "/overview", icon: <BarChart3 className="w-4 h-4" />, group: "intelligence" },
  { label: "Insights", href: "/insights", icon: <Lightbulb className="w-4 h-4" />, group: "intelligence" },
  { label: "Investigations", href: "/investigations", icon: <Search className="w-4 h-4" />, group: "intelligence" },
  { label: "Recommendations", href: "/recommendations", icon: <Target className="w-4 h-4" />, group: "intelligence" },
  { label: "Data Center", href: "/data-center", icon: <FolderOpen className="w-4 h-4" />, group: "data" },
  { label: "Knowledge", href: "/knowledge", icon: <BookOpen className="w-4 h-4" />, group: "data" },
  { label: "Semantic Layer", href: "/semantic-layer", icon: <Layers className="w-4 h-4" />, group: "data" },
  { label: "Reports", href: "/reports", icon: <FileText className="w-4 h-4" />, group: "platform" },
  { label: "Data Quality", href: "/data-quality", icon: <Activity className="w-4 h-4" />, group: "platform" },
  { label: "Settings", href: "/settings", icon: <Settings className="w-4 h-4" />, group: "platform" },
];

const GROUP_META: Record<string, { label: string; defaultOpen?: boolean }> = {
  intelligence: { label: "Intelligence" },
  data: { label: "Data" },
  platform: { label: "Platform" },
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        await healthCheck();
        setApiOnline(true);
      } catch {
        setApiOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  // Group items
  const grouped: Record<string, NavItem[]> = {};
  for (const item of NAV_ITEMS) {
    const g = item.group || "other";
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push(item);
  }

  const renderNavItems = (isMobile = false) => {
    let lastGroup = "";
    return NAV_ITEMS.map((item) => {
      const groupKey = item.group || "other";
      const showGroup = groupKey !== lastGroup;
      if (showGroup) lastGroup = groupKey;
      const active = isActive(item.href);
      const meta = GROUP_META[groupKey];

      return (
        <div key={item.href}>
          {showGroup && meta && sidebarOpen && (
            <div className="px-3 pt-5 pb-1.5 text-[0.6rem] font-semibold text-slate-500 uppercase tracking-wider">
              {meta.label}
            </div>
          )}
          {showGroup && meta && !sidebarOpen && (
            <div className="my-2 mx-auto w-5 h-px bg-slate-700" />
          )}
          <Link
            href={item.href}
            onClick={isMobile ? closeMobile : undefined}
            className={cn(
              "flex items-center gap-2.5 mx-2 px-3 py-2 rounded-lg text-[0.8125rem] transition-all duration-100",
              active
                ? "bg-brand-500/15 text-brand-300 font-medium"
                : "text-slate-400 hover:text-slate-200 hover:bg-white/5",
              !sidebarOpen && "justify-center mx-0 px-0"
            )}
            title={!sidebarOpen ? item.label : undefined}
          >
            <span className="shrink-0">{item.icon}</span>
            {sidebarOpen && <span className="truncate">{item.label}</span>}
          </Link>
        </div>
      );
    });
  };

  return (
    <div className="h-full flex">
      {/* ── Desktop Sidebar ── */}
      <aside
        className={cn(
          "hidden lg:flex flex-col h-full bg-slate-900 transition-all duration-200 shrink-0",
          sidebarOpen ? "w-56" : "w-16"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-3.5 h-14 border-b border-slate-800/80 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shrink-0 shadow-sm">
            <Zap className="w-4 h-4 text-white" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0">
              <div className="text-sm font-bold text-white tracking-tight">QueryBridge</div>
              <div className="text-[0.6rem] text-slate-500">Intelligence Platform</div>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-1 scrollbar-thin">
          {renderNavItems()}
        </nav>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-slate-800/80">
          {sidebarOpen ? (
            <div className="flex items-center gap-2 text-xs">
              {apiOnline !== null ? (
                apiOnline ? (
                  <>
                    <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-400 font-medium">Connected</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-3.5 h-3.5 text-rose-400" />
                    <span className="text-rose-400 font-medium">Disconnected</span>
                  </>
                )
              ) : (
                <span className="text-slate-500">Checking...</span>
              )}
            </div>
          ) : (
            <div className="flex justify-center">
              {apiOnline !== null ? (
                <div
                  className={cn(
                    "w-2 h-2 rounded-full",
                    apiOnline ? "bg-emerald-400" : "bg-rose-400"
                  )}
                />
              ) : (
                <div className="w-2 h-2 rounded-full bg-slate-600 animate-pulse" />
              )}
            </div>
          )}
        </div>
      </aside>

      {/* ── Mobile Sidebar Overlay ── */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={closeMobile} />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-slate-900 shadow-2xl z-10 flex flex-col">
            <div className="flex items-center justify-between px-4 h-14 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
                  <Zap className="w-4 h-4 text-white" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white tracking-tight">QueryBridge</div>
                  <div className="text-[0.6rem] text-slate-500">Intelligence Platform</div>
                </div>
              </div>
              <button onClick={closeMobile} className="text-slate-400 hover:text-white p-1">
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-2 px-1">
              {renderNavItems(true)}
            </nav>
            <div className="px-4 py-3 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs">
                {apiOnline !== null ? (
                  apiOnline ? (
                    <>
                      <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 font-medium">Connected</span>
                    </>
                  ) : (
                    <>
                      <WifiOff className="w-3.5 h-3.5 text-rose-400" />
                      <span className="text-rose-400 font-medium">Disconnected</span>
                    </>
                  )
                ) : (
                  <span className="text-slate-500">Checking...</span>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}

      {/* ── Main Content ── */}
      <div className="flex-1 flex flex-col min-w-0 h-full">
        {/* Header */}
        <header className="h-14 border-b border-slate-200/80 bg-white flex items-center gap-4 px-4 lg:px-5 shrink-0">
          <button
            className="lg:hidden text-slate-500 hover:text-slate-700"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="w-5 h-5" />
          </button>

          <button
            className="hidden lg:flex text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100 transition-colors"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            <ChevronLeft
              className={cn(
                "w-4 h-4 transition-transform duration-200",
                sidebarOpen ? "" : "rotate-180"
              )}
            />
          </button>

          <div className="flex-1" />

          {/* Search Trigger */}
          <button
            onClick={() => setSearchOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-400 hover:text-slate-600 hover:border-slate-300 transition-colors bg-slate-50/50"
          >
            <Search className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[0.6rem] font-mono bg-slate-100 text-slate-500 rounded border border-slate-200">
              ⌘K
            </kbd>
          </button>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* Search Palette */}
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
