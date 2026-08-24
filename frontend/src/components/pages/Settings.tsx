"use client";

import { useState, useEffect } from "react";
import {
  Settings as SettingsIcon,
  Database,
  Activity,
  CheckCircle,
  AlertCircle,
  XCircle,
  MinusCircle,
  Trash2,
} from "lucide-react";
import { getSystemHealth, getDataStatus, listActions, updateAction, deleteAction } from "@/lib/api/client";
import { cn, getStatusBg } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { formatNumber } from "@/lib/utils";

interface HealthCheck {
  status: string;
  latency_ms?: number;
  error?: string;
  message?: string;
  backend?: string;
  model?: string;
  chunks?: number;
}

interface ActionItem {
  id: string;
  title: string;
  description: string;
  owner: string;
  status: string;
  source_insight: string;
  expected_outcome: string;
  actual_outcome: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  healthy: <CheckCircle className="w-4 h-4 text-emerald-500" />,
  not_configured: <MinusCircle className="w-4 h-4 text-amber-500" />,
  error: <XCircle className="w-4 h-4 text-rose-500" />,
};

export function SettingsPage() {
  const [health, setHealth] = useState<Record<string, HealthCheck>>({});
  const [dataStatus, setDataStatus] = useState<{
    structured: Record<string, number>;
    knowledge: { documents: number; chunks: number };
  } | null>(null);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [h, ds, ac] = await Promise.all([
        getSystemHealth(),
        getDataStatus(),
        listActions(),
      ]);
      setHealth(h);
      setDataStatus(ds);
      setActions(ac.actions);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpdateAction = async (actionId: string, updates: { status?: string; actual_outcome?: string }) => {
    try {
      await updateAction(actionId, updates);
      loadData();
    } catch {
      // ignore
    }
  };

  const handleDeleteAction = async (actionId: string) => {
    try {
      await deleteAction(actionId);
      loadData();
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Data Sources & Settings</h1>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-48 bg-slate-200 rounded mb-2" />
              <div className="h-3 w-full bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8">
      <h1 className="text-lg font-bold text-slate-900">Data Sources & Settings</h1>

      {/* System Health */}
      <div>
        <h2 className="section-title">System Health</h2>
        <div className="space-y-2">
          {Object.entries(health).map(([name, info]) => (
            <div key={name} className="card">
              <div className="flex items-center gap-3">
                {STATUS_ICONS[info.status] || (
                  <AlertCircle className="w-4 h-4 text-slate-400" />
                )}
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">
                      {name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </span>
                    <Badge
                      variant={
                        info.status === "healthy"
                          ? "success"
                          : info.status === "not_configured"
                          ? "warning"
                          : "danger"
                      }
                    >
                      {info.status}
                    </Badge>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {Object.entries(info)
                      .filter(([k]) => k !== "status")
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(" · ")}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Data Status */}
      {dataStatus && (
        <div>
          <h2 className="section-title">Data Status</h2>
          <div className="card">
            <div className="grid grid-cols-4 gap-4 mb-4 pb-4 border-b border-slate-100">
              {Object.entries(dataStatus.structured).map(([table, count]) => (
                <div key={table}>
                  <div className="kpi-label">{table}</div>
                  <div className="text-sm font-semibold text-slate-900">
                    {formatNumber(count as number)}
                  </div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="kpi-label">Documents</div>
                <div className="text-sm font-semibold text-slate-900">
                  {dataStatus.knowledge.documents}
                </div>
              </div>
              <div>
                <div className="kpi-label">Chunks</div>
                <div className="text-sm font-semibold text-slate-900">
                  {formatNumber(dataStatus.knowledge.chunks)}
                </div>
              </div>
              <div>
                <div className="kpi-label">Vector Store</div>
                <div className="text-sm font-semibold text-slate-900">TF-IDF</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div>
        <h2 className="section-title">Actions</h2>
        {actions.length > 0 ? (
          <div className="space-y-3">
            {actions.map((action) => (
              <div key={action.id} className="card">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="card-header">{action.title}</div>
                    <div className="card-meta">
                      <span>Owner: {action.owner || "—"}</span>
                      <span>Created: {action.created_at?.slice(0, 10)}</span>
                    </div>
                  </div>
                  <Badge variant={action.status === "completed" ? "success" : action.status === "open" ? "neutral" : "warning"}>
                    {action.status.replace(/_/g, " ")}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 mt-3">
                  <select
                    value={action.status}
                    onChange={(e) => handleUpdateAction(action.id, { status: e.target.value })}
                    className="px-2 py-1 rounded border border-slate-200 text-xs text-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  >
                    <option value="open">Open</option>
                    <option value="in_progress">In Progress</option>
                    <option value="completed">Completed</option>
                    <option value="dismissed">Dismissed</option>
                  </select>
                  <input
                    type="text"
                    placeholder="Outcome..."
                    defaultValue={action.actual_outcome || ""}
                    onBlur={(e) => {
                      if (e.target.value !== (action.actual_outcome || "")) {
                        handleUpdateAction(action.id, { actual_outcome: e.target.value });
                      }
                    }}
                    className="flex-1 px-2 py-1 rounded border border-slate-200 text-xs text-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <button
                    onClick={() => handleDeleteAction(action.id)}
                    className="text-slate-400 hover:text-rose-500 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon="✅"
            title="No Actions"
            description="Create actions from recommendations to track business outcomes."
          />
        )}
      </div>
    </div>
  );
}
