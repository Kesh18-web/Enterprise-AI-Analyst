"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  Brain,
  ShieldCheck,
  Zap,
  Search,
  FileText,
  CheckCircle2,
  RotateCcw,
  Scale,
  Activity,
  Layers,
  Database,
  Upload,
  Bot,
  Sparkles,
  Terminal,
  ChevronRight,
  Plus,
  MessageSquare,
  Trash2,
  Send,
  Paperclip,
  File as FileIcon,
  Globe,
  Check,
  ChevronDown,
  Cpu,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface NodeEvent {
  node: string;
  trace_id?: string;
  safe?: boolean;
  sub_tasks?: string[];
  requires_mcp?: boolean;
  mcp_tools?: string[];
  mcp_results?: Record<string, any>;
  selected_model?: string;
  chunk_count?: number;
  confidence?: number;
  critique?: string;
  eval_scores?: Record<string, number>;
}

interface Citation {
  citation_id: number;
  source_name: string;
  page_number?: number;
  snippet: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  attachedFile?: string; // filename if user uploaded a file
  // Only set on assistant messages
  citations?: Citation[];
  evalScores?: Record<string, number> | null;
  telemetry?: any;
  nodeEvents?: NodeEvent[];
  cacheHit?: boolean;
  cacheType?: string;
  memoryCompacted?: boolean;
  searchScope?: "session" | "global";
  uploadStatus?: "success" | "skipped";
}

interface ChatSession {
  id: string; // This IS the session_id sent to backend
  name: string;
  createdAt: number;
  messages: ChatMessage[];
  searchScope: "session" | "global";
  attachedFiles: string[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genId(): string {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

function createChat(name = "New Chat"): ChatSession {
  return {
    id: genId(),
    name,
    createdAt: Date.now(),
    messages: [],
    searchScope: "session",
    attachedFiles: [],
  };
}

function createInitialChat(): ChatSession {
  return {
    id: genId(),
    name: "Chat 1",
    createdAt: Date.now(),
    messages: [],
    searchScope: "session",
    attachedFiles: [],
  };
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function AnalystWorkbench() {
  const { user, idToken, loading: authLoading, signOut } = useAuth();
  const router = useRouter();

  // Auth Guard: Redirect unauthenticated users to /login
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [user, authLoading, router]);
  
  const getAuthHeaders = useCallback((extra = {}) => ({
    "Authorization": `Bearer ${idToken}`,
    ...extra
  }), [idToken]);

  const [activeTab, setActiveTab] = useState<
    "workbench" | "indexing" | "observability" | "architect"
  >("workbench");

  // ── Chat State (Firestore Backend Sync) ────────────────────────────────────
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string>("session-init-1");
  const activeChat = chats.find((c) => c.id === activeChatId) ?? chats[0];

  // Helper to load messages for a specific session from Firestore
  const loadMessagesForSession = useCallback(async (sessionId: string) => {
    if (!sessionId || sessionId === "undefined") return;
    try {
      const res = await fetch(`http://localhost:8000/api/v1/sessions/${sessionId}/messages`, {
        headers: getAuthHeaders(),
      }).catch(() => null);
      if (res && res.ok) {
        const data = await res.json().catch(() => null);
        if (data && data.messages && Array.isArray(data.messages)) {
          const parsedMsgs = data.messages.map((m: any) => ({
            ...m,
            cacheHit: m.cacheHit ?? m.semantic_cache_hit ?? false,
            cacheType: m.cacheType ?? m.cache_type ?? "semantic_vector",
            nodeEvents: m.nodeEvents ?? m.node_execution_logs ?? [],
          }));
          setChats((prev) =>
            prev.map((c) => (c.id === sessionId ? { ...c, messages: parsedMsgs } : c))
          );
        }
      }
    } catch (err) {
      console.warn(`Could not load messages for session [${sessionId}]:`, err);
    }
  }, [getAuthHeaders]);

  // Fetch all chat sessions from Firestore API on mount
  useEffect(() => {
    if (!idToken) return;
    const fetchSessions = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v1/sessions").catch(() => null);
        if (res && res.ok) {
          const data = await res.json().catch(() => null);
          if (data && data.sessions && Array.isArray(data.sessions) && data.sessions.length > 0) {
            const validSessions = data.sessions.filter((s: any) => s && s.id && s.id !== "undefined");
            if (validSessions.length > 0) {
              const apiSessions: ChatSession[] = validSessions.map((s: any) => ({
                id: s.id,
                name: s.name || "Chat",
                createdAt: s.createdAt || Date.now(),
                messages: [],
                searchScope: s.searchScope || "session",
                attachedFiles: s.attachedFiles || [],
              }));
              setChats(apiSessions);
              const targetId = apiSessions[0].id;
              setActiveChatId(targetId);
              loadMessagesForSession(targetId);
            }
          } else {
            // First time setup — seed initial fresh chat in Firestore for this user
            const freshChat = createInitialChat();
            await fetch("http://localhost:8000/api/v1/sessions", {
              method: "POST",
              headers: getAuthHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({
                id: freshChat.id,
                name: freshChat.name,
                searchScope: freshChat.searchScope,
                attachedFiles: freshChat.attachedFiles,
              }),
            }).catch(() => null);
            setChats([freshChat]);
            setActiveChatId(freshChat.id);
          }
        }
      } catch (err) {
        console.warn("Firestore API offline or loading:", err);
      }
    };
    fetchSessions();
  }, [loadMessagesForSession]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const labFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages]);

