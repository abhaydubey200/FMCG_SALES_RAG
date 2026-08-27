"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Upload,
  FolderOpen,
  Database,
  FileText,
  Trash2,
  RefreshCw,
  Loader2,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { useDropzone } from "react-dropzone";
import {
  getDataCenter,
  dataHubUpload,
  listDataHubDatasets,
  deleteDataHubDataset,
  deleteDataCenterAsset,
} from "@/lib/api/client";
import { cn, formatNumber, getStatusBg } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";

interface DataAsset {
  id: string;
  name: string;
  type: string;
  category: string;
  source: string;
  status: string;
  row_count?: number;
  chunk_count?: number;
}

export function DataCenterPage() {
  const [assets, setAssets] = useState<DataAsset[]>([]);
  const [datasets, setDatasets] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<"upload" | "sources">("upload");
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [dc, ds] = await Promise.all([getDataCenter(), listDataHubDatasets()]);
      setAssets(dc.assets);
      setDatasets(ds);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    setUploading(true);
    setUploadResult(null);
    setDeleteError(null);
    try {
      const result = await dataHubUpload(acceptedFiles[0]);
      setUploadResult(result as unknown as Record<string, unknown>);
      loadData();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "application/pdf": [".pdf"],
      "application/msword": [".doc"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
    },
    maxFiles: 1,
  });

  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null);
  const [confirmDeleteDataset, setConfirmDeleteDataset] = useState<{ id: string; name: string } | null>(null);

  const handleDeleteDataset = async (datasetId: string) => {
    try {
      setDeleteError(null);
      await deleteDataHubDataset(datasetId);
      loadData();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete dataset");
    }
  };

  const handleDeleteAsset = async (assetId: string) => {
    try {
      setDeleteError(null);
      await deleteDataCenterAsset(assetId);
      setConfirmDelete(null);
      loadData();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete asset");
      setConfirmDelete(null);
    }
  };

  const filteredAssets = assets.filter(
    (a) =>
      !searchQuery ||
      a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.source.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const structuredAssets = filteredAssets.filter((a) => a.type === "structured");
  const unstructuredAssets = filteredAssets.filter((a) => a.type === "unstructured");
  const isDeletable = (id: string) => id.startsWith("datahub_") || id.startsWith("kb_");

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Data Center</h1>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-48 bg-slate-200 rounded mb-2" />
              <div className="h-3 w-32 bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-900">Data Center</h1>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search assets..."
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 w-48"
          />
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-600 border border-slate-200 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Delete error banner */}
      {deleteError && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{deleteError}</span>
          <button onClick={() => setDeleteError(null)} className="ml-auto text-rose-400 hover:text-rose-600">
            <span className="sr-only">Dismiss</span>
            ×
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setActiveTab("upload")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "upload"
              ? "border-brand-600 text-brand-700"
              : "border-transparent text-slate-500 hover:text-slate-700"
          )}
        >
          <Upload className="w-3.5 h-3.5 inline mr-1.5" />
          Upload
        </button>
        <button
          onClick={() => setActiveTab("sources")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "sources"
              ? "border-brand-600 text-brand-700"
              : "border-transparent text-slate-500 hover:text-slate-700"
          )}
        >
          <FolderOpen className="w-3.5 h-3.5 inline mr-1.5" />
          Sources ({assets.length})
        </button>
      </div>

      {/* Upload Tab */}
      {activeTab === "upload" && (
        <div className="space-y-4">
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
              isDragActive
                ? "border-brand-400 bg-brand-50"
                : "border-slate-300 hover:border-brand-400 hover:bg-slate-50"
            )}
          >
            <input {...getInputProps()} />
            {uploading ? (
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                <p className="text-sm text-slate-600">Uploading & processing...</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Upload className="w-8 h-8 text-slate-400" />
                <p className="text-sm text-slate-600">
                  Drag & drop a file here, or click to browse
                </p>
                <p className="text-xs text-slate-400">
                  Structured: .csv, .xlsx, .xls &middot; Documents: .pdf, .docx, .doc, .txt
                </p>
              </div>
            )}
          </div>

          {/* Upload Result */}
          {uploadResult && (
            <div className="card bg-emerald-50 border-emerald-200">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-4 h-4 text-emerald-600" />
                <span className="text-sm font-semibold text-emerald-800">
                  Upload successful
                </span>
              </div>
              <p className="text-sm text-emerald-700">
                {(uploadResult.total_rows as number) > 0
                  ? `Processed ${formatNumber(uploadResult.total_rows as number)} rows`
                  : "Document ingested and indexed"}
              </p>
              {(uploadResult.profiles as Array<Record<string, unknown>>)?.map(
                (profile, i) => (
                  <div key={i} className="mt-3 p-3 bg-white rounded-lg border border-emerald-200">
                    <div className="text-sm font-medium text-slate-900">
                      {profile.filename as string}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                      {(profile.row_count as number) > 0 && (
                        <>{formatNumber(profile.row_count as number)} rows · {profile.col_count as number} cols</>
                      )}
                      {(profile.row_count as number) === 0 && (profile.file_type as string) && (
                        <span className="text-violet-600">{(profile.file_type as string).toUpperCase()} document</span>
                      )}
                      <span>Quality: {profile.quality_score as number}/100</span>
                    </div>
                    {(profile.issues as Array<Record<string, unknown>>)?.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {(profile.issues as Array<Record<string, unknown>>).map(
                          (issue, j) => (
                            <div
                              key={j}
                              className="flex items-center gap-1.5 text-xs text-amber-700"
                            >
                              <AlertCircle className="w-3 h-3" />
                              {issue.message as string}
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* Sources Tab */}
      {activeTab === "sources" && (
        <div className="space-y-6">
          {/* Structured Assets */}
          <div>
            <h2 className="section-title">Structured Data</h2>
            {structuredAssets.length > 0 ? (
              <div className="space-y-2">
                {structuredAssets.map((asset) => (
                  <div key={asset.id} className="card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Database className="w-4 h-4 text-brand-500" />
                      <div>
                        <div className="text-sm font-medium text-slate-900">
                          {asset.name}
                        </div>
                        <div className="text-xs text-slate-400">
                          {asset.row_count != null
                            ? `${formatNumber(asset.row_count)} rows`
                            : asset.source}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={getStatusBg(asset.status).includes("emerald") ? "success" : asset.status === "empty" ? "neutral" : "warning"}>
                        {asset.status}
                      </Badge>
                      {isDeletable(asset.id) && (
                        <button
                          onClick={() => setConfirmDelete({ id: asset.id, name: asset.name })}
                          className="text-slate-400 hover:text-rose-500 transition-colors p-1"
                          title="Delete structured data"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="card border-dashed border-slate-200 bg-slate-50/50">
                <div className="flex items-center gap-3 py-4 px-5">
                  <Database className="w-4 h-4 text-slate-300" />
                  <div>
                    <p className="text-sm text-slate-500">No structured data uploaded</p>
                    <p className="text-xs text-slate-400">Upload a CSV or Excel file to see it here</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Unstructured Assets */}
          <div>
            <h2 className="section-title">Unstructured Documents</h2>
            {unstructuredAssets.length > 0 ? (
              <div className="space-y-2">
                {unstructuredAssets.map((asset) => (
                  <div key={asset.id} className="card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <FileText className="w-4 h-4 text-violet-500" />
                      <div>
                        <div className="text-sm font-medium text-slate-900">
                          {asset.name}
                        </div>
                        <div className="text-xs text-slate-400">
                          {asset.chunk_count != null
                            ? `${asset.chunk_count} chunks · ${asset.source}`
                            : asset.source}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="success">{asset.status}</Badge>
                      {isDeletable(asset.id) && (
                        <button
                          onClick={() => setConfirmDelete({ id: asset.id, name: asset.name })}
                          className="text-slate-400 hover:text-rose-500 transition-colors p-1"
                          title="Delete document"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="card border-dashed border-slate-200 bg-slate-50/50">
                <div className="flex items-center gap-3 py-4 px-5">
                  <FileText className="w-4 h-4 text-slate-300" />
                  <div>
                    <p className="text-sm text-slate-500">No documents uploaded</p>
                    <p className="text-xs text-slate-400">Upload a PDF, DOCX, DOC, or TXT file to index it for RAG</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Uploaded Datasets (Data Hub) */}
          {datasets.length > 0 && (
            <div>
              <h2 className="section-title">Uploaded Datasets</h2>
              <div className="space-y-2">
                {datasets.map((ds) => (
                  <div
                    key={ds.dataset_id as string}
                    className="card flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="w-4 h-4 text-emerald-500" />
                      <div>
                        <div className="text-sm font-medium text-slate-900">
                          {ds.filename as string}
                        </div>
                        <div className="text-xs text-slate-400">
                          {formatNumber(ds.total_rows as number)} rows · {ds.total_columns as number} cols
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="success">
                        Score: {ds.quality_score as number}
                      </Badge>
                      <button
                        onClick={() => setConfirmDeleteDataset({ id: ds.dataset_id as string, name: ds.filename as string })}
                        className="text-slate-400 hover:text-rose-500 transition-colors p-1"
                        title="Delete dataset"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Global empty state — only when truly nothing */}
          {assets.length === 0 && datasets.length === 0 && (
            <EmptyState
              icon="📁"
              title="No Data Sources"
              description="Upload a structured data file (CSV/Excel) or a document (PDF/DOCX/TXT) to get started."
            />
          )}
        </div>
      )}

      {/* Delete Confirmation Modal — Asset */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-rose-100 flex items-center justify-center">
                <Trash2 className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Delete Asset</h3>
                <p className="text-xs text-slate-500">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 mb-6">
              Are you sure you want to delete <strong>{confirmDelete.name}</strong>? All data, documents, embeddings, and associated semantic mappings will be permanently removed.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteAsset(confirmDelete.id)}
                className="px-4 py-2 text-sm text-white bg-rose-600 rounded-lg hover:bg-rose-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal — Dataset */}
      {confirmDeleteDataset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-rose-100 flex items-center justify-center">
                <Trash2 className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Delete Dataset</h3>
                <p className="text-xs text-slate-500">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 mb-6">
              Are you sure you want to delete <strong>{confirmDeleteDataset.name}</strong>? The dataset, its physical table, all columns, quality results, and semantic mappings will be permanently removed.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmDeleteDataset(null)}
                className="px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  handleDeleteDataset(confirmDeleteDataset.id);
                  setConfirmDeleteDataset(null);
                }}
                className="px-4 py-2 text-sm text-white bg-rose-600 rounded-lg hover:bg-rose-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
