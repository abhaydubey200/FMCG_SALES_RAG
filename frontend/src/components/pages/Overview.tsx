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
  Legend,
} from "recharts";
import {
  getAnalyticsOverview,
  getRevenueTrend,
  getCategoryPerformance,
  getDataStatus,
} from "@/lib/api/client";
import { formatCurrency, formatNumber, RECHARTS_COLORS } from "@/lib/utils";
import { KPICard } from "@/components/common/KPICard";
import { KPISkeleton, ChartSkeleton } from "@/components/common/Skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import Link from "next/link";

export function OverviewPage() {
  const [overview, setOverview] = useState<Record<string, unknown> | null>(null);
  const [trend, setTrend] = useState<Array<Record<string, unknown>>>([]);
  const [categories, setCategories] = useState<Array<Record<string, unknown>>>([]);
  const [hasData, setHasData] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const status = await getDataStatus();
        setHasData(status.has_data);
        if (status.has_data) {
          const [ov, tr, cat] = await Promise.all([
            getAnalyticsOverview(),
            getRevenueTrend(),
            getCategoryPerformance(),
          ]);
          setOverview(ov as unknown as Record<string, unknown>);
          setTrend(tr as unknown as Array<Record<string, unknown>>);
          setCategories(cat as unknown as Array<Record<string, unknown>>);
        }
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
      <div className="p-6 space-y-6">
        <h1 className="text-lg font-bold text-slate-900">Executive Overview</h1>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <KPISkeleton key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <div className="lg:col-span-3"><ChartSkeleton /></div>
          <div className="lg:col-span-2"><ChartSkeleton /></div>
        </div>
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Executive Overview</h1>
        <EmptyState
          icon="📊"
          title="No Data Connected"
          description="Upload a CSV or Excel file in Data Center to see your business overview."
          action={
            <Link
              href="/data-center"
              className="inline-flex items-center px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 transition-colors"
            >
              Go to Data Center
            </Link>
          }
        />
      </div>
    );
  }

  const kpi = overview as Record<string, number> | null;
  const trendData = trend.map((t) => ({
    ...t,
    month: t.month,
    revenue: Number(t.revenue) || 0,
    profit: Number(t.profit) || 0,
  }));
  const catData = categories.map((c) => ({
    category: c.category,
    revenue: Number(c.revenue) || 0,
  }));

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-lg font-bold text-slate-900">Executive Overview</h1>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICard
          label="Revenue"
          value={formatCurrency(kpi?.total_revenue)}
          delta={kpi?.revenue_growth_pct}
        />
        <KPICard
          label="Orders"
          value={formatNumber(kpi?.total_units_sold)}
          delta={kpi?.units_growth_pct}
        />
        <KPICard
          label="Margin"
          value={`${kpi?.gross_margin_pct ?? "N/A"}%`}
          delta={kpi?.margin_growth_pct}
        />
        <KPICard
          label="Spend"
          value={formatCurrency(kpi?.total_marketing_spend)}
          delta={kpi?.spend_growth_pct}
        />
        <KPICard
          label="ROAS"
          value={`${kpi?.avg_roas ?? "N/A"}x`}
          delta={kpi?.roas_growth_pct}
        />
        <KPICard
          label="Customers"
          value={formatNumber(kpi?.total_customers)}
          delta={kpi?.customer_growth_pct}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Revenue Trend */}
        <div className="lg:col-span-3 card">
          <h2 className="card-header mb-4">Revenue & Profit Trend</h2>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={trendData}>
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
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    formatCurrency(value),
                    name,
                  ]}
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
          ) : (
            <div className="h-64 flex items-center justify-center text-sm text-slate-400">
              No trend data available
            </div>
          )}
        </div>

        {/* Category Performance */}
        <div className="lg:col-span-2 card">
          <h2 className="card-header mb-4">Category Performance</h2>
          {catData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={catData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                />
                <YAxis
                  type="category"
                  dataKey="category"
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                  width={90}
                />
                <Tooltip
                  formatter={(value: number) => [formatCurrency(value), "Revenue"]}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                  }}
                />
                <Bar
                  dataKey="revenue"
                  fill={RECHARTS_COLORS[0]}
                  radius={[0, 4, 4, 0]}
                  barSize={20}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-sm text-slate-400">
              No category data available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
