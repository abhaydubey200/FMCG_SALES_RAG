"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen,
  Upload,
  Trash2,
  Search,
  FileText,
  Loader2,
  CheckCircle,
} from "lucide-react";
import { useDropzone } from "react-dropzone";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  sendQuery,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";

interface Doc {
  document_id: string;
  document_name: string;
  document_type: string;
  chunk_count: number;
  source_path: string;
}

export function KnowledgePage() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<Record<string, unknown>> | null>(null);
  const [searching, setSearching] = useState(false);

  const loadDocs = async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    setUploading(true);
    try {
      await uploadDocument(acceptedFiles[0]);
      loadDocs();
    } catch {
      // ignore
    } finally {
      setUploading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/markdown": [".md"],
      "text/csv": [".csv"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
    },
    maxFiles: 1,
  });

  const handleDelete = async (docId: string) => {
    try {
      await deleteDocument(docId);
      loadDocs();
    } catch {
      // ignore
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const result = await sendQuery(searchQuery);
      setSearchResults(
        result.evidence?.knowledge_base_chunks as Array<Record<string, unknown>> || []
      );
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const totalChunks = documents.reduce((sum, d) => sum + d.chunk_count, 0);

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-slate-900 mb-4">Knowledge Center</h1>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
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
      <h1 className="text-lg font-bold text-slate-900">Knowledge Center</h1>

      {/* Status Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="kpi-card">
          <div className="kpi-label">Documents</div>
          <div className="kpi-value">{documents.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Chunks</div>
          <div className="kpi-value">{totalChunks.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Vector Store</div>
          <div className="kpi-value">TF-IDF + BM25</div>
        </div>
      </div>

      {/* Indexed Documents */}
      <div>
        <h2 className="section-title">Indexed Documents</h2>
        {documents.length > 0 ? (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div key={doc.document_id} className="card flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="w-4 h-4 text-violet-500" />
                  <div>
                    <div className="text-sm font-medium text-slate-900">
                      📄 {doc.document_name}
                    </div>
                    <div className="text-xs text-slate-400">
                      {doc.chunk_count} chunks · {doc.document_type}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="success">Indexed ✓</Badge>
                  <button
                    onClick={() => handleDelete(doc.document_id)}
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
            icon="📚"
            title="No Documents"
            description="Upload documents (PDF, TXT, MD, CSV) to build your knowledge base."
          />
        )}
      </div>

      {/* Upload */}
      <div>
        <h2 className="section-title">Upload Document</h2>
        <p className="text-xs text-slate-400 mb-3">
          Supported: Markdown, CSV, Excel, Text
        </p>
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer",
            isDragActive
              ? "border-brand-400 bg-brand-50"
              : "border-slate-300 hover:border-brand-400 hover:bg-slate-50"
          )}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <div className="flex items-center justify-center gap-2">
              <Loader2 className="w-5 h-5 text-brand-500 animate-spin" />
              <span className="text-sm text-slate-600">Processing...</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1">
              <Upload className="w-6 h-6 text-slate-400" />
              <p className="text-sm text-slate-600">
                Drag & drop or click to upload
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Search */}
      <div>
        <h2 className="section-title">Search</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search documents..."
            className="flex-1 px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              searching || !searchQuery.trim()
                ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                : "bg-brand-600 text-white hover:bg-brand-700"
            )}
          >
            {searching ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Search className="w-3.5 h-3.5" />
            )}
            Search
          </button>
        </div>

        {searchResults && (
          <div className="mt-3 space-y-2">
            {searchResults.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">
                No results found
              </p>
            ) : (
              searchResults.map((r, i) => (
                <div key={i} className="card">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-slate-900">
                      {r.source as string}
                    </span>
                    <span className="text-xs text-brand-500">
                      relevance: {r.relevance_score as number}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-3">
                    {r.text as string}
                  </p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
