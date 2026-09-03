"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Send,
  Plus,
  History,
  Sparkles,
  Loader2,
  Trash2,
  Brain,
  MessageSquare,
  Clock,
  ChevronDown,
  PanelLeftClose,
  PanelLeft,
  AlertCircle,
  Square,
  RotateCcw,
} from "lucide-react";
import {
  aiQuery,
  aiQueryStream,
  getDataStatus,
  listConversations,
  createConversation,
  getConversation,
  addMessage,
  deleteConversation,
  type StreamEvent,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { AnalystResponse } from "@/components/analyst/AnalystResponse";
import { timeAgo } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Timeout constants
// ---------------------------------------------------------------------------
const STREAM_TIMEOUT_MS = 120_000; // 2 minutes max for streaming
const INITIAL_CONNECT_TIMEOUT_MS = 30_000; // 30s for first bytes
const MIN_QUESTION_LENGTH = 3;

interface Message {
  role: "user" | "assistant";
  content: string;
  result?: {
    answer: string;
    query_type: string;
    sources: Array<{ type: string; source: string }>;
    metrics: Record<string, unknown>;
    evidence: {
      knowledge_base_chunks?: Array<{
        source: string;
        text: string;
        relevance_score: number;
      }>;
      structured_data?: Record<string, unknown>;
      detected_conflict?: { note: string };
    };
    visualization?: {
      kpis?: Array<{ label: string; value: string; delta?: number | null }>;
      charts?: Array<{
        type: string;
        title: string;
        data: Record<string, unknown>[];
        x_key: string;
        y_keys: string[];
        y_labels?: string[];
        colors?: string[];
      }>;
      tables?: Array<{
        title: string;
        columns: Array<{
          key: string;
          header: string;
          sortable?: boolean;
          align?: string;
          format?: string;
        }>;
        rows: Record<string, unknown>[];
      }>;
      follow_ups?: string[];
    };
  };
  _streaming?: boolean;
  _error?: boolean;
}

interface Conversation {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

function groupConversations(convs: Conversation[]) {
  const now = new Date();
  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const thisWeek: Conversation[] = [];
  const older: Conversation[] = [];

  for (const c of convs) {
    const d = new Date(c.updated_at);
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diffDays < 1) today.push(c);
    else if (diffDays < 2) yesterday.push(c);
    else if (diffDays < 7) thisWeek.push(c);
    else older.push(c);
  }

  return [
    { label: "Today", items: today },
    { label: "Yesterday", items: yesterday },
    { label: "This Week", items: thisWeek },
    { label: "Older", items: older },
  ].filter((g) => g.items.length > 0);
}

/** Create a timeout promise that rejects after ms */
function timeoutPromise(ms: number, label: string): Promise<never> {
  return new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`TIMEOUT:${label}`)), ms)
  );
}

