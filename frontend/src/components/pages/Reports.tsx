"use client";

import { useState, useEffect } from "react";
import {
  FileText,
  Loader2,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Target,
} from "lucide-react";
import { generateExecutiveBrief, getDataStatus } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/common/EmptyState";

interface BriefSection {
  title: string;
  content: string;
}

const SECTION_ICONS: Record<string, React.ReactNode> = {
  "Business Performance": <BarChart3 className="w-4 h-4 text-brand-600" />,
  "Key Drivers": <TrendingUp className="w-4 h-4 text-emerald-600" />,
  "Risks": <AlertTriangle className="w-4 h-4 text-amber-600" />,
  "Opportunities": <Lightbulb className="w-4 h-4 text-violet-600" />,
  "Recommended Actions": <Target className="w-4 h-4 text-rose-600" />,
};

export function ReportsPage() {
  const [sections, setSections] = useState<BriefSection[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string>("");
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
      const result = await generateExecutiveBrief();
      setSections(result.sections);
      setGeneratedAt(result.generated_at);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Executive Reports</h1>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
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
        <h1 className="text-lg font-bold text-slate-900 mb-4">Executive Reports</h1>
        <EmptyState
          icon="📄"
          title="No Data for Reports"
          description="Upload structured data to generate executive reports."
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-900">Executive Reports</h1>
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
              Generating...
            </>
          ) : (
            <>
              <FileText className="w-4 h-4" />
              Generate Report
            </>
          )}
        </button>
      </div>

      {sections.length > 0 ? (
        <div className="space-y-3">
          {generatedAt && (
            <p className="text-xs text-slate-400">
              Generated: {new Date(generatedAt).toLocaleString()}
            </p>
          )}
          {sections.map((section, i) => (
            <div key={i} className="card">
              <div className="flex items-center gap-2 mb-2">
                {SECTION_ICONS[section.title] || (
                  <FileText className="w-4 h-4 text-slate-400" />
                )}
                <div className="card-header">{section.title}</div>
              </div>
              <div className="card-body whitespace-pre-line leading-relaxed">
                {section.content}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon="📄"
          title="No Report Generated"
          description="Click 'Generate Report' to create a structured business summary."
        />
      )}
    </div>
  );
}
