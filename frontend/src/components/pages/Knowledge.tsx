"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Upload,
  Trash2,
  Search,
  FileText,
  Loader2,
  BookOpen,
  Hash,
  Layers,
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
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingState } from "@/components/common/LoadingState";

interface Doc {
  document_id: string;
  document_name: string;
  document_type: string;
  chunk_count: number;
  source_path: string;
}

const DOC_ICONS: Record<string, string> = {
  markdown: "📝",
  pdf: "📕",
  docx: "📘",
  txt: "📄",
  csv: "📊",
};

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
      // knowledge documents loaded from vector store; empty is valid if no docs exist
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
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
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
        <PageHeader title="Knowledge Center" subtitle="Manage documents and RAG knowledge base" />
        <LoadingState layout="list" lines={4} />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Knowledge Center"
        subtitle="Manage documents and RAG knowledge base"
      />

      {/* Status Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="stat-box">
          <div className="stat-label">Documents</div>
          <div className="flex items-center gap-2 mt-1">
            <BookOpen className="w-4 h-4 text-brand-500" />
            <div className="stat-value">{documents.length}</div>
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Total Chunks</div>
          <div className="flex items-center gap-2 mt-1">
            <Hash className="w-4 h-4 text-emerald-500" />
            <div className="stat-value">{totalChunks.toLocaleString()}</div>
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Retrieval</div>
          <div className="flex items-center gap-2 mt-1">
            <Layers className="w-4 h-4 text-violet-500" />
            <div className="stat-value text-sm font-semibold">Hybrid</div>
          </div>
        </div>
      </div>

      {/* Indexed Documents */}
      <div>
        <h2 className="section-title flex items-center gap-2">
          <FileText className="w-3.5 h-3.5" />
          Indexed Documents
        </h2>
        {documents.length > 0 ? (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div key={doc.document_id} className="card flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="text-2xl">
                    {DOC_ICONS[doc.document_type] || "📄"}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-slate-900">{doc.document_name}</div>
                    <div className="text-xs text-slate-400">
                      {doc.chunk_count} chunks · {doc.document_type}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="success">Indexed</Badge>
                  <button
                    onClick={() => handleDelete(doc.document_id)}
                    className="text-slate-400 hover:text-rose-500 transition-colors p-1.5 rounded-md hover:bg-rose-50"
                    title="Delete document"
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
            description="Upload documents (PDF, Markdown, TXT, DOCX) to build your knowledge base."
          />
        )}
      </div>

      {/* Upload */}
      <div>
        <h2 className="section-title">Upload Document</h2>
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer",
            isDragActive
              ? "border-brand-400 bg-brand-50/50 scale-[1.01]"
              : "border-slate-200 hover:border-brand-300 hover:bg-slate-50"
          )}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
              <p className="text-sm text-slate-600">Processing document...</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload className="w-6 h-6 text-slate-400" />
              <div>
                <p className="text-sm font-medium text-slate-600">Drag & drop or click to upload</p>
                <p className="text-xs text-slate-400 mt-1">Markdown, PDF, DOCX, TXT</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Search */}
      <div>
        <h2 className="section-title">Search Knowledge Base</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search documents..."
            className="input-field flex-1"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className={cn(
              "btn-primary text-sm",
              (searching || !searchQuery.trim()) && "opacity-50 cursor-not-allowed"
            )}
          >
            {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            Search
          </button>
        </div>

        {searchResults && (
          <div className="mt-3 space-y-2">
            {searchResults.length === 0 ? (
              <div className="text-center py-8 text-sm text-slate-400">No results found</div>
            ) : (
              searchResults.map((r, i) => (
                <div key={i} className="card animate-fade-in">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-slate-900">{r.source as string}</span>
                    <Badge variant="brand">
                      score: {Number(r.relevance_score).toFixed(3)}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-3 leading-relaxed">{r.text as string}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
