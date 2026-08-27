import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number | string | null | undefined): string {
  if (value == null) return "N/A";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "N/A";
  if (Math.abs(num) >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
  if (Math.abs(num) >= 1e3) return `$${(num / 1e3).toFixed(1)}K`;
  return `$${num.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function formatNumber(value: number | string | null | undefined): string {
  if (value == null) return "N/A";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "N/A";
  return num.toLocaleString("en-US");
}

export function formatPercent(
  value: number | string | null | undefined
): string {
  if (value == null) return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  const sign = num >= 0 ? "+" : "";
  return `${sign}${num.toFixed(1)}%`;
}

export function formatRoas(value: number | string | null | undefined): string {
  if (value == null) return "N/A";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "N/A";
  return `${num.toFixed(2)}x`;
}

export function getQueryTypeVariant(queryType: string): string {
  const variants: Record<string, string> = {
    knowledge: "bg-brand-50 text-brand-700 border border-brand-200",
    analytical: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    hybrid: "bg-violet-50 text-violet-700 border border-violet-200",
    diagnostic: "bg-rose-50 text-rose-700 border border-rose-200",
    unanswerable: "bg-slate-100 text-slate-600 border border-slate-200",
    ambiguous: "bg-slate-100 text-slate-600 border border-slate-200",
  };
  return variants[queryType] || variants.ambiguous;
}

export function getInsightIcon(type: string): string {
  const icons: Record<string, string> = {
    warning: "⚠️",
    success: "✅",
    info: "💡",
  };
  return icons[type] || "💡";
}

export function getInsightBorder(type: string): string {
  const borders: Record<string, string> = {
    warning: "border-l-amber-500",
    success: "border-l-emerald-500",
    info: "border-l-brand-500",
  };
  return borders[type] || borders.info;
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    healthy: "text-emerald-600",
    ready: "text-emerald-600",
    indexed: "text-emerald-600",
    pass: "text-emerald-600",
    warning: "text-amber-600",
    warn: "text-amber-600",
    error: "text-rose-600",
    empty: "text-slate-400",
    not_configured: "text-amber-600",
  };
  return colors[status] || "text-slate-500";
}

export function getStatusBg(status: string): string {
  const colors: Record<string, string> = {
    healthy: "bg-emerald-50 text-emerald-700 border-emerald-200",
    ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
    indexed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warning: "bg-amber-50 text-amber-700 border-amber-200",
    warn: "bg-amber-50 text-amber-700 border-amber-200",
    error: "bg-rose-50 text-rose-700 border-rose-200",
    empty: "bg-slate-50 text-slate-500 border-slate-200",
  };
  return colors[status] || "bg-slate-50 text-slate-500 border-slate-200";
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "...";
}

export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export const RECHARTS_COLORS = [
  "#4f46e5",
  "#059669",
  "#d97706",
  "#e11d48",
  "#7c3aed",
  "#0891b2",
  "#c026d3",
  "#65a30d",
];

export const CHART_BASE_LAYOUT = {
  height: 280,
  margin: { l: 10, r: 10, t: 30, b: 10 },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { family: "Inter, sans-serif", size: 12, color: "#475569" },
};
