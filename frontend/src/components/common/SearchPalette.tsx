"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, X, FileText, Package, Megaphone, Users } from "lucide-react";
import { globalSearch } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface SearchPaletteProps {
  open: boolean;
  onClose: () => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  product: <Package className="w-4 h-4 text-brand-500" />,
  campaign: <Megaphone className="w-4 h-4 text-emerald-500" />,
  customer: <Users className="w-4 h-4 text-amber-500" />,
  document: <FileText className="w-4 h-4 text-violet-500" />,
};

export function SearchPalette({ open, onClose }: SearchPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{
    type: string;
    id: string;
    title: string;
    subtitle: string;
  }>>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await globalSearch(query);
        setResults(data.results);
        setSelectedIndex(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      const r = results[selectedIndex];
      let href = "/";
      if (r.type === "product") href = `/data-center?highlight=${r.id}`;
      else if (r.type === "campaign") href = `/data-center?highlight=${r.id}`;
      else if (r.type === "document") href = `/knowledge?highlight=${r.id}`;
      else href = `/data-center?highlight=${r.id}`;
      router.push(href);
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden animate-fade-in">
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <Search className="w-4 h-4 text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search products, campaigns, customers, documents..."
            className="flex-1 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 outline-none"
          />
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {loading && (
            <div className="px-4 py-8 text-center text-sm text-slate-400">
              Searching...
            </div>
          )}

          {!loading && query && results.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-slate-400">
              No results found
            </div>
          )}

          {!loading && results.length > 0 && (
            <div className="py-1">
              {results.map((r, i) => (
                <button
                  key={`${r.type}-${r.id}`}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors",
                    i === selectedIndex
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-700 hover:bg-slate-50"
                  )}
                  onClick={() => {
                    let href = "/data-center";
                    router.push(href);
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  <span className="shrink-0">{TYPE_ICONS[r.type] || <FileText className="w-4 h-4 text-slate-400" />}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{r.title}</div>
                    <div className="text-xs text-slate-400 truncate">{r.subtitle}</div>
                  </div>
                  <span className="ml-auto text-[0.6rem] text-slate-400 uppercase tracking-wider shrink-0">
                    {r.type}
                  </span>
                </button>
              ))}
            </div>
          )}

          {!query && (
            <div className="px-4 py-6 text-center text-sm text-slate-400">
              Type to search across all data assets
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
