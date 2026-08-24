"use client";

import { useState, useEffect } from "react";
import { Target, Loader2 } from "lucide-react";
import { generateInsights, getDataStatus } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";

interface Recommendation {
  title: string;
  why: string;
  evidence: string;
  confidence: string;
  impact: string;
}

export function RecommendationsPage() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
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

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const result = await generateInsights();
      if (result.insights) {
        setRecommendations(
          result.insights.map((i) => ({
            title: i.title,
            why: i.description,
            evidence: i.evidence.join(" · "),
            confidence: i.confidence,
            impact: i.impact,
          }))
        );
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Recommendations</h1>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-48 bg-slate-200 rounded mb-2" />
              <div className="h-3 w-full bg-slate-100 rounded mb-1" />
              <div className="h-3 w-2/3 bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Recommendations</h1>
        <EmptyState
          icon="📋"
          title="No Data for Recommendations"
          description="Upload structured data to receive evidence-backed recommendations."
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-900">Recommendations</h1>
        <button
          onClick={handleGenerate}
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
              Analyzing...
            </>
          ) : (
            <>
              <Target className="w-4 h-4" />
              Generate Recommendations
            </>
          )}
        </button>
      </div>

      {recommendations.length > 0 ? (
        <div className="space-y-3">
          {recommendations.map((rec, i) => (
            <div key={i} className="card border-l-4 border-l-brand-500">
              <div className="card-header">📋 {rec.title}</div>
              <div className="card-body">
                <strong>Why:</strong> {rec.why}
              </div>
              {rec.evidence && (
                <div className="card-meta">
                  <span>Evidence: {rec.evidence}</span>
                </div>
              )}
              <div className="flex items-center gap-3 mt-2">
                <span className="text-xs text-slate-500">
                  Impact:{" "}
                  <Badge
                    variant={rec.impact === "high" ? "danger" : "warning"}
                  >
                    {rec.impact}
                  </Badge>
                </span>
                <span className="text-xs text-slate-500">
                  Confidence:{" "}
                  <Badge
                    variant={
                      rec.confidence === "high" ? "success" : "neutral"
                    }
                  >
                    {rec.confidence}
                  </Badge>
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon="📋"
          title="No Recommendations"
          description="Click 'Generate Recommendations' to get evidence-backed suggestions."
        />
      )}
    </div>
  );
}