  // ── Sidebar Expansion State ───────────────────────────────────────────────
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  // ── Toast Notification State ───────────────────────────────────────────────
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 2000);
  };

  // ── Health ─────────────────────────────────────────────────────────────────
  const [backendStatus, setBackendStatus] = useState<any>(null);
  useEffect(() => {
    fetch("http://localhost:8000/api/v1/health")
      .then((r) => r.json())
      .then((d) => setBackendStatus(d))
      .catch(() => setBackendStatus({ status: "offline" }));
  }, []);

  // ── Workbench Query State ──────────────────────────────────────────────────
  const [query, setQuery] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [hitlMode, setHitlMode] = useState(false);

  // Model selector: 'auto' | 'flash' | 'pro' | 'groq'
  type ModelPreference = "auto" | "flash" | "pro" | "groq";
  const [modelPreference, setModelPreference] = useState<ModelPreference>("auto");
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);

  const MODEL_OPTIONS: { value: ModelPreference; label: string; desc: string; color: string; dotColor: string }[] = [
    { value: "auto",  label: "Auto",     desc: "Automatic model selection", color: "text-slate-200", dotColor: "bg-indigo-400" },
    { value: "flash", label: "Fast",     desc: "High-speed responses",     color: "text-slate-200", dotColor: "bg-slate-400" },
    { value: "pro",   label: "Pro",      desc: "Deep reasoning engine",     color: "text-slate-200", dotColor: "bg-slate-400" },
    { value: "groq",  label: "Ultra",    desc: "Maximum throughput",        color: "text-slate-200", dotColor: "bg-slate-400" },
  ];
  const activeModel = MODEL_OPTIONS.find((m) => m.value === modelPreference) ?? MODEL_OPTIONS[0];

  // Live node stepper state (only for the in-progress run)
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [nodeEvents, setNodeEvents] = useState<NodeEvent[]>([]);
  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [hitlRequired, setHitlRequired] = useState(false);
  const [hitlApproved, setHitlApproved] = useState(false);
  const [runningExplainabilityReason, setRunningExplainabilityReason] = useState("");

  // ── Chat helpers ───────────────────────────────────────────────────────────
  const updateChat = useCallback(
    (chatId: string, updater: (c: ChatSession) => ChatSession) => {
      setChats((prev) => prev.map((c) => (c.id === chatId ? updater(c) : c)));
    },
    []
  );

  const toggleSearchScope = async () => {
    const nextScope = activeChat.searchScope === "session" ? "global" : "session";
    updateChat(activeChat.id, (c) => ({ ...c, searchScope: nextScope }));
    try {
      await fetch(`http://localhost:8000/api/v1/sessions/${activeChat.id}`, {
        method: "PATCH",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ searchScope: nextScope }),
      });
    } catch (err) {
      console.error("Error updating searchScope in Firestore:", err);
    }
  };

  const addNewChat = async () => {
    const n = chats.length + 1;
    const chat = createChat(`Chat ${n}`);
    setChats((prev) => [...prev, chat]);
    setActiveChatId(chat.id);
    setQuery("");
    setActiveNode(null);
    setNodeEvents([]);
    setLatestTelemetry(null);
    setRunningExplainabilityReason("");
    setHitlRequired(false);

    try {
      await fetch("http://localhost:8000/api/v1/sessions", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          id: chat.id,
          name: chat.name,
          searchScope: chat.searchScope,
          attachedFiles: chat.attachedFiles,
        }),
      });
    } catch (err) {
      console.error("Error saving new chat to Firestore:", err);
    }
  };

  const deleteChat = async (chatId: string) => {
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== chatId);
      if (next.length === 0) {
        const fresh = createChat("Chat 1");
        setActiveChatId(fresh.id);
        return [fresh];
      }
      if (activeChatId === chatId) {
        setActiveChatId(next[0].id);
        loadMessagesForSession(next[0].id);
      }
      return next;
    });

    try {
      await fetch(`http://localhost:8000/api/v1/sessions/${chatId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
    } catch (err) {
      console.error("Error deleting session from Firestore:", err);
    }
  };

  const switchChat = (chatId: string) => {
    setActiveChatId(chatId);
    setActiveNode(null);
    setNodeEvents([]);
    setRunningExplainabilityReason("");
    setHitlRequired(false);
    loadMessagesForSession(chatId);
  };

  // Auto-name chat after first message — calls Gemini Flash to generate a clean, ChatGPT-style title
  const autoNameChat = async (chatId: string, firstQuery: string) => {
    if (!firstQuery.trim()) return;
    try {
      const res = await fetch(`http://localhost:8000/api/v1/sessions/${chatId}/generate-name`, {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ query: firstQuery }),
      });
      if (res.ok) {
        const data = await res.json();
        const name = data.name || firstQuery.slice(0, 40);
        setChats((prev) =>
          prev.map((c) => (c.id === chatId ? { ...c, name } : c))
        );
      }
    } catch (err) {
      // Fallback: truncate query
      const name = firstQuery.length > 40 ? firstQuery.slice(0, 40) + "…" : firstQuery;
      setChats((prev) =>
        prev.map((c) => (c.id === chatId ? { ...c, name } : c))
      );
    }
  };

  // ── In-Chat File Upload Handler ───────────────────────────────────────────
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", activeChat.id); // In-chat upload tagged to current chat!

    try {
      const res = await fetch("http://localhost:8000/api/v1/documents/upload", {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Upload failed");
      }

      const data = await res.json();
      const isSkipped = data.status === "skipped";

      if (isSkipped) {
        showToast("Document already uploaded in this session");
      } else {
        showToast("File uploaded successfully");
      }

      // Auto-name chat if empty
      if (activeChat.messages.length === 0) {
        autoNameChat(activeChat.id, `Doc: ${file.name}`);
      }

      // Record file attachment in chat thread
      const attachMsg: ChatMessage = {
        id: genId(),
        role: "user",
        content: isSkipped ? `Uploaded document (duplicate): ${file.name}` : `Uploaded document: ${file.name}`,
        timestamp: new Date(),
        attachedFile: file.name,
        searchScope: activeChat.searchScope,
        uploadStatus: isSkipped ? "skipped" : "success",
      };

      updateChat(activeChat.id, (c) => ({
        ...c,
        attachedFiles: c.attachedFiles?.includes(file.name) ? c.attachedFiles : [...(c.attachedFiles || []), file.name],
        messages: [...c.messages, attachMsg],
      }));
    } catch (err: any) {
      console.error("File upload error:", err);
      const isFetchErr = err?.message === "Failed to fetch" || err?.name === "TypeError";
      const userErrMsg = isFetchErr
        ? "Backend server starting up. Please try uploading again in a few seconds."
        : `Upload failed: ${err.message || err}`;
      showToast(userErrMsg);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // ── handleAnalyze ──────────────────────────────────────────────────────────
  const handleAnalyze = async () => {
    if (!query.trim() || isAnalyzing) return;

    const chat = activeChat;
    const sessionId = chat.id; // Stable UUID per chat
    const userMsgId = genId();
    const userMsg: ChatMessage = {
      id: userMsgId,
      role: "user",
      content: query.trim(),
      timestamp: new Date(),
      searchScope: chat.searchScope,
    };

    // Auto-name on first message
    if (chat.messages.length === 0) autoNameChat(chat.id, query.trim());

    updateChat(chat.id, (c) => ({ ...c, messages: [...c.messages, userMsg] }));
    setQuery("");

    // Persist user message directly into Firestore database
    try {
      fetch(`http://localhost:8000/api/v1/sessions/${chat.id}/messages`, {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(userMsg),
      }).catch((e) => console.error("Error saving user message to Firestore:", e));
    } catch (_) {}

    setIsAnalyzing(true);
    setActiveNode("guardrail");
    setNodeEvents([]);
    setRunningExplainabilityReason("");
    setHitlRequired(false);
    setHitlApproved(false);

    const collectedNodeEvents: any[] = [];
    let completePayload: any = null;
    let hitlPayload: any = null;

    try {
      const response = await fetch("http://localhost:8000/api/v1/analyze/stream", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          query: userMsg.content,
          session_id: sessionId,
          search_scope: chat.searchScope,
          hitl_mode: hitlMode,
          model_preference: modelPreference,
        }),
      });

      if (!response.body) throw new Error("ReadableStream not supported");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\n\s*\n/);
        buffer = parts.pop() || "";

        for (const part of parts) {
          for (const line of part.split("\n")) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const jsonStr = trimmed.replace(/^data:\s*/, "").trim();
            if (!jsonStr || (!jsonStr.startsWith("{") && !jsonStr.startsWith("[")))
              continue;
            try {
              const data = JSON.parse(jsonStr);
              if (data.event === "node_complete") {
                collectedNodeEvents.push(data);
                setActiveNode(data.node);
                setNodeEvents((prev) => [...prev, data]);
              } else if (data.event === "hitl_approval_required") {
                hitlPayload = data;
                setHitlRequired(true);
              } else if (data.event === "complete") {
                completePayload = data;
              }
            } catch {
              /* ignore parse errors */
            }
          }
        }
      }

      // Immediately display response when stream completes
      if (completePayload) {
        setLatestTelemetry(completePayload.telemetry || null);
        setActiveNode("complete");

        const assistantMsg: ChatMessage = {
          id: genId(),
          role: "assistant",
          content: completePayload.report || "",
          timestamp: new Date(),
          citations: completePayload.citations || [],
          evalScores: completePayload.eval_scores || null,
          telemetry: completePayload.telemetry || null,
          nodeEvents: collectedNodeEvents,
          cacheHit: completePayload.semantic_cache_hit || false,
          cacheType: completePayload.cache_type || "semantic_vector",
          memoryCompacted: completePayload.memory_compacted || false,
          searchScope: chat.searchScope,
        };

        updateChat(chat.id, (c) => ({ ...c, messages: [...c.messages, assistantMsg] }));
      }
      setIsAnalyzing(false);
    } catch (err: any) {
      console.error("Stream analysis error:", err);
      setIsAnalyzing(false);
      setActiveNode(null);
      const errorMsg: ChatMessage = {
        id: genId(),
        role: "assistant",
        content: "⚠️ **Backend Connection Error**: The backend API is currently starting up or offline. Please wait a few seconds and try sending your query again.",
        timestamp: new Date(),
        searchScope: chat.searchScope,
      };
      updateChat(chat.id, (c) => ({ ...c, messages: [...c.messages, errorMsg] }));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAnalyze();
    }
  };

  // ── Document Indexing Lab (Global Workspace) ────────────────────────────────
  const [docTitle, setDocTitle] = useState("");
  const [docSource, setDocSource] = useState("");
  const [docContent, setDocContent] = useState("");
  const [indexingStatus, setIndexingStatus] = useState<string | null>(null);

  const handleIndexDocument = async () => {
    if (!docTitle || !docContent) return;
    setIndexingStatus("Indexing chunks into Global Workspace Knowledge...");
    try {
      const res = await fetch("http://localhost:8000/api/v1/documents/index", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          title: docTitle,
          source_name: docSource || "Lab Document",
          content: docContent,
          session_id: "global_workspace", // Global Lab documents tagged to global_workspace!
        }),
      });
      const data = await res.json();
      setIndexingStatus(
        `✅ Indexed '${data.title}' into Global Workspace Knowledge Base (ID: ${data.doc_id}, Chunks: ${data.chunks_indexed})`
      );
      showToast("Document uploaded successfully");
      setDocTitle("");
      setDocSource("");
      setDocContent("");
    } catch (e) {
      setIndexingStatus(`Error: ${e}`);
    }
  };

  // ── Architect State ────────────────────────────────────────────────────────
  const [architectPrompt, setArchitectPrompt] = useState(
    "I need a Legal Compliance Assistant that reads Confluence, searches GitHub, answers policy questions, remembers previous conversations and posts reports to Slack."
  );
  const [architectResult, setArchitectResult] = useState<any>(null);

  const handleGenerateArchitecture = () => {
    setArchitectResult({
      topology: "Cyclic LangGraph Multi-Agent Architecture",
      scaffold_dir: "scaffolds/legal_compliance_assistant/",
      components: [
        { name: "Guardrail Agent", type: "Security", model: "Groq/Llama-3" },
        { name: "Confluence Search Tool", type: "MCP Capability", endpoint: "mcp://confluence" },
        { name: "GitHub Repository Search", type: "MCP Capability", endpoint: "mcp://github" },
        { name: "Policy Analysis Agent", type: "Cognitive", model: "Claude-3-5-Sonnet" },
        { name: "Slack Notification Tool", type: "MCP Capability", endpoint: "mcp://slack" },
      ],
      nodes: ["Guardrail", "Planner", "ConfluenceRetriever", "GitHubRetriever", "Analyzer", "SlackPublisher"],
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen flex-col bg-[#090d16] text-slate-100 overflow-hidden relative">
      {/* 2-Second Top Right Toast Notification */}
      {toastMessage && (
        <div className="absolute top-4 right-6 z-50 flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xl border border-emerald-400/30 animate-bounce">
          <Check className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Navbar */}
      <header className="flex h-16 items-center border-b border-slate-800 bg-slate-950/80 px-6 backdrop-blur justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 shadow-lg shadow-indigo-500/20">
            <Brain className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-lg font-bold tracking-tight text-white">Enterprise AI Analyst</h1>
        </div>

        {/* System Telemetry Badges */}
        {(() => {
          const lastAssistantMsg = activeChat?.messages.filter((m) => m.role === "assistant").slice(-1)[0];
          const activeTelemetry = latestTelemetry || lastAssistantMsg?.telemetry;
          const tokens = activeTelemetry?.total_tokens ?? 0;
          const cost = activeTelemetry?.formatted_cost ?? (activeTelemetry?.total_cost ? `$${Number(activeTelemetry.total_cost).toFixed(6)}` : "$0.000000");

          return (
            <div className="flex items-center gap-3 text-xs">
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 rounded-lg bg-cyan-500/10 px-3 py-1.5 border border-cyan-500/30 text-cyan-300">
                  <Terminal className="h-3.5 w-3.5 text-cyan-400" />
                  <span>{tokens} Tokens</span>
                </div>
                <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 border border-emerald-500/30 text-emerald-400 font-semibold">
                  <span>{cost}</span>
                </div>
              </div>
            </div>
          );
        })()}
      </header>

      {/* Main Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <aside className={`${sidebarExpanded ? "w-96" : "w-64"} border-r border-slate-800 bg-slate-950/60 flex flex-col transition-all duration-300`}>
          {/* Platform Modules */}
          <div className="p-4 space-y-1 border-b border-slate-800">
            <div className="flex items-center justify-between px-1 mb-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Platform Modules
              </p>
              <button
                onClick={() => setSidebarExpanded(!sidebarExpanded)}
                title={sidebarExpanded ? "Collapse Sidebar" : "Expand Sidebar for full chat titles"}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/80 transition"
              >
                {sidebarExpanded ? (
                  <PanelLeftClose className="h-4 w-4 text-indigo-400" />
                ) : (
                  <PanelLeftOpen className="h-4 w-4 text-slate-400" />
                )}
              </button>
            </div>
            {[
              { id: "workbench", label: "Live Analyst Workbench", Icon: Bot },
              { id: "indexing", label: "Document Indexing Lab", Icon: Upload },
            ].map(({ id, label, Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id as any)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  activeTab === id
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </button>
            ))}
          </div>

          {/* Chat Sessions List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-1">
            <div className="flex items-center justify-between px-1 mb-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Chats
              </p>
              <button
                onClick={addNewChat}
                title="New Chat"
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-indigo-400 hover:bg-indigo-500/10 border border-indigo-500/20 hover:border-indigo-500/40 transition"
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
            </div>

            {chats.map((chat, idx) => (
              <div
                key={chat.id || `chat-${idx}`}
                onClick={() => switchChat(chat.id)}
                className={`group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-all ${
                  activeChatId === chat.id
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200 border border-transparent"
                }`}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="flex-1 text-sm font-medium truncate">{chat.name}</span>
                {chat.attachedFiles && chat.attachedFiles.length > 0 && (
                  <span title={`${chat.attachedFiles.length} files uploaded in this chat`} className="flex items-center text-[10px] text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20">
                    <Paperclip className="h-2.5 w-2.5 mr-0.5" />
                    {chat.attachedFiles.length}
                  </span>
                )}
                {chat.messages.length > 0 && (
                  <span className="text-[10px] text-slate-500">
                    {chat.messages.filter((m) => m.role === "user").length}
                  </span>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteChat(chat.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition rounded p-0.5 hover:text-red-400"
                  title="Delete chat"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* Content Panel */}
        <main className="flex-1 overflow-hidden bg-[#090d16] flex flex-col">

          {/* ── TAB 1: LIVE ANALYST WORKBENCH ────────────────────────────────── */}
          {activeTab === "workbench" && (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Chat header */}
              <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-950/40">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-indigo-400" />
                  <span className="text-sm font-semibold text-slate-200">{activeChat?.name}</span>
                  <span className="text-xs font-mono text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/60">
                    {activeChat?.id}
                  </span>
                  {activeChat?.attachedFiles && activeChat.attachedFiles.length > 0 && (
                    <span className="text-[11px] text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded-full border border-cyan-500/30 flex items-center gap-1 font-medium ml-2">
                      <Paperclip className="h-3 w-3" />
                      {activeChat.attachedFiles.length} file(s) attached
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {/* ── Model Selector Dropdown ── */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setModelDropdownOpen((prev) => !prev)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition select-none ${
                        modelDropdownOpen
                          ? "bg-slate-800 border-slate-600 text-slate-200"
                          : "bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-600 hover:text-slate-100"
                      }`}
                      title="Select AI model"
                    >
                      <span className={`h-2 w-2 rounded-full ${activeModel.dotColor} shrink-0`} />
                      <span className={activeModel.color}>{activeModel.label}</span>
                      <ChevronDown className={`h-3 w-3 text-slate-500 transition-transform ${modelDropdownOpen ? "rotate-180" : ""}`} />
                    </button>

                    {modelDropdownOpen && (
                      <div
                        className="absolute right-0 top-full mt-1.5 z-50 w-52 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl shadow-black/50 overflow-hidden"
                        onMouseLeave={() => setModelDropdownOpen(false)}
                      >
                        <div className="px-3 py-2 border-b border-slate-800">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Select Model</p>
                        </div>
                        {MODEL_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => { setModelPreference(opt.value); setModelDropdownOpen(false); }}
                            className={`flex items-start gap-2.5 w-full px-3 py-2.5 text-left transition hover:bg-slate-800 ${
                              modelPreference === opt.value ? "bg-slate-800/70" : ""
                            }`}
                          >
                            <span className={`mt-1 h-2 w-2 rounded-full shrink-0 ${opt.dotColor}`} />
                            <div>
                              <p className={`text-xs font-semibold ${opt.color}`}>{opt.label}</p>
                              <p className="text-[10px] text-slate-500 mt-0.5">{opt.desc}</p>
                            </div>
                            {modelPreference === opt.value && (
                              <Check className="h-3.5 w-3.5 text-indigo-400 ml-auto mt-0.5 shrink-0" />
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Single Global Workspace Knowledge Toggle */}
                  <button
                    type="button"
                    onClick={toggleSearchScope}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${
                      activeChat?.searchScope === "global"
                        ? "bg-indigo-600/30 text-indigo-300 border-indigo-500 shadow-md shadow-indigo-500/20"
                        : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
                    }`}
                    title="Toggle to include Global Workspace Knowledge base documents alongside current chat uploads"
                  >
                    <Globe className={`h-3.5 w-3.5 ${activeChat?.searchScope === "global" ? "text-indigo-400" : "text-slate-500"}`} />
                    <span>Global Workspace Knowledge</span>
                    <span className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${activeChat?.searchScope === "global" ? "bg-indigo-500 text-white" : "bg-slate-800 text-slate-500"}`}>
                      {activeChat?.searchScope === "global" ? "ON" : "OFF"}
                    </span>
                  </button>

                  {/* User Profile & Logout */}
                  {user && (
                    <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
                      {user.photoURL ? (
                        <img
                          src={user.photoURL}
                          alt={user.displayName || "User"}
                          className="w-7 h-7 rounded-full border border-slate-700 object-cover"
                        />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">
                          {(user.displayName || user.email || "U")[0].toUpperCase()}
                        </div>
                      )}
                      <span className="text-xs font-medium text-slate-300 hidden md:inline max-w-[100px] truncate">
                        {user.displayName || user.email?.split("@")[0]}
                      </span>
                      <button
                        type="button"
                        onClick={signOut}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
                        title="Sign Out"
                      >
                        <LogOut className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Messages Thread */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                {(!activeChat || activeChat.messages.length === 0) && (
                  <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
                    <Bot className="h-12 w-12 opacity-30" />
                    <p className="text-sm">Ask a compliance or policy question or upload a document to start this chat.</p>
                    <p className="text-xs text-slate-600 text-center max-w-md">
                      Documents uploaded in this chat are automatically searched. Toggle "Global Workspace Knowledge" above to also search lab documents.
                    </p>
                  </div>
                )}

                {activeChat?.messages.map((msg, idx) => (
                  <div key={msg.id || `msg-${idx}`}>
                    {msg.role === "user" ? (
                      /* User bubble */
                      <div className="flex justify-end">
                        <div className="max-w-[70%] space-y-1">
                          {msg.attachedFile ? (
                            /* File attachment bubble */
                            <div className="rounded-2xl rounded-tr-sm bg-slate-900 border border-slate-800 p-3.5 flex items-center gap-3 text-slate-200 shadow-md">
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                                <FileIcon className="h-5 w-5" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold truncate text-slate-100">{msg.attachedFile}</p>
                                <p className={`text-[10px] ${msg.uploadStatus === "skipped" ? "text-amber-400 font-medium" : "text-cyan-400"}`}>
                                  {msg.uploadStatus === "skipped" ? "Document already uploaded in this session" : "Document indexed into current chat context"}
                                </p>
                              </div>
                            </div>
                          ) : (
                            <div className="rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-3 text-sm text-white shadow-lg shadow-indigo-500/10">
                              {msg.content}
                            </div>
                          )}
                          <div className="flex items-center justify-end gap-2 px-1">
                            {msg.searchScope && (
                              <span className="text-[10px] text-slate-500">
                                {msg.searchScope === "session" ? "In-Chat RAG" : "Global Workspace RAG"}
                              </span>
                            )}
                            <span className="text-[10px] text-slate-600">
                              {new Date(msg.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* Assistant bubble */
                      <div className="flex justify-start gap-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 shadow-md mt-1">
                          <Brain className="h-4 w-4 text-white" />
                        </div>
                        <div className="flex-1 max-w-[85%] space-y-3">
                          {/* Badges row */}
                          <div className="flex flex-wrap gap-2">
                            {msg.cacheHit && (
                              msg.cacheType === "exact_hash" ? (
                                <div className="flex items-center gap-1.5 text-[11px] bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 px-3 py-1 rounded-lg font-bold shadow-md shadow-cyan-500/20 animate-pulse">
                                  <Zap className="h-3.5 w-3.5 text-cyan-400 fill-cyan-400" />
                                  <span>Exact Cache Hit (1ms)</span>
                                </div>
                              ) : (
                                <div className="flex items-center gap-1.5 text-[11px] bg-emerald-500/20 border border-emerald-400/40 text-emerald-300 px-3 py-1 rounded-lg font-bold shadow-md shadow-emerald-500/20 animate-pulse">
                                  <Zap className="h-3.5 w-3.5 text-emerald-400 fill-emerald-400" />
                                  <span>Semantic Cache Hit (10ms)</span>
                                </div>
                              )
                            )}
                            {msg.memoryCompacted && (
                              <div className="flex items-center gap-1 text-[11px] bg-purple-500/10 border border-purple-500/30 text-purple-400 px-2.5 py-1 rounded-lg font-semibold">
                                <Brain className="h-3 w-3" /> Memory Compacted
                              </div>
                            )}
                            {msg.evalScores && (
                              <div className="flex items-center gap-1 text-[11px] bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-2.5 py-1 rounded-lg font-semibold">
                                <CheckCircle2 className="h-3 w-3" />
                                Groundedness {Math.round(((msg.evalScores.groundedness ?? msg.evalScores.overall_quality) ?? 0.95) * 100)}%
                              </div>
                            )}
                          </div>

                          {/* Completed Node Execution Stepper Card (Stays visible permanently) */}
                          {msg.nodeEvents && msg.nodeEvents.length > 0 && (
                            <div className="rounded-xl bg-slate-950/80 border border-slate-800 p-3 space-y-2">
                              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400">
                                <span className="flex items-center gap-1.5 uppercase tracking-wider text-indigo-400">
                                  <Terminal className="h-3.5 w-3.5" />
                                  LangGraph Workflow ({msg.nodeEvents.length} Nodes Executed)
                                </span>
                              </div>
                              <div className="grid grid-cols-7 gap-1.5">
                                {[
                                  { id: "guardrail", name: "Guardrail", Icon: ShieldCheck },
                                  { id: "planner", name: "Planner", Icon: Brain },
                                  { id: "router", name: "Router", Icon: Zap },
                                  { id: "retrieval", name: "Retrieval", Icon: Search },
                                  { id: "analysis", name: "Analysis", Icon: FileText },
                                  { id: "reflection", name: "Reflection", Icon: RotateCcw },
                                  { id: "judge", name: "Judge", Icon: Scale },
                                ].map(({ id, name, Icon }) => {
                                  const isDone = msg.nodeEvents?.some((e: any) => e.node === id);
                                  return (
                                    <div
                                      key={id}
                                      className={`flex flex-col items-center rounded-lg p-1.5 border text-center transition-all ${
                                        isDone
                                          ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-400"
                                          : "bg-slate-950/20 border-slate-850 text-slate-700"
                                      }`}
                                    >
                                      <Icon className="h-3.5 w-3.5 mb-0.5" />
                                      <span className="text-[9px] font-medium leading-none">{name}</span>
                                      {isDone && <CheckCircle2 className="h-2.5 w-2.5 mt-1 text-emerald-400" />}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Report */}
                          <div className="rounded-2xl rounded-tl-sm bg-slate-900 border border-slate-800 px-5 py-4 text-sm text-slate-200 whitespace-pre-line leading-relaxed shadow-md">
                            {msg.content || (
                              <span className="text-slate-500 italic">No report generated.</span>
                            )}
                          </div>

                          {/* Citations */}
                          {msg.citations && msg.citations.length > 0 && (
                            <div className="space-y-2">
                              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                                <CheckCircle2 className="h-3 w-3 text-cyan-400" />
                                Verified Citations ({msg.citations.length})
                              </p>
                              <div className="grid grid-cols-2 gap-2">
                                {msg.citations.map((c) => (
                                  <div
                                    key={c.citation_id}
                                    className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs"
                                  >
                                    <div className="flex justify-between items-center font-semibold text-indigo-400 mb-1">
                                      <span>[Doc {c.citation_id}]</span>
                                      <span className="text-slate-500">P{c.page_number || 1}</span>
                                    </div>
                                    <p className="text-slate-300 font-medium truncate">{c.source_name}</p>
                                    <p className="text-slate-500 line-clamp-2 mt-0.5">"{c.snippet}"</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <span className="text-[10px] text-slate-600 px-1">
                            {new Date(msg.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Live node stepper (while analyzing) */}
                {isAnalyzing && (
                  <div className="flex justify-start gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 shadow-md mt-1 animate-pulse">
                      <Brain className="h-4 w-4 text-white" />
                    </div>
                    <div className="flex-1 max-w-[85%] space-y-3">
                      {runningExplainabilityReason && (
                        <div className="flex items-center gap-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 text-[11px] font-medium text-amber-300 w-fit">
                          <Sparkles className="h-3 w-3 text-amber-400" />
                          {runningExplainabilityReason}
                        </div>
                      )}
                      <div className="rounded-2xl rounded-tl-sm bg-slate-900 border border-slate-800 px-5 py-4 space-y-3">
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                          <Terminal className="h-3.5 w-3.5 text-indigo-400" />
                          LangGraph Node Execution
                        </p>
                        <div className="grid grid-cols-7 gap-2">
                          {[
                            { id: "guardrail", name: "Guardrail", Icon: ShieldCheck },
                            { id: "planner", name: "Planner", Icon: Brain },
                            { id: "router", name: "Router", Icon: Zap },
                            { id: "retrieval", name: "Retrieval", Icon: Search },
                            { id: "analysis", name: "Analysis", Icon: FileText },
                            { id: "reflection", name: "Reflection", Icon: RotateCcw },
                            { id: "judge", name: "Judge", Icon: Scale },
                          ].map(({ id, name, Icon }) => {
                            const isActive = activeNode === id;
                            const isDone = nodeEvents.some((e) => e.node === id);
                            return (
                              <div
                                key={id}
                                className={`flex flex-col items-center rounded-xl p-2.5 border text-center transition-all duration-300 ${
                                  isActive
                                    ? "bg-gradient-to-b from-indigo-600/40 via-indigo-700/30 to-slate-900 border-indigo-400 text-indigo-200 shadow-xl shadow-indigo-500/40 ring-2 ring-indigo-400/60 animate-pulse scale-105"
                                    : isDone
                                    ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-400 shadow-md shadow-emerald-950/30"
                                    : "bg-slate-950/40 border-slate-800/80 text-slate-600 opacity-60"
                                }`}
                              >
                                <Icon className={`h-4 w-4 mb-1 ${isActive ? "text-indigo-300 animate-bounce" : isDone ? "text-emerald-400" : ""}`} />
                                <span className="text-[10px] font-semibold">{name}</span>
                                {isDone && !isActive && (
                                  <CheckCircle2 className="h-3 w-3 mt-1 text-emerald-400" />
                                )}
                                {isActive && (
                                  <span className="mt-1 text-[9px] bg-indigo-500 text-white font-bold px-1.5 py-0.2 rounded-full shadow-sm animate-pulse">
                                    Running
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input bar */}
              <div className="border-t border-slate-800 bg-slate-950/60 px-6 py-4">
                {/* Hidden File Input */}
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".pdf,.txt,.md"
                  className="hidden"
                />

                <div className="flex gap-3 items-center">
                  {/* Paperclip file upload button */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading || isAnalyzing}
                    title="Upload document (.pdf, .txt, .md) to this chat"
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:text-indigo-400 hover:border-indigo-500/50 transition disabled:opacity-50"
                  >
                    {isUploading ? (
                      <RotateCcw className="h-4 w-4 animate-spin text-indigo-400" />
                    ) : (
                      <Paperclip className="h-4 w-4" />
                    )}
                  </button>

                  <input
                    id="query-input"
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask a policy, audit, or technical documentation question..."
                    disabled={isAnalyzing}
                    className="flex-1 rounded-xl bg-slate-900 px-4 py-3 text-sm text-slate-100 border border-slate-800 focus:border-indigo-500 focus:outline-none transition disabled:opacity-50"
                  />
                  <button
                    id="run-agent-btn"
                    onClick={handleAnalyze}
                    disabled={isAnalyzing || !query.trim()}
                    className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 px-5 py-3 text-sm font-semibold text-white hover:from-indigo-500 hover:to-indigo-400 shadow-lg shadow-indigo-500/20 disabled:opacity-50 transition"
                  >
                    {isAnalyzing ? (
                      <RotateCcw className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <p className="text-[11px] text-slate-600 mt-1.5 px-1">
                  Session: <span className="font-mono">{activeChat?.id?.slice(0, 16) || "init"}…</span>
                  {" · "}
                  {activeChat?.searchScope === "session"
                    ? "In-Chat RAG (This chat's documents)"
                    : "Global Workspace RAG (Lab + Chat documents)"}
                  {" · "}Press Enter to send
                </p>
              </div>
            </div>
          )}

          {/* ── TAB 2: DOCUMENT INDEXING LAB ─────────────────────────────────── */}
          {activeTab === "indexing" && (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-4xl mx-auto rounded-2xl p-6 border border-slate-800 bg-slate-900/30 space-y-6">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Upload className="h-5 w-5 text-indigo-400" />
                    Global Workspace Knowledge Ingestion Lab
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Documents indexed here are saved directly into <span className="font-semibold text-indigo-300">Global Workspace Knowledge</span> and are accessible across all chats when Global Workspace search is enabled.
                  </p>
                </div>

                <div className="space-y-6">
                  {/* File Upload Card */}
                  <div className="rounded-2xl border border-dashed border-indigo-500/40 bg-indigo-950/20 p-8 text-center hover:border-indigo-500/70 transition">
                    <input
                      type="file"
                      ref={labFileInputRef}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        setIndexingStatus("Uploading & indexing file into Global Workspace Knowledge...");
                        const formData = new FormData();
                        formData.append("file", file);
                        formData.append("session_id", "global_workspace");
                        try {
                          const res = await fetch("http://localhost:8000/api/v1/documents/upload", {
                            method: "POST",
                            headers: getAuthHeaders(),
                            body: formData,
                          });
                          if (!res.ok) throw new Error("Upload failed");
                          const data = await res.json();
                          if (data.status === "skipped") {
                            setIndexingStatus(`⚠️ '${data.filename || data.title}' already uploaded in Global Workspace Knowledge!`);
                            showToast("Document already uploaded in Global Workspace");
                          } else {
                            setIndexingStatus(`✅ Indexed '${data.filename || data.title}' into Global Workspace Knowledge! (Chunks: ${data.chunks_indexed})`);
                            showToast("Document uploaded successfully");
                          }
                        } catch (err: any) {
                          const isFetchErr = err?.message === "Failed to fetch" || err?.name === "TypeError";
                          const userErrMsg = isFetchErr
                            ? "Backend server is starting up. Please try again in a few seconds."
                            : `Error: ${err.message || err}`;
                          setIndexingStatus(userErrMsg);
                          showToast(userErrMsg);
                        } finally {
                          if (labFileInputRef.current) labFileInputRef.current.value = "";
                        }
                      }}
                      accept=".pdf,.txt,.md"
                      className="hidden"
                    />
                    <div className="flex flex-col items-center gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
                        <Upload className="h-6 w-6" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-200">
                          Upload Document (.pdf, .txt, .md) to Global Workspace
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Extracted chunks will be available across all chats when Global Workspace search is enabled.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => labFileInputRef.current?.click()}
                        className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 transition shadow-lg shadow-indigo-500/20"
                      >
                        Select & Index File
                      </button>
                    </div>
                  </div>

                  <div className="relative flex py-2 items-center">
                    <div className="flex-grow border-t border-slate-800"></div>
                    <span className="flex-shrink mx-4 text-xs font-semibold uppercase tracking-wider text-slate-500">Or Paste Raw Text</span>
                    <div className="flex-grow border-t border-slate-800"></div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Document Title</label>
                    <input
                      type="text"
                      value={docTitle}
                      onChange={(e) => setDocTitle(e.target.value)}
                      placeholder="e.g. SOC2 Global Security Policy 2025"
                      className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm text-slate-100 border border-slate-800 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Source Filename</label>
                    <input
                      type="text"
                      value={docSource}
                      onChange={(e) => setDocSource(e.target.value)}
                      placeholder="e.g. SOC2_Policy_2025.pdf"
                      className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm text-slate-100 border border-slate-800 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Document Text Content</label>
                    <textarea
                      rows={6}
                      value={docContent}
                      onChange={(e) => setDocContent(e.target.value)}
                      placeholder="Paste raw compliance policies, architecture specs, or standards..."
                      className="w-full rounded-xl bg-slate-900 p-4 text-xs font-mono text-slate-300 border border-slate-800 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  <button
                    onClick={handleIndexDocument}
                    className="rounded-xl bg-slate-800 px-6 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-700 transition border border-slate-700"
                  >
                    Index Raw Text into Global Workspace Base
                  </button>

                  {indexingStatus && (
                    <div className="rounded-xl bg-indigo-950/30 border border-indigo-500/30 p-4 text-xs text-indigo-300">
                      {indexingStatus}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 3: JUDGE & TELEMETRY ─────────────────────────────────────── */}
          {activeTab === "observability" && (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-5xl mx-auto space-y-6">
                <div className="rounded-2xl p-6 border border-slate-800 bg-slate-900/30">
                  <h2 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
                    <Scale className="h-5 w-5 text-emerald-400" />
                    LLM-as-a-Judge Evaluation & Telemetry Scorecard
                  </h2>
                  <p className="text-xs text-slate-400 mb-6">
                    Every execution graph run is audited by the Judge Agent and recorded into Firestore.
                  </p>
                  <div className="grid grid-cols-4 gap-4">
                    {[
                      { label: "Overall Groundedness", value: "94%", sub: "Verified against chunks", color: "text-emerald-400" },
                      { label: "Citation Coverage", value: "100%", sub: "Footnote precision", color: "text-cyan-400" },
                      { label: "Reflection Re-plans", value: "1 Cycle", sub: "Self-correction count", color: "text-amber-400" },
                      { label: "Avg Node Latency", value: "140ms", sub: "Cross-Encoder + RRF", color: "text-indigo-400" },
                    ].map(({ label, value, sub, color }) => (
                      <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                        <p className="text-xs text-slate-400 font-semibold mb-1">{label}</p>
                        <p className={`text-2xl font-extrabold ${color}`}>{value}</p>
                        <p className="text-[11px] text-slate-500 mt-1">{sub}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 4: AI SOLUTION ARCHITECT ─────────────────────────────────── */}
          {activeTab === "architect" && (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-5xl mx-auto space-y-6">
                <div className="rounded-2xl p-6 border border-slate-800 bg-slate-900/30 space-y-4">
                  <div>
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                      <Layers className="h-5 w-5 text-cyan-400" />
                      Version 2 — AI Solution Architect
                    </h2>
                    <p className="text-xs text-slate-400">
                      Transform the agent runtime into a platform that designs and scaffolds new enterprise AI agents from natural language prompts.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <label className="block text-xs font-semibold text-slate-400">
                      Describe Desired Enterprise AI Assistant
                    </label>
                    <textarea
                      rows={4}
                      value={architectPrompt}
                      onChange={(e) => setArchitectPrompt(e.target.value)}
                      className="w-full rounded-xl bg-slate-900 p-4 text-xs text-slate-200 border border-slate-800 focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={handleGenerateArchitecture}
                    className="rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:from-cyan-500 hover:to-indigo-500 transition shadow-lg shadow-cyan-500/20 flex items-center gap-2"
                  >
                    <Sparkles className="h-4 w-4" />
                    Generate Agent Topology & Code Scaffold
                  </button>
                </div>

                {architectResult && (
                  <div className="rounded-2xl p-6 border border-cyan-500/30 bg-slate-900/30 space-y-4">
                    <h3 className="text-sm font-semibold text-cyan-300 border-b border-slate-800 pb-2">
                      Generated LangGraph Agent Topology
                    </h3>
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div className="rounded-xl bg-slate-900/60 p-4 border border-slate-800">
                        <p className="font-semibold text-slate-300 mb-2">Topology Graph Nodes:</p>
                        <ul className="space-y-1 text-slate-400 font-mono">
                          {architectResult.nodes.map((n: string) => (
                            <li key={n} className="flex items-center gap-1.5">
                              <ChevronRight className="h-3 w-3 text-cyan-400" /> {n}
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="rounded-xl bg-slate-900/60 p-4 border border-slate-800">
                        <p className="font-semibold text-slate-300 mb-2">MCP Tools & Cognitive Agents:</p>
                        <div className="space-y-2">
                          {architectResult.components.map((c: any) => (
                            <div key={c.name} className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800">
                              <span className="font-medium text-slate-200">{c.name}</span>
                              <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded border border-cyan-500/30">
                                {c.type}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
