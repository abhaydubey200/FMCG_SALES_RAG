"use client";

import { useState, useEffect, useRef } from "react";
import {
  Send,
  Plus,
  History,
  Sparkles,
  Loader2,
  Trash2,
  Brain,
} from "lucide-react";
import {
  sendQuery,
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
}

interface Conversation {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  const loadConversations = async () => {
    try {
      const data = await listConversations();
      setConversations(data.conversations);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (overrideInput?: string) => {
    const q = (overrideInput || input).trim();
    if (!q || loading) return;

    const userMessage: Message = { role: "user", content: q };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      if (!currentConvId) {
        const conv = await createConversation();
        setCurrentConvId(conv.id);
      }

      if (currentConvId) {
        await addMessage(currentConvId, { role: "user", content: q });
      }

      // Add a placeholder for the streaming response
      let streamedContent = "";
      let streamMetadata: { query_type?: string; sources?: Array<{ type: string; source: string }>; visualization?: Record<string, unknown>; agents_used?: string[]; skills_used?: string[]; plan_steps?: number; classification_reason?: string } = {};

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", result: undefined, _streaming: true } as Message,
      ]);

      try {
        for await (const event of aiQueryStream(q)) {
          if (event.type === "metadata") {
            const meta = event as Extract<StreamEvent, { type: "metadata" }>;
            streamMetadata = {
              query_type: meta.query_type,
              sources: meta.sources,
              visualization: meta.visualization as Record<string, unknown>,
              agents_used: (meta as any).agents_used || [],
              skills_used: (meta as any).skills_used || [],
              plan_steps: (meta as any).plan_steps || 0,
              classification_reason: (meta as any).classification_reason || "",
            };
            // Update the streaming message with metadata
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && (last as any)._streaming) {
                updated[updated.length - 1] = {
                  ...last,
                  result: {
                    answer: "",
                    query_type: meta.query_type,
                    sources: meta.sources,
                    metrics: {},
                    evidence: {},
                    visualization: meta.visualization as any,
                  },
                };
              }
              return updated;
            });
          } else if (event.type === "token") {
            const token = event as Extract<StreamEvent, { type: "token" }>;
            streamedContent += token.content;
            const content = streamedContent;
            // Update the streaming message with new content
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
          } else if (event.type === "done") {
            const done = event as Extract<StreamEvent, { type: "done" }>;
            // Finalize the streaming message
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && (last as any)._streaming) {
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: done.answer,
                  result: {
                    answer: done.answer,
                    query_type: (done.metrics as any)?.query_type || streamMetadata?.query_type || "analytical",
                    sources: streamMetadata?.sources || [],
                    metrics: done.metrics,
                    evidence: {},
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
      } catch (streamError) {
        // If streaming fails, fall back to non-streaming query
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && (updated[lastIdx] as any)._streaming) {
            updated.pop(); // remove streaming placeholder
          }
          return updated;
        });
        const result = await aiQuery(q);
        const assistantMessage: Message = {
          role: "assistant",
          content: result.answer,
          result: result as Message["result"],
        };
        setMessages((prev) => [...prev, assistantMessage]);
      }

      if (currentConvId) {
        // Get the final assistant message for persistence
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.result) {
            addMessage(currentConvId, {
              role: "assistant",
              content: last.content,
              result: last.result,
            });
          }
          return prev;
        });
      }

      loadConversations();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Unable to process the query. Please check that the API is running and data is available.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setCurrentConvId(null);
  };

  const handleLoadConversation = async (conv: Conversation) => {
    try {
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

  return (
    <div className="flex h-full bg-slate-50">
      {/* History Sidebar */}
      {showHistory && (
        <div className="w-72 border-r border-slate-200 bg-white flex flex-col shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <span className="text-sm font-semibold text-slate-900">
              Conversations
            </span>
            <button
              onClick={() => setShowHistory(false)}
              className="text-slate-400 hover:text-slate-600 p-1"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-slate-400">
                No conversations yet
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={cn(
                    "px-4 py-3 border-b border-slate-100 cursor-pointer hover:bg-slate-50 transition-colors group",
                    currentConvId === conv.id && "bg-brand-50 border-l-2 border-l-brand-500"
                  )}
                  onClick={() => handleLoadConversation(conv)}
                >
                  <div className="text-sm font-medium text-slate-900 truncate">
                    {conv.title}
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-slate-400">
                      {conv.message_count} messages
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteConversation(conv.id);
                      }}
                      className="text-xs text-slate-400 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900">
                AI Analyst
              </h1>
              <p className="text-xs text-slate-400">
                Decision Intelligence Workspace
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors",
                showHistory
                  ? "bg-brand-50 text-brand-700 border-brand-200"
                  : "text-slate-600 border-slate-200 hover:bg-slate-50"
              )}
            >
              <History className="w-3.5 h-3.5" />
              History
            </button>
            <button
              onClick={handleNewChat}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-600 border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              New Chat
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {isEmpty ? (
            /* Empty State — no hardcoded prompts, only contextual guidance */
            <div className="max-w-2xl mx-auto px-6 py-16">
              <div className="text-center mb-10">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="w-7 h-7 text-white" />
                </div>
                <h2 className="text-xl font-bold text-slate-900 mb-2">
                  What would you like to analyze?
                </h2>
                {hasData || hasKb ? (
                  <p className="text-sm text-slate-500 max-w-md mx-auto">
                    Ask questions about your uploaded data. The analyst will
                    dynamically discover what metrics, dimensions, and
                    documents are available and answer from real data.
                  </p>
                ) : (
                  <p className="text-sm text-slate-500 max-w-md mx-auto">
                    Upload structured data (CSV/Excel) or documents (PDF/DOCX/TXT)
                    in the Data Center, then come back to ask business questions.
                  </p>
                )}
              </div>
            </div>
          ) : (
            /* Messages */
            <div className="max-w-4xl mx-auto px-6 py-6 space-y-6">
              {messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="max-w-[80%] bg-brand-600 text-white rounded-2xl rounded-tr-md px-4 py-2.5 text-sm">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-md px-5 py-4 shadow-sm">
                      {(msg as any)._streaming ? (
                        /* Streaming response — show tokens as they arrive */
                        <div>
                          {msg.result && (
                            <div className="flex items-center gap-2 mb-3">
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border bg-brand-50 text-brand-700 border-brand-200 animate-pulse">
                                STREAMING
                              </span>
                              <Loader2 className="w-3 h-3 animate-spin text-brand-400" />
                            </div>
                          )}
                          <div className="prose prose-sm max-w-none text-slate-700 leading-relaxed">
                            {msg.content || (
                              <div className="flex items-center gap-2 text-slate-400">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span className="text-sm">Thinking...</span>
                              </div>
                            )}
                            {msg.content && (
                              <span className="inline-block w-0.5 h-4 bg-brand-500 animate-pulse ml-0.5 align-middle" />
                            )}
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
                <div>
                  <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-md px-5 py-4 shadow-sm">
                    <div className="flex items-center gap-3 text-slate-500">
                      <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
                      <span className="text-sm">
                        Analyzing your question...
                      </span>
                    </div>
                    <div className="mt-3 space-y-1.5">
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        <div className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
                        Classifying query intent
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Retrieving evidence from data sources
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="border-t border-slate-200 bg-white px-6 py-4">
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
                  className="w-full resize-none rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ minHeight: "48px", maxHeight: "120px" }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = "auto";
                    target.style.height =
                      Math.min(target.scrollHeight, 120) + "px";
                  }}
                />
              </div>
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                className={cn(
                  "flex items-center justify-center w-11 h-11 rounded-xl transition-all shrink-0",
                  input.trim() && !loading
                    ? "bg-brand-600 text-white hover:bg-brand-700 shadow-sm"
                    : "bg-slate-100 text-slate-400 cursor-not-allowed"
                )}
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
            {!(hasData || hasKb) && (
              <p className="text-xs text-slate-400 mt-2">
                Connect data sources or upload documents to start asking
                questions.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
