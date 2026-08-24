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
  ChevronRight,
  Wifi,
  WifiOff,
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
  { label: "AI Analyst", href: "/", icon: <Brain className="w-4 h-4" />, group: "ai" },
  { label: "Overview", href: "/overview", icon: <BarChart3 className="w-4 h-4" />, group: "intelligence" },
  { label: "Insights", href: "/insights", icon: <Lightbulb className="w-4 h-4" />, group: "intelligence" },
  { label: "Investigations", href: "/investigations", icon: <Search className="w-4 h-4" />, group: "intelligence" },
  { label: "Recommendations", href: "/recommendations", icon: <Target className="w-4 h-4" />, group: "intelligence" },
  { label: "Data Center", href: "/data-center", icon: <FolderOpen className="w-4 h-4" />, group: "data" },
  { label: "Knowledge", href: "/knowledge", icon: <BookOpen className="w-4 h-4" />, group: "data" },
  { label: "Semantic Layer", href: "/semantic-layer", icon: <Layers className="w-4 h-4" />, group: "data" },
  { label: "Reports", href: "/reports", icon: <FileText className="w-4 h-4" />, group: "system" },
  { label: "Data Quality", href: "/data-quality", icon: <Activity className="w-4 h-4" />, group: "system" },
  { label: "Settings", href: "/settings", icon: <Settings className="w-4 h-4" />, group: "system" },
];

const GROUP_LABELS: Record<string, string> = {
  ai: null as unknown as string,
  intelligence: "INTELLIGENCE",
  data: "DATA",
  system: "SYSTEM",
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

  // Keyboard shortcut for search
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

  let lastGroup = "";

  return (
    <div className="h-full flex">
      {/* Desktop Sidebar */}
      <aside
        className={cn(
          "hidden lg:flex flex-col h-full bg-slate-900 border-r border-slate-800 transition-all duration-200",
          sidebarOpen ? "w-56" : "w-16"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 h-14 border-b border-slate-800 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
            <Brain className="w-4.5 h-4.5 text-white" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0">
              <div className="text-sm font-bold text-white truncate">QueryBridge</div>
              <div className="text-[0.6rem] text-slate-400 truncate">Intelligence</div>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 scrollbar-thin">
          {NAV_ITEMS.map((item) => {
            const groupLabel = item.group ? GROUP_LABELS[item.group] : undefined;
            const showGroupLabel = item.group && item.group !== "ai" && groupLabel && lastGroup !== item.group;
            if (showGroupLabel && item.group) lastGroup = item.group;
            const active = isActive(item.href);

            return (
              <div key={item.href}>
                {showGroupLabel && sidebarOpen && groupLabel && (
                  <div className="px-3 pt-4 pb-1.5 text-[0.6rem] font-semibold text-slate-500 tracking-wider">
                    {groupLabel}
                  </div>
                )}
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                    active
                      ? "bg-brand-600/15 text-brand-300 border border-brand-500/20"
                      : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent",
                    !sidebarOpen && "justify-center"
                  )}
                  title={!sidebarOpen ? item.label : undefined}
                >
                  <span className="shrink-0">{item.icon}</span>
                  {sidebarOpen && <span className="truncate">{item.label}</span>}
                </Link>
              </div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-slate-800">
          {sidebarOpen ? (
            <div className="flex items-center gap-2 text-xs">
              {apiOnline !== null ? (
                apiOnline ? (
                  <>
                    <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-400 font-medium">Online</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-3.5 h-3.5 text-rose-400" />
                    <span className="text-rose-400 font-medium">Offline</span>
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

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={closeMobile}
          />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-slate-900 shadow-xl z-10 flex flex-col">
            <div className="flex items-center justify-between px-4 h-14 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
                  <Brain className="w-4.5 h-4.5 text-white" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white">QueryBridge</div>
                  <div className="text-[0.6rem] text-slate-400">Intelligence</div>
                </div>
              </div>
              <button onClick={closeMobile} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-3 px-2">
              {NAV_ITEMS.map((item) => {
                const groupLabel = item.group ? GROUP_LABELS[item.group] : undefined;
                const showGroupLabel = item.group && item.group !== "ai" && groupLabel && lastGroup !== item.group;
                if (showGroupLabel && item.group) lastGroup = item.group;
                const active = isActive(item.href);

                return (
                  <div key={item.href}>
                    {showGroupLabel && groupLabel && (
                      <div className="px-3 pt-4 pb-1.5 text-[0.6rem] font-semibold text-slate-500 tracking-wider">
                        {groupLabel}
                      </div>
                    )}
                    <Link
                      href={item.href}
                      onClick={closeMobile}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                        active
                          ? "bg-brand-600/15 text-brand-300 border border-brand-500/20"
                          : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
                      )}
                    >
                      <span className="shrink-0">{item.icon}</span>
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </div>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 h-full">
        {/* Header */}
        <header className="h-14 border-b border-slate-200 bg-white flex items-center gap-4 px-4 lg:px-6 shrink-0">
          <button
            className="lg:hidden text-slate-500 hover:text-slate-700"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="w-5 h-5" />
          </button>

          <button
            className="hidden lg:flex text-slate-400 hover:text-slate-600"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            <ChevronRight
              className={cn(
                "w-4 h-4 transition-transform",
                sidebarOpen ? "rotate-180" : ""
              )}
            />
          </button>

          <div className="flex-1" />

          {/* Search Trigger */}
          <button
            onClick={() => setSearchOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-400 hover:text-slate-600 hover:border-slate-300 transition-colors"
          >
            <Search className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Search...</span>
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
