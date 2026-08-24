import { cn, formatPercent } from "@/lib/utils";

interface KPICardProps {
  label: string;
  value: string;
  delta?: number | null;
  className?: string;
}

export function KPICard({ label, value, delta, className }: KPICardProps) {
  return (
    <div className={cn("kpi-card", className)}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {delta != null && (
        <div
          className={cn(
            "kpi-delta",
            delta >= 0 ? "text-emerald-600" : "text-rose-600"
          )}
        >
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
        </div>
      )}
      {delta == null && <div className="kpi-delta text-slate-400">—</div>}
    </div>
  );
}
