"use client";

import { useState, useEffect, useRef } from "react";
import {
  Send,
  Plus,
  History,
  Copy,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Loader2,
  MessageSquare,
  FileText,
  Database,
  AlertTriangle,
  Sparkles,
} from "lucide-react";
import {
  sendQuery,
  getDataStatus,
  listConversations,
  createConversation,
  getConversation,
  addMessage,
  deleteConversation,
} from "@/lib/api/client";
import { cn, getQueryTypeVariant, truncate } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { EmptyState } from "@/components/common/EmptyState";

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
  const [expandedEvidence, setExpandedEvidence] = useState<Record<number, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Check data status
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

  // Load conversations
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

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;

    const userMessage: Message = { role: "user", content: q };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      // Create conversation if needed
      if (!currentConvId) {
        const conv = await createConversation();
        setCurrentConvId(conv.id);
      }

      // Add user message to conversation
      if (currentConvId) {
        await addMessage(currentConvId, { role: "user", content: q });
      }

      // Send query
      const result = await sendQuery(q);
      const assistantMessage: Message = {
        role: "assistant",
        content: result.answer,
        result,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Add assistant message to conversation
      if (currentConvId) {
        await addMessage(currentConvId, {
          role: "assistant",
          content: result.answer,
          result,
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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const getSuggestions = () => {
    const suggestions: string[] = [];
    if (hasData) {
      suggestions.push(
        "Which category generated the highest revenue?",
        "Why did Electronics revenue decline in Q2?",
        "Which campaign has the highest ROAS?",
        "Which customer segment has the highest LTV?"
      );
    }
    if (hasKb) {
      suggestions.push(
        "What does the marketing strategy recommend?",
        "What discount policy does the pricing policy specify?"
      );
    }
    return suggestions;
  };

  return (
    <div className="flex h-full">
      {/* History Sidebar */}
      {showHistory && (
        <div className="w-72 border-r border-slate-200 bg-white flex flex-col shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <span className="text-sm font-semibold text-slate-900">History</span>
            <button
              onClick={() => setShowHistory(false)}
              className="text-slate-400 hover:text-slate-600"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-slate-400">
                No conversations yet
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={cn(
                    "px-4 py-3 border-b border-slate-100 cursor-pointer hover:bg-slate-50 transition-colors",
                    currentConvId === conv.id && "bg-brand-50"
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
                      className="text-xs text-slate-400 hover:text-rose-500"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-brand-600" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900">AI Analyst</h1>
              <p className="text-xs text-slate-400">
                Ask anything about your data
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
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 && !loading ? (
            <div className="max-w-2xl mx-auto py-12">
              <EmptyState
                icon="🤖"
                title="What can I help you analyze?"
                description="Ask questions about your sales data, marketing campaigns, customer segments, or uploaded documents."
              />
              {getSuggestions().length > 0 && (
                <div className="mt-8 space-y-2">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                    Suggested questions
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {getSuggestions().map((s, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          setInput(s);
                          inputRef.current?.focus();
                        }}
                        className="text-left px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((msg, i) => (
                <div key={i} className="animate-fade-in">
                  {msg.role === "user" ? (
                    <div className="msg-user">
                      <span className="font-semibold text-slate-700">You: </span>
                      {msg.content}
                    </div>
                  ) : (
                    <div>
                      <div className="msg-ai">
                        {/* Classification */}
                        {msg.result && (
                          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-slate-100">
                            <span
                              className={cn(
                                "badge",
                                getQueryTypeVariant(msg.result.query_type)
                              )}
                            >
                              {msg.result.query_type.toUpperCase()}
                            </span>
                            <span className="text-xs text-slate-400">
                              {(msg.result.metrics?.end_to_end_latency_ms as number)?.toFixed(0) || 0}ms
                            </span>
                          </div>
                        )}

                        {/* Answer */}
                        <div className="leading-relaxed whitespace-pre-wrap">
                          {msg.content}
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-100">
                          <button
                            onClick={() => copyToClipboard(msg.content)}
                            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                      </div>

                      {/* Evidence Panel */}
                      {msg.result && (
                        <div className="mt-2">
                          <button
                            onClick={() =>
                              setExpandedEvidence((prev) => ({
                                ...prev,
                                [i]: !prev[i],
                              }))
                            }
                            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors w-full"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            Evidence ({msg.result.sources?.length || 0} sources)
                            {expandedEvidence[i] ? (
                              <ChevronUp className="w-3.5 h-3.5 ml-auto" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5 ml-auto" />
                            )}
                          </button>

                          {expandedEvidence[i] && (
                            <div className="mt-2 bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-3 animate-fade-in">
                              {/* Sources */}
                              {msg.result.sources?.map((s, j) => (
                                <div key={j} className="flex items-center gap-2">
                                  {s.type === "knowledge_base" ? (
                                    <FileText className="w-3.5 h-3.5 text-violet-500 shrink-0" />
                                  ) : (
                                    <Database className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                  )}
                                  <span className="text-sm font-medium text-slate-700">
                                    {s.source}
                                  </span>
                                  <Badge
                                    variant={
                                      s.type === "knowledge_base"
                                        ? "violet"
                                        : "success"
                                    }
                                  >
                                    {s.type === "knowledge_base" ? "Doc" : "Data"}
                                  </Badge>
                                </div>
                              ))}

                              {/* Knowledge Chunks */}
                              {msg.result.evidence?.knowledge_base_chunks?.map(
                                (chunk, j) => (
                                  <div
                                    key={j}
                                    className="evidence-item"
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium text-slate-700">
                                        {chunk.source}
                                      </span>
                                      <span className="text-xs text-brand-500">
                                        relevance: {chunk.relevance_score}
                                      </span>
                                    </div>
                                    <div className="text-xs text-slate-500 mt-1">
                                      {truncate(chunk.text, 300)}
                                    </div>
                                  </div>
                                )
                              )}

                              {/* Structured Data */}
                              {msg.result.evidence?.structured_data && (
                                <div>
                                  <p className="text-xs font-semibold text-slate-500 mb-1">
                                    Structured Data:
                                  </p>
                                  <pre className="text-xs text-slate-600 bg-white rounded p-2 border border-slate-200 overflow-x-auto">
                                    {JSON.stringify(
                                      msg.result.evidence.structured_data,
                                      null,
                                      2
                                    )}
                                  </pre>
                                </div>
                              )}

                              {/* Conflict Warning */}
                              {msg.result.evidence?.detected_conflict && (
                                <div className="flex items-start gap-2 p-2 rounded bg-amber-50 border border-amber-200">
                                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                                  <span className="text-xs text-amber-700">
                                    {msg.result.evidence.detected_conflict.note}
                                  </span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Loading Indicator */}
              {loading && (
                <div className="msg-ai animate-fade-in">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Analyzing your question...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-200 bg-white px-6 py-4">
          <div className="max-w-3xl mx-auto">
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
                  className="w-full resize-none rounded-lg border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ minHeight: "44px", maxHeight: "120px" }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = "auto";
                    target.style.height = Math.min(target.scrollHeight, 120) + "px";
                  }}
                />
              </div>
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className={cn(
                  "flex items-center justify-center w-10 h-10 rounded-lg transition-colors shrink-0",
                  input.trim() && !loading
                    ? "bg-brand-600 text-white hover:bg-brand-700"
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
