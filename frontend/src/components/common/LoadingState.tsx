"use client";

import { cn } from "@/lib/utils";

interface LoadingStateProps {
  lines?: number;
  layout?: "list" | "grid" | "detail";
  className?: string;
}

export function LoadingState({ lines = 4, layout = "list", className }: LoadingStateProps) {
  if (layout === "grid") {
    return (
      <div className={cn("grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3", className)}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="card animate-pulse">
            <div className="h-3 w-20 bg-slate-100 rounded mb-3" />
            <div className="h-6 w-28 bg-slate-200 rounded mb-2" />
            <div className="h-2 w-16 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (layout === "detail") {
    return (
      <div className={cn("space-y-4", className)}>
        <div className="card animate-pulse">
          <div className="h-5 w-48 bg-slate-200 rounded mb-3" />
          <div className="h-3 w-full bg-slate-100 rounded mb-2" />
          <div className="h-3 w-3/4 bg-slate-100 rounded mb-2" />
          <div className="h-3 w-1/2 bg-slate-100 rounded" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-3 w-16 bg-slate-100 rounded mb-2" />
              <div className="h-7 w-24 bg-slate-200 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // list layout (default)
  return (
    <div className={cn("space-y-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="card animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-slate-100" />
            <div className="flex-1">
              <div className="h-3.5 w-40 bg-slate-200 rounded mb-2" />
              <div className="h-2.5 w-24 bg-slate-100 rounded" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function KPISkeleton() {
  return (
    <div className="kpi-card animate-pulse">
      <div className="h-2.5 w-14 bg-slate-100 rounded mb-2" />
      <div className="h-7 w-24 bg-slate-200 rounded mb-1" />
      <div className="h-2.5 w-10 bg-slate-100 rounded" />
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="card animate-pulse">
      <div className="h-4 w-40 bg-slate-200 rounded mb-4" />
      <div className="bg-slate-50 rounded-lg" style={{ height }} />
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="card animate-pulse">
      <div className="h-4 w-32 bg-slate-200 rounded mb-4" />
      <div className="space-y-2">
        <div className="h-8 bg-slate-100 rounded" />
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <div className="h-4 flex-1 bg-slate-50 rounded" />
            <div className="h-4 w-20 bg-slate-50 rounded" />
            <div className="h-4 w-20 bg-slate-50 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}
