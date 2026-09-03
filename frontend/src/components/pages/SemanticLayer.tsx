"use client";

import { useState, useEffect } from "react";
import { Layers, ArrowRight, Database, Hash, Variable } from "lucide-react";
import { cn } from "@/lib/utils";
import { getSemanticMetrics, getSemanticDimensions } from "@/lib/api/client";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingState } from "@/components/common/LoadingState";

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
  const [activeTab, setActiveTab] = useState<"metrics" | "dimensions">("metrics");

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
        <PageHeader title="Semantic Layer" subtitle="Business concepts, metrics, and dimensions" />
        <LoadingState layout="list" lines={5} />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Semantic Layer"
        subtitle="Business concepts, metrics, and dimensions"
      />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="stat-box">
          <div className="stat-label">Metrics</div>
          <div className="flex items-center gap-2 mt-1">
            <Variable className="w-4 h-4 text-brand-500" />
            <div className="stat-value">{metrics.length}</div>
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Dimensions</div>
          <div className="flex items-center gap-2 mt-1">
            <Hash className="w-4 h-4 text-emerald-500" />
            <div className="stat-value">{dimensions.length}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setActiveTab("metrics")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "metrics" ? "tab-active" : "tab-inactive"
          )}
        >
          <Variable className="w-3.5 h-3.5 inline mr-1.5" />
          Metrics ({metrics.length})
        </button>
        <button
          onClick={() => setActiveTab("dimensions")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "dimensions" ? "tab-active" : "tab-inactive"
          )}
        >
          <Hash className="w-3.5 h-3.5 inline mr-1.5" />
          Dimensions ({dimensions.length})
        </button>
      </div>

      {/* Metrics */}
      {activeTab === "metrics" && (
        <>
          {metrics.length > 0 ? (
            <div className="space-y-3">
              {metrics.map((m) => (
                <div key={m.name} className="card">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="card-title">{m.name}</div>
                        <Badge variant="success">
                          <Database className="w-3 h-3" />
                          {m.source}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">{m.definition}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    <code className="text-xs bg-slate-50 px-2.5 py-1 rounded-md border border-slate-200/60 font-mono text-slate-700">
                      {m.formula}
                    </code>
                  </div>
                  {m.dimensions.length > 0 && (
                    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs text-slate-400">Dimensions:</span>
                      {m.dimensions.map((d) => (
                        <Badge key={d} variant="neutral">{d}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon="📐"
              title="No Metrics Defined"
              description="Metrics are auto-detected from your data sources when you upload data."
            />
          )}
        </>
      )}

      {/* Dimensions */}
      {activeTab === "dimensions" && (
        <>
          {dimensions.length > 0 ? (
            <div className="space-y-3">
              {dimensions.map((d) => (
                <div key={d.name} className="card">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="card-title">{d.name}</div>
                      <div className="text-xs text-slate-500 mt-1">
                        Source: {d.source}
                      </div>
                    </div>
                    <Badge variant="brand">
                      <Database className="w-3 h-3" />
                      {d.source}
                    </Badge>
                  </div>
                  {(d.columns && d.columns.length > 0) && (
                    <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs text-slate-400">Columns:</span>
                      {d.columns.map((col) => (
                        <Badge key={col} variant="neutral">{col}</Badge>
                      ))}
                    </div>
                  )}
                  {(d.values && d.values.length > 0) && (
                    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs text-slate-400">Values:</span>
                      {d.values.map((v) => (
                        <Badge key={v} variant="neutral">{v}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon="📐"
              title="No Dimensions Defined"
              description="Dimensions are auto-detected from your data sources when you upload data."
            />
          )}
        </>
      )}
    </div>
  );
}


