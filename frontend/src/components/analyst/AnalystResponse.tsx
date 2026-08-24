"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ChevronDown,
  ChevronUp,
  Copy,
  Database,
  FileText,
  Code,
  CheckCircle,
  ExternalLink,
} from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";
import { AnalystChart, type ChartSpec } from "./AnalystChart";

interface KPI {
  label: string;
  value: string;
  delta?: number | null;
  format?: string;
}

interface TableSpec {
  title: string;
  columns: Array<{
    key: string;
    header: string;
    sortable?: boolean;
    align?: "left" | "right" | "center";
    format?: string;
  }>;
  rows: Record<string, unknown>[];
}

interface Source {
  type: string;
  source: string;
}

interface Evidence {
  knowledge_base_chunks?: Array<{
    source: string;
    text: string;
    relevance_score: number;
  }>;
  structured_data?: Record<string, unknown>;
  detected_conflict?: { note: string };
}

interface Visualization {
  kpis?: KPI[];
  charts?: Array<{
    type: string;
    title: string;
    data: Record<string, unknown>[];
    x_key: string;
    y_keys: string[];
    y_labels?: string[];
    colors?: string[];
  }>;
  tables?: TableSpec[];
  follow_ups?: string[];
}

interface AnalystResponseProps {
  answer: string;
  queryType: string;
  visualization?: Visualization;
  sources?: Source[];
  evidence?: Evidence;
  metrics?: Record<string, any>;
  onFollowUp?: (question: string) => void;
}

