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
  HardDrive,
  FileSpreadsheet,
  File,
  Table2,
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
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingState } from "@/components/common/LoadingState";

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

const FILE_ICONS: Record<string, React.ReactNode> = {
  csv: <Table2 className="w-4 h-4 text-emerald-500" />,
  xlsx: <FileSpreadsheet className="w-4 h-4 text-emerald-500" />,
  xls: <FileSpreadsheet className="w-4 h-4 text-emerald-500" />,
  pdf: <FileText className="w-4 h-4 text-rose-500" />,
  docx: <FileText className="w-4 h-4 text-blue-500" />,
  doc: <FileText className="w-4 h-4 text-blue-500" />,
  txt: <File className="w-4 h-4 text-slate-500" />,
  md: <FileText className="w-4 h-4 text-violet-500" />,
};

function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  return FILE_ICONS[ext] || <File className="w-4 h-4 text-slate-400" />;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function DataCenterPage() {
  const [assets, setAssets] = useState<DataAsset[]>([]);
  const [datasets, setDatasets] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<"upload" | "sources">("sources");
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [dc, ds] = await Promise.allSettled([getDataCenter(), listDataHubDatasets()]);
      setAssets(dc.status === "fulfilled" ? dc.value.assets : []);
      setDatasets(ds.status === "fulfilled" ? ds.value : []);
      if (dc.status === "rejected" && ds.status === "rejected") {
        setDeleteError("Unable to connect to data service. Please check that the backend is running.");
      }
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to load data");
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
        <PageHeader title="Data Center" subtitle="Manage your data assets and uploads" />
        <LoadingState layout="list" lines={5} />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Data Center"
        subtitle="Manage your data assets and uploads"
        action={
          <button onClick={loadData} className="btn-secondary text-sm">
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        }
      />

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="stat-box">
          <div className="stat-label">Total Assets</div>
          <div className="stat-value">{assets.length + datasets.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Structured</div>
          <div className="stat-value">{structuredAssets.length + datasets.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Documents</div>
          <div className="stat-value">{unstructuredAssets.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Total Rows</div>
          <div className="stat-value">
            {formatNumber(
              datasets.reduce((sum, ds) => sum + ((ds.total_rows as number) || 0), 0) +
                structuredAssets.reduce((sum, a) => sum + (a.row_count || 0), 0)
            )}
          </div>
        </div>
      </div>

      {/* Delete error banner */}
      {deleteError && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700 animate-fade-in">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{deleteError}</span>
          <button onClick={() => setDeleteError(null)} className="ml-auto text-rose-400 hover:text-rose-600">
            ×
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setActiveTab("upload")}
          className={cn("px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "upload" ? "tab-active" : "tab-inactive"
          )}
        >
          <Upload className="w-3.5 h-3.5 inline mr-1.5" />
          Upload
        </button>
        <button
          onClick={() => setActiveTab("sources")}
          className={cn("px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "sources" ? "tab-active" : "tab-inactive"
          )}
        >
          <FolderOpen className="w-3.5 h-3.5 inline mr-1.5" />
          Sources ({assets.length + datasets.length})
        </button>
      </div>

      {/* Upload Tab */}
      {activeTab === "upload" && (
        <div className="space-y-4">
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer",
              isDragActive
                ? "border-brand-400 bg-brand-50/50 scale-[1.01]"
                : "border-slate-200 hover:border-brand-300 hover:bg-slate-50"
            )}
          >
            <input {...getInputProps()} />
            {uploading ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-brand-50 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-700">Processing file...</p>
                  <p className="text-xs text-slate-400 mt-1">Uploading, profiling, and indexing</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center">
                  <Upload className="w-6 h-6 text-slate-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-700">
                    Drag & drop a file here, or click to browse
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    CSV, Excel (.xlsx, .xls) · PDF, DOCX, DOC, TXT
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Upload Result */}
          {uploadResult && (
            <div className="card bg-emerald-50/50 border-emerald-200/60 animate-fade-in">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
                  <CheckCircle className="w-4 h-4 text-emerald-600" />
                </div>
                <div>
                  <span className="text-sm font-semibold text-emerald-800">Upload successful</span>
                  <p className="text-xs text-emerald-600">
                    {(uploadResult.total_rows as number) > 0
                      ? `Processed ${formatNumber(uploadResult.total_rows as number)} rows`
                      : "Document ingested and indexed"}
                  </p>
                </div>
              </div>
              {(uploadResult.profiles as Array<Record<string, unknown>>)?.map((profile, i) => (
                <div key={i} className="p-3 bg-white rounded-lg border border-emerald-200/60 mt-2">
                  <div className="flex items-center gap-2">
                    {getFileIcon(profile.filename as string)}
                    <span className="text-sm font-medium text-slate-900">{profile.filename as string}</span>
                  </div>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-slate-500">
                    {(profile.row_count as number) > 0 && (
                      <span>{formatNumber(profile.row_count as number)} rows · {profile.col_count as number} cols</span>
                    )}
                    {(profile.row_count as number) === 0 && (profile.file_type as string) && (
                      <span className="text-violet-600 font-medium">{(profile.file_type as string).toUpperCase()} document</span>
                    )}
                    <span>Quality: {profile.quality_score as number}/100</span>
                  </div>
                  {(profile.issues as Array<Record<string, unknown>>)?.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {(profile.issues as Array<Record<string, unknown>>).map((issue, j) => (
                        <div key={j} className="flex items-center gap-1.5 text-xs text-amber-700">
                          <AlertCircle className="w-3 h-3" />
                          {issue.message as string}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sources Tab */}
      {activeTab === "sources" && (
        <div className="space-y-6">
          {/* Search */}
          {assets.length + datasets.length > 0 && (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter assets..."
                className="input-field max-w-xs"
              />
            </div>
          )}

          {/* Structured Assets */}
          <div>
            <h2 className="section-title flex items-center gap-2">
              <Database className="w-3.5 h-3.5" />
              Structured Data
            </h2>
            {structuredAssets.length > 0 ? (
              <div className="space-y-2">
                {structuredAssets.map((asset) => (
                  <div key={asset.id} className="card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center">
                        <Database className="w-4 h-4 text-emerald-600" />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-slate-900">{asset.name}</div>
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
                          className="text-slate-400 hover:text-rose-500 transition-colors p-1.5 rounded-md hover:bg-rose-50"
                          title="Delete"
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
                <div className="flex items-center gap-3 py-5 px-5">
                  <Database className="w-5 h-5 text-slate-300" />
                  <div>
                    <p className="text-sm text-slate-500 font-medium">No structured data uploaded</p>
                    <p className="text-xs text-slate-400">Upload a CSV or Excel file to get started</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Unstructured Assets */}
          <div>
            <h2 className="section-title flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />
              Knowledge Documents
            </h2>
            {unstructuredAssets.length > 0 ? (
              <div className="space-y-2">
                {unstructuredAssets.map((asset) => (
                  <div key={asset.id} className="card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center">
                        {getFileIcon(asset.name)}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-slate-900">{asset.name}</div>
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
                          className="text-slate-400 hover:text-rose-500 transition-colors p-1.5 rounded-md hover:bg-rose-50"
                          title="Delete"
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
                <div className="flex items-center gap-3 py-5 px-5">
                  <FileText className="w-5 h-5 text-slate-300" />
                  <div>
                    <p className="text-sm text-slate-500 font-medium">No documents uploaded</p>
                    <p className="text-xs text-slate-400">Upload PDF, DOCX, TXT, or Markdown files for RAG</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Uploaded Datasets (Data Hub) */}
          {datasets.length > 0 && (
            <div>
              <h2 className="section-title flex items-center gap-2">
                <HardDrive className="w-3.5 h-3.5" />
                Uploaded Datasets
              </h2>
              <div className="space-y-2">
                {datasets.map((ds) => (
                  <div key={ds.dataset_id as string} className="card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center">
                        {getFileIcon(ds.filename as string)}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-slate-900">{ds.filename as string}</div>
                        <div className="text-xs text-slate-400">
                          {formatNumber(ds.total_rows as number)} rows · {ds.total_columns as number} columns
                          {Array.isArray(ds.sheets) && ds.sheets.length > 1 && (
                            <span className="text-violet-500 ml-1">
                              · {ds.sheets.length} sheets
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="success">
                        Quality: {ds.quality_score as number}
                      </Badge>
                      <button
                        onClick={() => setConfirmDeleteDataset({ id: ds.dataset_id as string, name: ds.filename as string })}
                        className="text-slate-400 hover:text-rose-500 transition-colors p-1.5 rounded-md hover:bg-rose-50"
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

          {/* Global empty state */}
          {assets.length === 0 && datasets.length === 0 && (
            <EmptyState
              icon="📁"
              title="No Data Sources"
              description="Upload a structured data file (CSV/Excel) or a document (PDF/DOCX/TXT) to get started."
              action={
                <button onClick={() => setActiveTab("upload")} className="btn-primary text-sm mt-2">
                  <Upload className="w-3.5 h-3.5" />
                  Upload Data
                </button>
              }
            />
          )}
        </div>
      )}

      {/* Delete Confirmation Modal — Asset */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4">
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
              <button onClick={() => setConfirmDelete(null)} className="btn-secondary text-sm">
                Cancel
              </button>
              <button onClick={() => handleDeleteAsset(confirmDelete.id)} className="btn-danger text-sm">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal — Dataset */}
      {confirmDeleteDataset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4">
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
              <button onClick={() => setConfirmDeleteDataset(null)} className="btn-secondary text-sm">
                Cancel
              </button>
              <button
                onClick={() => {
                  handleDeleteDataset(confirmDeleteDataset.id);
                  setConfirmDeleteDataset(null);
                }}
                className="btn-danger text-sm"
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
