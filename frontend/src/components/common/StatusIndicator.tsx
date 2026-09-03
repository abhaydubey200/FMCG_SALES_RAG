"use client";

import { cn } from "@/lib/utils";
import { CheckCircle, AlertTriangle, XCircle, MinusCircle, Loader2 } from "lucide-react";

type StatusType = "healthy" | "warning" | "error" | "idle" | "loading" | "unknown";

interface StatusIndicatorProps {
  status: StatusType;
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const STATUS_CONFIG: Record<StatusType, {
  icon: React.ReactNode;
  color: string;
  bg: string;
  label: string;
}> = {
  healthy: {
    icon: <CheckCircle className="w-4 h-4" />,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    label: "Healthy",
  },
  warning: {
    icon: <AlertTriangle className="w-4 h-4" />,
    color: "text-amber-600",
    bg: "bg-amber-50",
    label: "Warning",
  },
  error: {
    icon: <XCircle className="w-4 h-4" />,
    color: "text-rose-600",
    bg: "bg-rose-50",
    label: "Error",
  },
  idle: {
    icon: <MinusCircle className="w-4 h-4" />,
    color: "text-slate-400",
    bg: "bg-slate-50",
    label: "Idle",
  },
  loading: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    color: "text-indigo-500",
    bg: "bg-indigo-50",
    label: "Checking...",
  },
  unknown: {
    icon: <MinusCircle className="w-4 h-4" />,
    color: "text-slate-400",
    bg: "bg-slate-50",
    label: "Unknown",
  },
};

export function StatusIndicator({ status, label, size = "md", className }: StatusIndicatorProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.unknown;
  const displayLabel = label || config.label;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium",
        size === "sm" && "px-2 py-0.5 text-xs",
        size === "md" && "px-2.5 py-1 text-xs",
        size === "lg" && "px-3 py-1.5 text-sm",
        config.bg,
        config.color,
        className
      )}
    >
      {config.icon}
      {displayLabel}
    </div>
  );
}

interface DotStatusProps {
  status: StatusType;
  size?: "sm" | "md";
  className?: string;
}

export function DotStatus({ status, size = "sm", className }: DotStatusProps) {
  const colorMap: Record<StatusType, string> = {
    healthy: "bg-emerald-500",
    warning: "bg-amber-500",
    error: "bg-rose-500",
    idle: "bg-slate-300",
    loading: "bg-indigo-500 animate-pulse",
    unknown: "bg-slate-300",
  };

  return (
    <span
      className={cn(
        "inline-block rounded-full",
        size === "sm" && "w-1.5 h-1.5",
        size === "md" && "w-2 h-2",
        colorMap[status] || colorMap.unknown,
        className
      )}
    />
  );
}