export function AnalystResponse({
  answer,
  queryType,
  visualization,
  sources,
  evidence,
  metrics,
  onFollowUp,
}: AnalystResponseProps) {
  const [showSQL, setShowSQL] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showCalc, setShowCalc] = useState(false);
  const [copied, setCopied] = useState(false);

  const viz = visualization || {};
  const kpis = viz.kpis || [];
  const charts = viz.charts || [];
  const tables = viz.tables || [];
  const followUps = viz.follow_ups || [];

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const queryTypeColors: Record<string, string> = {
    analytical: "bg-emerald-50 text-emerald-700 border-emerald-200",
    knowledge: "bg-brand-50 text-brand-700 border-brand-200",
    hybrid: "bg-violet-50 text-violet-700 border-violet-200",
    diagnostic: "bg-rose-50 text-rose-700 border-rose-200",
    unanswerable: "bg-slate-100 text-slate-600 border-slate-200",
    ambiguous: "bg-slate-100 text-slate-600 border-slate-200",
  };

  return (
    <div className="space-y-5">
      {/* Query type badge + latency */}
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border",
            queryTypeColors[queryType] || queryTypeColors.ambiguous
          )}
        >
          {queryType.toUpperCase()}
        </span>
        {metrics && metrics.end_to_end_latency_ms != null && (
          <span className="text-xs text-slate-400">
            {Number(metrics.end_to_end_latency_ms).toFixed(0)}ms
          </span>
        )}
        {metrics && metrics.llm_backend && (
          <span className="text-xs text-slate-400">
            via {String(metrics.llm_backend)}
          </span>
        )}
      </div>

      {/* KPI Metrics */}
      {kpis.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {kpis.map((kpi, i) => (
            <div
              key={i}
              className="bg-white border border-slate-200 rounded-lg px-4 py-3"
            >
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                {kpi.label}
              </div>
              <div className="text-xl font-bold text-slate-900 mt-1">
                {kpi.value}
              </div>
              {kpi.delta != null && (
                <div
                  className={cn(
                    "text-xs font-medium mt-0.5",
                    kpi.delta >= 0 ? "text-emerald-600" : "text-rose-600"
                  )}
                >
                  {kpi.delta >= 0 ? "▲" : "▼"} {Math.abs(kpi.delta).toFixed(1)}%
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Charts */}
      {charts.length > 0 && (
        <div className="space-y-4">
          {charts.map((chart, i) => (
            <div
              key={i}
              className="bg-white border border-slate-200 rounded-lg p-4"
            >
              <AnalystChart spec={{ ...chart, type: chart.type as ChartSpec["type"] }} />
            </div>
          ))}
        </div>
      )}

      {/* Narrative / Answer */}
      <div className="prose prose-sm max-w-none text-slate-700 leading-relaxed">
        <ReactMarkdown
          components={{
            p: ({ children }: any) => (
              <p className="mb-3 last:mb-0">{children}</p>
            ),
            ul: ({ children }: any) => (
              <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>
            ),
            ol: ({ children }: any) => (
              <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>
            ),
            strong: ({ children }: any) => (
              <strong className="font-semibold text-slate-800">{children}</strong>
            ),
            code: ({ children, className: cn }: any) => {
              const isBlock = cn?.includes("language-");
              if (isBlock) {
                return (
                  <code className="block bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs font-mono overflow-x-auto">
                    {children}
                  </code>
                );
              }
              return (
                <code className="px-1.5 py-0.5 bg-slate-100 rounded text-xs font-mono text-slate-700">
                  {children}
                </code>
              );
            },
          }}
        >
          {answer}
        </ReactMarkdown>
      </div>

      {/* Tables */}
      {tables.length > 0 && (
        <div className="space-y-4">
          {tables.map((table, i) => (
            <div
              key={i}
              className="bg-white border border-slate-200 rounded-lg overflow-hidden"
            >
              <div className="px-4 py-2.5 border-b border-slate-100">
                <h4 className="text-sm font-semibold text-slate-700">
                  {table.title}
                </h4>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      {table.columns.map((col) => (
                        <th
                          key={col.key}
                          className={cn(
                            "px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider",
                            col.align === "right" && "text-right",
                            col.align === "center" && "text-center"
                          )}
                        >
                          {col.header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, ri) => (
                      <tr
                        key={ri}
                        className="border-b border-slate-50 hover:bg-slate-50/50"
                      >
                        {table.columns.map((col) => {
                          const val = row[col.key];
                          let display: React.ReactNode = "—";
                          if (val != null) {
                            if (col.format === "currency") {
                              display = formatCurrency(val as number);
                            } else if (col.format === "percent") {
                              display = `${(val as number).toFixed(1)}%`;
                            } else if (col.format === "roas") {
                              display = `${(val as number).toFixed(2)}x`;
                            } else if (typeof val === "number") {
                              display = val.toLocaleString("en-US");
                            } else {
                              display = String(val);
                            }
                          }
                          return (
                            <td
                              key={col.key}
                              className={cn(
                                "px-3 py-2 text-slate-700",
                                col.align === "right" && "text-right",
                                col.align === "center" && "text-center"
                              )}
                            >
                              {display}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Expandable sections */}
      <div className="space-y-2">
        {/* Sources */}
        {sources && sources.length > 0 && (
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <FileText className="w-3.5 h-3.5" />
            Evidence ({sources.length} sources)
            {showEvidence ? (
              <ChevronUp className="w-3.5 h-3.5 ml-auto" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 ml-auto" />
            )}
          </button>
        )}
        {showEvidence && sources && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-3 animate-in fade-in">
            {sources.map((s, j) => (
              <div key={j} className="flex items-center gap-2">
                {s.type === "knowledge_base" ? (
                  <FileText className="w-3.5 h-3.5 text-violet-500 shrink-0" />
                ) : (
                  <Database className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                )}
                <span className="text-sm font-medium text-slate-700">
                  {s.source}
                </span>
                <span
                  className={cn(
                    "text-xs px-1.5 py-0.5 rounded",
                    s.type === "knowledge_base"
                      ? "bg-violet-50 text-violet-600"
                      : "bg-emerald-50 text-emerald-600"
                  )}
                >
                  {s.type === "knowledge_base" ? "Doc" : "Data"}
                </span>
              </div>
            ))}
            {/* Knowledge chunks */}
            {evidence?.knowledge_base_chunks?.map((chunk, j) => (
              <div key={j} className="bg-white border border-slate-200 rounded p-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-700 text-sm">
                    {chunk.source}
                  </span>
                  <span className="text-xs text-brand-500">
                    score: {chunk.relevance_score.toFixed(3)}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                  {chunk.text}
                </p>
              </div>
            ))}
            {/* Conflict warning */}
            {evidence?.detected_conflict && (
              <div className="flex items-start gap-2 p-2 rounded bg-amber-50 border border-amber-200">
                <span className="text-amber-600 text-sm">⚠</span>
                <span className="text-xs text-amber-700">
                  {evidence.detected_conflict.note}
                </span>
              </div>
            )}
          </div>
        )}

        {/* SQL */}
        {metrics && (
          <button
            onClick={() => setShowSQL(!showSQL)}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Code className="w-3.5 h-3.5" />
            View SQL & Sources
            {showSQL ? (
              <ChevronUp className="w-3.5 h-3.5 ml-auto" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 ml-auto" />
            )}
          </button>
        )}
        {showSQL && metrics && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 animate-in fade-in">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">
                Query Details
              </span>
              <button
                onClick={() =>
                  copyToClipboard(
                    JSON.stringify(metrics, null, 2)
                  )
                }
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
              >
                {copied ? (
                  <CheckCircle className="w-3 h-3" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="space-y-2 text-xs text-slate-600">
              <div>
                <span className="font-medium">Query Type:</span>{" "}
                {String(metrics.query_type)}
              </div>
              {metrics.llm_backend && (
                <div>
                  <span className="font-medium">LLM:</span>{" "}
                  {String(metrics.llm_model || metrics.llm_backend)}
                </div>
              )}
              {metrics.end_to_end_latency_ms != null && (
                <div>
                  <span className="font-medium">Latency:</span>{" "}
                  {Number(metrics.end_to_end_latency_ms).toFixed(0)}ms
                </div>
              )}
              <div>
                <span className="font-medium">Data Sources:</span>{" "}
                {sources?.map((s) => s.source).join(", ") || "—"}
              </div>
            </div>
          </div>
        )}

        {/* How was this calculated? */}
        {metrics && (
          <button
            onClick={() => setShowCalc(!showCalc)}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Database className="w-3.5 h-3.5" />
            How was this calculated?
            {showCalc ? (
              <ChevronUp className="w-3.5 h-3.5 ml-auto" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 ml-auto" />
            )}
          </button>
        )}
        {showCalc && metrics && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 animate-in fade-in text-xs text-slate-600 space-y-2">
            <div>
              <span className="font-medium">Classification:</span>{" "}
              {String(metrics.classification_reason || "—")}
            </div>
            <div>
              <span className="font-medium">Retrieval:</span>{" "}
              {String(metrics.retrieval_latency_ms || 0)}ms
            </div>
            <div>
              <span className="font-medium">Generation:</span>{" "}
              {String(metrics.generation_latency_ms || 0)}ms
            </div>
            <div>
              <span className="font-medium">Total:</span>{" "}
              {String(metrics.end_to_end_latency_ms || 0)}ms
            </div>
          </div>
        )}
      </div>

      {/* Follow-up questions */}
      {followUps.length > 0 && onFollowUp && (
        <div className="pt-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
            Follow-up questions
          </p>
          <div className="flex flex-wrap gap-2">
            {followUps.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp(q)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
