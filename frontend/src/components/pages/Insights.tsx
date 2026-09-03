"use client";

import { useState, useEffect } from "react";
import { Lightbulb, AlertTriangle, CheckCircle, Info, Loader2 } from "lucide-react";
import { generateInsights, getDataStatus } from "@/lib/api/client";
import { cn, getInsightBorder } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingState } from "@/components/common/LoadingState";

interface Insight {
  type: "warning" | "success" | "info";
  title: string;
  description: string;
  impact: string;
  confidence: string;
  evidence: string[];
}

const ICONS: Record<string, React.ReactNode> = {
  warning: <AlertTriangle className="w-4 h-4 text-amber-600" />,
  success: <CheckCircle className="w-4 h-4 text-emerald-600" />,
  info: <Info className="w-4 h-4 text-brand-600" />,
};

export function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
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
      setInsights(result.insights as Insight[]);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="p-6">
        <PageHeader title="AI Insights" subtitle="AI-generated business patterns and anomalies" />
        <LoadingState layout="list" lines={4} />
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="p-6">
        <PageHeader title="AI Insights" subtitle="AI-generated business patterns and anomalies" />
        <EmptyState
          icon="💡"
          title="No Data for Insights"
          description="Upload structured data to generate AI-powered business insights."
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="AI Insights"
        subtitle="AI-generated business patterns and anomalies"
        action={
          <button
            onClick={handleGenerate}
            disabled={loading}
            className={cn("btn-primary text-sm", loading && "opacity-50 cursor-not-allowed")}
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Lightbulb className="w-4 h-4" />
                Generate Insights
              </>
            )}
          </button>
        }
      />

      {insights.length > 0 ? (
        <div className="space-y-3">
          {insights.map((insight, i) => (
            <div
              key={i}
              className={cn("card border-l-4", getInsightBorder(insight.type))}
            >
              <div className="flex items-start gap-3">
                <span className="shrink-0 mt-0.5">{ICONS[insight.type]}</span>
                <div className="flex-1 min-w-0">
                  <div className="card-title">{insight.title}</div>
                  <p className="text-sm text-slate-600 mt-1 leading-relaxed">{insight.description}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs text-slate-500">
                      Impact:{" "}
                      <Badge variant={insight.impact === "high" ? "danger" : "warning"}>
                        {insight.impact}
                      </Badge>
                    </span>
                    <span className="text-xs text-slate-500">
                      Confidence:{" "}
                      <Badge variant={insight.confidence === "high" ? "success" : "neutral"}>
                        {insight.confidence}
                      </Badge>
                    </span>
                  </div>
                  {insight.evidence?.length > 0 && (
                    <div className="mt-2 text-xs text-slate-500">
                      Evidence: {insight.evidence.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon="💡"
          title="No Insights Yet"
          description="Click 'Generate Insights' to analyze your data for actionable patterns."
        />
      )}
    </div>
  );
}
