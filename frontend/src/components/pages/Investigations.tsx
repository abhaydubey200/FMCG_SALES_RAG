"use client";

import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { Search, Loader2 } from "lucide-react";
import { investigateMetric, getDataStatus } from "@/lib/api/client";
import { cn, formatCurrency, formatNumber } from "@/lib/utils";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { ChartSkeleton } from "@/components/common/Skeleton";

const METRICS = ["revenue", "roas", "margin", "customers", "campaigns"];

export function InvestigationsPage() {
  const [selectedMetric, setSelectedMetric] = useState("revenue");
  const [investigation, setInvestigation] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasData, setHasData] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    const check = async () => {
      try {
        const status = await getDataStatus();
        setHasData(status.has_data);
      } catch {
        // ignore
      } finally {
        setInitialLoading(false);
      }
    };
    check();
  }, []);

  const handleInvestigate = async () => {
    setLoading(true);
    try {
      const result = await investigateMetric(selectedMetric);
      setInvestigation(result as unknown as Record<string, unknown>);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Investigation Workspace</h1>
        <ChartSkeleton />
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Investigation Workspace</h1>
        <EmptyState
          icon="🔬"
          title="No Data to Investigate"
          description="Upload structured data to enable drill-down investigations."
        />
      </div>
    );
  }

  const breakdowns = (investigation?.breakdowns as Record<string, Array<Record<string, unknown>>>) || {};
  const trend = (investigation?.trend as Array<Record<string, unknown>>) || [];
  const topEntities = (investigation?.top_entities as Array<Record<string, unknown>>) || [];

  const renderBreakdownChart = (key: string, data: Array<Record<string, unknown>>) => {
    if (!data || data.length === 0) return null;
    const numCols = Object.keys(data[0]).filter(
      (k) => typeof data[0][k] === "number"
    );
    const catCol = Object.keys(data[0]).find(
      (k) => typeof data[0][k] !== "number"
    );

    if (!catCol || numCols.length === 0) return null;

    return (
      <div key={key}>
        <h3 className="section-title capitalize">
          {key.replace("by_", "").replace("_", " ")}
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey={catCol}
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                  }}
                />
                <Bar dataKey={numCols[0]} fill="#4f46e5" radius={[4, 4, 0, 0]} barSize={32} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card overflow-hidden">
            <DataTable
              columns={Object.keys(data[0]).map((k) => ({
                key: k,
                header: k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
                sortable: true,
                align: typeof data[0][k] === "number" ? "right" : "left",
              }))}
              data={data}
              pageSize={8}
            />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-lg font-bold text-slate-900">Investigation Workspace</h1>

      {/* Metric Selector */}
      <div className="flex items-center gap-3">
        <select
          value={selectedMetric}
          onChange={(e) => setSelectedMetric(e.target.value)}
          className="px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {METRICS.map((m) => (
            <option key={m} value={m}>
              {m.charAt(0).toUpperCase() + m.slice(1)}
            </option>
          ))}
        </select>
        <button
          onClick={handleInvestigate}
          disabled={loading}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
            loading
              ? "bg-slate-100 text-slate-400 cursor-not-allowed"
              : "bg-brand-600 text-white hover:bg-brand-700"
          )}
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Investigating...
            </>
          ) : (
            <>
              <Search className="w-4 h-4" />
              Start Investigation
            </>
          )}
        </button>
      </div>

      {/* Results */}
      {investigation ? (
        <div className="space-y-6">
          {/* Breakdowns */}
          {Object.entries(breakdowns).map(([key, data]) =>
            renderBreakdownChart(key, data as Array<Record<string, unknown>>)
          )}

          {/* Trend */}
          {trend.length > 0 && (
            <div>
              <h3 className="section-title">Trend</h3>
              <div className="card">
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="month"
                      tick={{ fontSize: 11, fill: "#94a3b8" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#94a3b8" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: "1px solid #e2e8f0",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="revenue"
                      stroke="#4f46e5"
                      fill="#4f46e5"
                      fillOpacity={0.06}
                      strokeWidth={2}
                      name="Revenue"
                    />
                    <Area
                      type="monotone"
                      dataKey="profit"
                      stroke="#059669"
                      fill="#059669"
                      fillOpacity={0.06}
                      strokeWidth={2}
                      name="Profit"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top Entities */}
          {topEntities.length > 0 && (
            <div>
              <h3 className="section-title">Top Entities</h3>
              <div className="card overflow-hidden">
                <DataTable
                  columns={Object.keys(topEntities[0]).map((k) => ({
                    key: k,
                    header: k
                      .replace(/_/g, " ")
                      .replace(/\b\w/g, (c) => c.toUpperCase()),
                    sortable: true,
                    align:
                      typeof topEntities[0][k] === "number" ? "right" : "left",
                  }))}
                  data={topEntities}
                  pageSize={10}
                />
              </div>
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          icon="🔬"
          title="Ready to Investigate"
          description="Select a metric and click 'Start Investigation' to drill into your business data."
        />
      )}
    </div>
  );
}
