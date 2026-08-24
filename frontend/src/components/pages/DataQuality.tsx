"use client";

import { useState, useEffect } from "react";
import { Activity, CheckCircle, AlertCircle } from "lucide-react";
import { getDataQuality } from "@/lib/api/client";
import { cn, formatNumber } from "@/lib/utils";
import { EmptyState } from "@/components/common/EmptyState";

interface QualityCheck {
  column: string;
  null_count: number;
  completeness: number;
  status: string;
}

interface QualityTable {
  total_rows: number;
  checks: QualityCheck[];
  duplicate_count: number;
}

export function DataQualityPage() {
  const [report, setReport] = useState<{
    tables: Record<string, QualityTable>;
    overall_score: number;
    total_checks: number;
    passed_checks: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const dq = await getDataQuality();
        setReport(dq);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Data Quality</h1>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-48 bg-slate-200 rounded mb-2" />
              <div className="h-2 w-full bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Data Quality</h1>
        <EmptyState
          icon="🔍"
          title="No Data to Assess"
          description="Upload structured data to see quality metrics."
        />
      </div>
    );
  }

  const score = report.overall_score;
  const scoreClass =
    score >= 90 ? "quality-good" : score >= 70 ? "quality-ok" : "quality-bad";

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-lg font-bold text-slate-900">Data Quality</h1>

      {/* Score Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="kpi-card">
          <div className="kpi-label">Score</div>
          <div className="kpi-value">{score.toFixed(0)}/100</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Checks</div>
          <div className="kpi-value">
            {report.passed_checks}/{report.total_checks}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Tables</div>
          <div className="kpi-value">{Object.keys(report.tables).length}</div>
        </div>
      </div>

      {/* Quality Bar */}
      <div className="quality-bar">
        <div
          className={cn("quality-fill", scoreClass)}
          style={{ width: `${score}%` }}
        />
      </div>

      {/* Tables */}
      <div>
        <h2 className="section-title">Tables</h2>
        <div className="space-y-2">
          {Object.entries(report.tables).map(([tableName, tableData]) => (
            <div key={tableName} className="card">
              <button
                onClick={() =>
                  setExpandedTable(
                    expandedTable === tableName ? null : tableName
                  )
                }
                className="w-full flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <Activity className="w-4 h-4 text-brand-500" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900">
                      {tableName.charAt(0).toUpperCase() + tableName.slice(1)}
                    </div>
                    <div className="text-xs text-slate-400">
                      {formatNumber(tableData.total_rows)} rows ·{" "}
                      {tableData.checks.length} checks
                    </div>
                  </div>
                </div>
                <span className="text-xs text-slate-400">
                  {expandedTable === tableName ? "▲" : "▼"}
                </span>
              </button>

              {expandedTable === tableName && (
                <div className="mt-4 space-y-2 animate-fade-in">
                  {tableData.checks.map((check) => (
                    <div
                      key={check.column}
                      className="flex items-center gap-3 text-sm"
                    >
                      {check.status === "pass" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      ) : (
                        <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                      )}
                      <span className="font-medium text-slate-700">
                        {check.column}
                      </span>
                      <span className="text-slate-400">
                        — {check.completeness}% complete · {check.null_count}{" "}
                        nulls
                      </span>
                    </div>
                  ))}
                  {tableData.duplicate_count > 0 && (
                    <div className="flex items-center gap-2 text-sm text-amber-600 mt-2">
                      <AlertCircle className="w-3.5 h-3.5" />
                      {tableData.duplicate_count} duplicate keys
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
