"use client";

import { useState, useEffect } from "react";
import { Layers } from "lucide-react";
import { getSemanticMetrics, getSemanticDimensions } from "@/lib/api/client";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";

interface Metric {
  name: string;
  definition: string;
  formula: string;
  source: string;
  dimensions: string[];
}

interface Dimension {
  name: string;
  columns?: string[];
  values?: string[];
  source: string;
}

export function SemanticLayerPage() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [m, d] = await Promise.all([
          getSemanticMetrics(),
          getSemanticDimensions(),
        ]);
        setMetrics(m.metrics);
        setDimensions(d.dimensions);
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
        <h1 className="text-lg font-bold text-slate-900 mb-4">Semantic & Metric Layer</h1>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-40 bg-slate-200 rounded mb-2" />
              <div className="h-3 w-full bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8">
      <h1 className="text-lg font-bold text-slate-900">Semantic & Metric Layer</h1>

      {/* Metrics */}
      <div>
        <h2 className="section-title">Business Metrics</h2>
        {metrics.length > 0 ? (
          <div className="space-y-2">
            {metrics.map((m) => (
              <div key={m.name} className="card">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="card-header">{m.name}</div>
                    <div className="card-body">{m.definition}</div>
                  </div>
                  <Badge variant="success">{m.source}</Badge>
                </div>
                <div className="mt-2">
                  <code className="text-xs bg-slate-50 px-2 py-1 rounded border border-slate-200 font-mono text-slate-700">
                    {m.formula}
                  </code>
                </div>
                <div className="card-meta">
                  <span>Dimensions: {m.dimensions.join(", ")}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon="📐"
            title="No Metrics Defined"
            description="Metrics are auto-detected from your data sources."
          />
        )}
      </div>

      {/* Dimensions */}
      <div>
        <h2 className="section-title">Dimensions</h2>
        {dimensions.length > 0 ? (
          <div className="space-y-2">
            {dimensions.map((d) => (
              <div key={d.name} className="card">
                <div className="card-header">{d.name}</div>
                <div className="card-body">
                  Source: {d.source} · Columns:{" "}
                  {d.columns?.join(", ") || d.values?.join(", ")}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon="📐"
            title="No Dimensions Defined"
            description="Dimensions are auto-detected from your data sources."
          />
        )}
      </div>
    </div>
  );
}