export function AIAnalyst() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hasData, setHasData] = useState(false);
  const [hasKb, setHasKb] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConvId, setCurrentConvId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer while loading
  useEffect(() => {
    if (!loading || startTime === null) {
      setElapsed(0);
      return;
    }
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [loading, startTime]);

  useEffect(() => {
    const checkData = async () => {
      try {
        const status = await getDataStatus();
        setHasData(status.has_data);
        setHasKb(status.has_knowledge);
      } catch {
        setHasData(false);
        setHasKb(false);
      }
    };
    checkData();
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      const data = await listConversations();
      setConversations(data.conversations);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** Cancel any in-flight request */
  const stopGenerating = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const handleSend = useCallback(async (overrideInput?: string) => {
    const q = (overrideInput || input).trim();
    if (!q || loading) return;

    // Validate question length
    if (q.length < MIN_QUESTION_LENGTH) {
      setError(`Question must be at least ${MIN_QUESTION_LENGTH} characters.`);
      return;
    }

    const userMessage: Message = { role: "user", content: q };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setError(null);
    setStartTime(Date.now());

    // Create a new abort controller for this request
    const ac = new AbortController();
    abortControllerRef.current = ac;

    let convId = currentConvId;
    let assistantMsgIdx = -1;

    try {
      // Ensure conversation exists
      if (!convId) {
        try {
          const conv = await createConversation();
          convId = conv.id;
          setCurrentConvId(conv.id);
        } catch {
          // Continue without conversation persistence
        }
      }

      // Persist user message (non-blocking — don't fail the query)
      if (convId) {
        addMessage(convId, { role: "user", content: q }).catch(() => {});
      }

      // Add streaming placeholder
      setMessages((prev) => {
        const msg: Message = {
          role: "assistant",
          content: "",
          result: undefined,
          _streaming: true,
        };
        assistantMsgIdx = prev.length;
        return [...prev, msg];
      });

      // ── Try streaming first ──
      let streamSucceeded = false;
      let streamedContent = "";
      let streamMetadata: Record<string, unknown> = {};

      try {
        const streamIterator = aiQueryStream(q, convId || undefined, ac.signal);

        // Race stream against timeout
        const streamResult = await Promise.race([
          (async () => {
            for await (const event of streamIterator) {
              if (ac.signal.aborted) break;

              if (event.type === "metadata") {
                const meta = event as Extract<StreamEvent, { type: "metadata" }>;
                streamMetadata = {
                  query_type: meta.query_type,
                  sources: meta.sources,
                  visualization: meta.visualization,
                  agents_used: (meta as any).agents_used || [],
                  skills_used: (meta as any).skills_used || [],
                  plan_steps: (meta as any).plan_steps || 0,
                  classification_reason: (meta as any).classification_reason || "",
                  trace_id: (meta as any).trace_id || "",
                };
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && (last as any)._streaming) {
                    updated[updated.length - 1] = {
                      ...last,
                      result: {
                        answer: "",
                        query_type: meta.query_type,
                        sources: meta.sources || [],
                        metrics: {},
                        evidence: {},
                        visualization: (meta.visualization as any) || {},
                      },
                    };
                  }
                  return updated;
                });
              } else if (event.type === "token") {
                const token = event as Extract<StreamEvent, { type: "token" }>;
                streamedContent += token.content;
                const content = streamedContent;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && (last as any)._streaming) {
                    updated[updated.length - 1] = {
                      ...last,
                      content,
                      result: last.result ? { ...last.result, answer: content } : undefined,
                    };
                  }
                  return updated;
                });
              } else if (event.type === "progress") {
                // Progress events — update UI stage
                const prog = event as Extract<StreamEvent, { type: "progress" }>;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && (last as any)._streaming) {
                    updated[updated.length - 1] = {
                      ...last,
                      content: last.content || "",
                      result: last.result
                        ? { ...last.result, answer: last.result.answer || "" }
                        : undefined,
                    };
                  }
                  return updated;
                });
              } else if (event.type === "done") {
                const done = event as Extract<StreamEvent, { type: "done" }>;
                streamSucceeded = true;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && (last as any)._streaming) {
                    updated[updated.length - 1] = {
                      role: "assistant",
                      content: done.answer || streamedContent,
                      result: {
                        answer: done.answer || streamedContent,
                        query_type: (done.metrics as any)?.query_type || (streamMetadata as any)?.query_type || "analytical",
                        sources: (done as any).sources || (streamMetadata as any)?.sources || [],
                        metrics: done.metrics || {},
                        evidence: (done as any).evidence || {},
                        visualization: done.visualization as any,
                      },
                    };
                  }
                  return updated;
                });
              } else if (event.type === "error") {
                const errEvt = event as Extract<StreamEvent, { type: "error" }>;
                throw new Error(errEvt.error);
              }
            }
            return "stream-done";
          })(),
          timeoutPromise(STREAM_TIMEOUT_MS, "streaming"),
        ]);
      } catch (streamError) {
        // ── Streaming failed — try non-streaming fallback ──
        if (ac.signal.aborted) {
          // User cancelled
          setMessages((prev) => {
            const updated = [...prev];
            if (updated.length > 0 && (updated[updated.length - 1] as any)._streaming) {
              updated.pop();
            }
            return [...updated, {
              role: "assistant" as const,
              content: "Generation stopped.",
              _error: true,
            }];
          });
          setLoading(false);
          setStartTime(null);
          return;
        }

        // Remove streaming placeholder
        setMessages((prev) => {
          const updated = [...prev];
          if (updated.length > 0 && (updated[updated.length - 1] as any)._streaming) {
            updated.pop();
          }
          return updated;
        });

        // Try non-streaming fallback
        try {
          const result = await Promise.race([
            aiQuery(q, convId || undefined, ac.signal),
            timeoutPromise(STREAM_TIMEOUT_MS, "non-streaming fallback"),
          ]);
          const assistantMessage: Message = {
            role: "assistant",
            content: result.answer,
            result: result as Message["result"],
          };
          setMessages((prev) => [...prev, assistantMessage]);
          streamSucceeded = true;
        } catch (fallbackError) {
          const isAbort = ac.signal.aborted;
          const isTimeout = fallbackError instanceof Error && fallbackError.message.startsWith("TIMEOUT:");
          let errorMsg = "Query failed";
          if (isAbort) {
            errorMsg = "Generation stopped.";
          } else if (isTimeout) {
            errorMsg = "The request timed out. The AI model may be slow — try a simpler question.";
          } else if (fallbackError instanceof Error) {
            errorMsg = fallbackError.message;
          }

          setError(errorMsg);
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant" as const,
              content: "",
              _error: true,
              result: {
                answer: "",
                query_type: "error",
                sources: [],
                metrics: {},
                evidence: {},
                visualization: {},
              },
            } as Message,
          ]);
        }
      }

      // Persist assistant response
      if (convId && streamSucceeded) {
        const capturedConvId = convId;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.result) {
            addMessage(capturedConvId, {
              role: "assistant",
              content: last.content,
              result: last.result,
            }).catch(() => {});
          }
          return prev;
        });
      }

      loadConversations();
    } catch {
      setError("Connection error. Please check that the API is running and try again.");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant" as const,
          content: "",
          _error: true,
        } as Message,
      ]);
    } finally {
      setLoading(false);
      setStartTime(null);
      abortControllerRef.current = null;
    }
  }, [input, loading, currentConvId, loadConversations]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    stopGenerating();
    setMessages([]);
    setCurrentConvId(null);
    setError(null);
    setLoading(false);
    setStartTime(null);
  };

  const handleLoadConversation = async (conv: Conversation) => {
    try {
      stopGenerating();
      const data = await getConversation(conv.id);
      setMessages(
        data.messages.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          result: m.result as Message["result"],
        }))
      );
      setCurrentConvId(conv.id);
      setShowHistory(false);
      setError(null);
    } catch {
      // ignore
    }
  };

  const handleDeleteConversation = async (convId: string) => {
    try {
      await deleteConversation(convId);
      if (currentConvId === convId) {
        handleNewChat();
      }
      loadConversations();
    } catch {
      // ignore
    }
  };

  const isEmpty = messages.length === 0 && !loading;
  const groupedConvs = groupConversations(conversations);

  return (
    <div className="flex h-full bg-slate-50">
      {/* ── Conversation Sidebar ── */}
      <div
        className={cn(
          "hidden md:flex flex-col border-r border-slate-200/80 bg-white transition-all duration-200 shrink-0",
          showHistory ? "w-72" : "w-0 overflow-hidden border-0"
        )}
      >
        {showHistory && (
          <>
            <div className="flex items-center justify-between px-4 h-14 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-900">Conversations</span>
              <button
                onClick={() => setShowHistory(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto py-2 px-2 scrollbar-thin">
              {conversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
                  <MessageSquare className="w-8 h-8 text-slate-200 mb-3" />
                  <p className="text-sm text-slate-400">No conversations yet</p>
                </div>
              ) : (
                groupedConvs.map((group) => (
                  <div key={group.label} className="mb-2">
                    <div className="px-3 pt-3 pb-1.5 text-[0.6rem] font-semibold text-slate-400 uppercase tracking-wider">
                      {group.label}
                    </div>
                    {group.items.map((conv) => (
                      <div
                        key={conv.id}
                        className={cn(
                          "px-3 py-2.5 rounded-lg cursor-pointer transition-colors group",
                          currentConvId === conv.id
                            ? "bg-brand-50 border border-brand-200/60"
                            : "hover:bg-slate-50 border border-transparent"
                        )}
                        onClick={() => handleLoadConversation(conv)}
                      >
                        <div className="text-sm font-medium text-slate-900 truncate">
                          {conv.title}
                        </div>
                        <div className="flex items-center justify-between mt-1">
                          <span className="text-xs text-slate-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {conv.message_count} messages · {timeAgo(conv.updated_at)}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteConversation(conv.id);
                            }}
                            className="text-slate-400 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-5 h-14 border-b border-slate-200/80 bg-white shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-900">AI Analyst</h1>
              <p className="text-xs text-slate-400">Decision Intelligence Workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                showHistory
                  ? "bg-brand-50 text-brand-600"
                  : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              )}
              title="Toggle conversation history"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
            <button
              onClick={handleNewChat}
              className="btn-ghost text-xs"
              title="New conversation"
            >
              <Plus className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">New Chat</span>
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {isEmpty ? (
            /* ── Empty State ── */
            <div className="max-w-2xl mx-auto px-6 py-20">
              <div className="text-center">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center mx-auto mb-5 shadow-lg">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
                <h2 className="text-xl font-bold text-slate-900 mb-2">
                  What would you like to analyze?
                </h2>
                <p className="text-sm text-slate-500 max-w-md mx-auto leading-relaxed mb-8">
                  {hasData || hasKb
                    ? "Ask questions about your data. The analyst dynamically discovers metrics, dimensions, and documents to answer from real evidence."
                    : "Upload structured data (CSV/Excel) or documents (PDF/DOCX/TXT) in the Data Center, then come back to ask business questions."}
                </p>

                {(hasData || hasKb) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto text-left">
                    <button
                      onClick={() => handleSend("What is total revenue?")}
                      className="card card-interactive p-3"
                    >
                      <div className="text-xs font-medium text-brand-600 mb-1">Analytics</div>
                      <div className="text-sm text-slate-700">What is total revenue across all datasets?</div>
                    </button>
                    <button
                      onClick={() => handleSend("What is revenue by region?")}
                      className="card card-interactive p-3"
                    >
                      <div className="text-xs font-medium text-emerald-600 mb-1">Breakdown</div>
                      <div className="text-sm text-slate-700">Break down revenue by region</div>
                    </button>
                    {hasKb && (
                      <button
                        onClick={() => handleSend("What is the standard trade promotion discount limit?")}
                        className="card card-interactive p-3"
                      >
                        <div className="text-xs font-medium text-violet-600 mb-1">Knowledge</div>
                        <div className="text-sm text-slate-700">What is the trade promotion limit?</div>
                      </button>
                    )}
                    <button
                      onClick={() => handleSend("Compare performance across datasets")}
                      className="card card-interactive p-3"
                    >
                      <div className="text-xs font-medium text-amber-600 mb-1">Comparison</div>
                      <div className="text-sm text-slate-700">Compare performance across datasets</div>
                    </button>
                  </div>
                )}

                {!hasData && !hasKb && (
                  <a
                    href="/data-center"
                    className="btn-primary inline-flex"
                  >
                    <span>Go to Data Center</span>
                  </a>
                )}
              </div>
            </div>
          ) : (
            /* ── Messages ── */
            <div className="max-w-4xl mx-auto px-6 py-6 space-y-5">
              {messages.map((msg, i) => (
                <div key={i} className="animate-fade-in">
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="max-w-[80%] msg-user">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="msg-ai">
                      {(msg as any)._streaming ? (
                        <div>
                          {msg.result && (
                            <div className="flex items-center gap-2 mb-3">
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[0.65rem] font-semibold bg-brand-50 text-brand-600 border border-brand-200/60 animate-pulse">
                                <Loader2 className="w-3 h-3 animate-spin" />
                                STREAMING
                                {elapsed > 0 && (
                                  <span className="ml-1 text-brand-400 font-normal">{elapsed}s</span>
                                )}
                              </span>
                            </div>
                          )}
                          <div className="text-sm text-slate-700 leading-relaxed">
                            {msg.content || (
                              <div className="flex items-center gap-2 text-slate-400 py-2">
                                <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
                                <span className="text-sm">Thinking{elapsed > 5 ? ` (${elapsed}s)` : ""}...</span>
                              </div>
                            )}
                            {msg.content && (
                              <span className="inline-block w-0.5 h-4 bg-brand-500 animate-pulse ml-0.5 align-middle" />
                            )}
                          </div>
                        </div>
                      ) : (msg as any)._error ? (
                        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
                          <div className="flex items-start gap-2">
                            <AlertCircle className="w-4 h-4 text-rose-500 mt-0.5 flex-shrink-0" />
                            <div className="flex-1">
                              <p className="text-sm font-medium text-rose-700">Unable to complete request</p>
                              <p className="text-xs text-rose-600 mt-1">
                                {error || "The request failed. Please try again."}
                              </p>
                              <button
                                onClick={() => handleSend(messages.find(m => m.role === "user")?.content || "")}
                                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-rose-600 hover:text-rose-800"
                              >
                                <RotateCcw className="w-3 h-3" />
                                Retry
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : msg.result ? (
                        <AnalystResponse
                          answer={msg.content}
                          queryType={msg.result.query_type}
                          visualization={msg.result.visualization as any}
                          sources={msg.result.sources}
                          evidence={msg.result.evidence as any}
                          metrics={msg.result.metrics}
                          onFollowUp={(q) => handleSend(q)}
                        />
                      ) : (
                        <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
                          {msg.content}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {loading && messages.length > 0 && !messages.some((m) => (m as any)._streaming) && (
                <div className="animate-fade-in">
                  <div className="msg-ai">
                    <div className="flex items-center gap-3 text-slate-500">
                      <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
                      <span className="text-sm">Analyzing your question...</span>
                      {elapsed > 5 && (
                        <span className="text-xs text-slate-400">({elapsed}s)</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Error Banner */}
        {error && !messages.some(m => (m as any)._error) && (
          <div className="mx-6 mb-2 flex items-center gap-2 px-4 py-2.5 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700 animate-fade-in">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-600">
              ×
            </button>
          </div>
        )}

        {/* Composer */}
        <div className="border-t border-slate-200/80 bg-white px-6 py-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    hasData || hasKb
                      ? "Ask a business question..."
                      : "Upload data first, then ask questions here..."
                  }
                  disabled={loading}
                  rows={1}
                  className="input-field resize-none"
                  style={{ minHeight: "44px", maxHeight: "120px" }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = "auto";
                    target.style.height = Math.min(target.scrollHeight, 120) + "px";
                  }}
                />
              </div>
              {loading ? (
                <button
                  onClick={stopGenerating}
                  className="flex items-center justify-center w-11 h-11 rounded-xl bg-rose-500 text-white hover:bg-rose-600 shadow-sm transition-all shrink-0"
                  title="Stop generating"
                >
                  <Square className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim()}
                  className={cn(
                    "flex items-center justify-center w-11 h-11 rounded-xl transition-all shrink-0",
                    input.trim()
                      ? "bg-brand-600 text-white hover:bg-brand-700 shadow-sm"
                      : "bg-slate-100 text-slate-400 cursor-not-allowed"
                  )}
                >
                  <Send className="w-4 h-4" />
                </button>
              )}
            </div>
            {!(hasData || hasKb) && (
              <p className="text-xs text-slate-400 mt-2">
                Connect data sources or upload documents to start asking questions.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
