"use client";

import {
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { RECHARTS_COLORS } from "@/lib/utils";

export interface ChartSpec {
  type: "line" | "bar" | "area" | "pie";
  title: string;
  data: Record<string, unknown>[];
  x_key: string;
  y_keys: string[];
  y_labels?: string[];
  colors?: string[];
}

interface AnalystChartProps {
  spec: ChartSpec;
  className?: string;
}

function formatValue(val: unknown): string {
  if (val == null) return "";
  if (typeof val === "number") {
    if (Math.abs(val) >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
    if (Math.abs(val) >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
    return val.toLocaleString("en-US");
  }
  return String(val);
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="text-slate-600">
          <span
            className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5"
            style={{ backgroundColor: entry.color }}
          />
          {entry.name}: {formatValue(entry.value)}
        </p>
      ))}
    </div>
  );
};

export function AnalystChart({ spec, className }: AnalystChartProps) {
  const colors = spec.colors || RECHARTS_COLORS;
  const height = 280;

  if (!spec.data || spec.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-slate-400">
        No data available for visualization
      </div>
    );
  }

  const xAxis = (
    <XAxis
      dataKey={spec.x_key}
      tick={{ fontSize: 11, fill: "#64748b" }}
      tickLine={false}
      axisLine={{ stroke: "#e2e8f0" }}
    />
  );
  const yAxis = (
    <YAxis
      tick={{ fontSize: 11, fill: "#64748b" }}
      tickLine={false}
      axisLine={false}
      tickFormatter={formatValue}
    />
  );
  const grid = <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />;
  const tooltip = <Tooltip content={<CustomTooltip />} />;

  const title = (
    <h4 className="text-sm font-semibold text-slate-700 mb-3">{spec.title}</h4>
  );

  if (spec.type === "pie") {
    const dataKey = spec.y_keys[0] || "value";
    return (
      <div className={className}>
        {title}
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Pie
              data={spec.data}
              dataKey={dataKey}
              nameKey={spec.x_key}
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ name, percent }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
            >
              {spec.data.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            {tooltip}
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (spec.type === "line") {
    return (
      <div className={className}>
        {title}
        <ResponsiveContainer width="100%" height={height}>
          <LineChart
            data={spec.data}
            margin={{ left: 10, right: 10, top: 10, bottom: 10 }}
          >
            {grid}
            {xAxis}
            {yAxis}
            {tooltip}
            {spec.y_keys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={spec.y_labels?.[i] || key}
                stroke={colors[i % colors.length]}
                strokeWidth={2}
                dot={{ r: 3, fill: colors[i % colors.length] }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (spec.type === "area") {
    return (
      <div className={className}>
        {title}
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart
            data={spec.data}
            margin={{ left: 10, right: 10, top: 10, bottom: 10 }}
          >
            {grid}
            {xAxis}
            {yAxis}
            {tooltip}
            {spec.y_keys.map((key, i) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                name={spec.y_labels?.[i] || key}
                stroke={colors[i % colors.length]}
                fill={colors[i % colors.length]}
                fillOpacity={0.15}
                strokeWidth={2}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Default: bar chart
  return (
    <div className={className}>
      {title}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={spec.data}
          margin={{ left: 10, right: 10, top: 10, bottom: 10 }}
        >
          {grid}
          {xAxis}
          {yAxis}
          {tooltip}
          {spec.y_keys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              name={spec.y_labels?.[i] || key}
              fill={colors[i % colors.length]}
              radius={[3, 3, 0, 0]}
              maxBarSize={48}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
