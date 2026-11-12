"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentResponse,
  AgentTurn,
  Citation,
  Paper,
  SearchResponse,
  Source,
} from "@/lib/api/papers";
import { normalizeArxiv, normalizeOpenAlex } from "@/lib/api/papers";

type ServiceStatus = "checking" | "ready" | "unavailable";
type LibraryEntry = {
  id: string;
  source: "openalex" | "arxiv";
  source_id: string;
  metadata?: Paper;
};
type PrivateDocument = {
  id: string;
  library_entry_id: string | null;
  source_type: "openalex" | "arxiv" | "personal";
  source_id: string;
  title: string;
  source_url: string;
  original_filename: string;
  size_bytes: number;
  state: "queued" | "processing" | "indexed" | "failed";
  parser_version?: string | null;
  error_code?: string | null;
  chunk_count: number;
};
type ConversationSummary = { id: string; title: string };

const sourceLabels: Record<Source, string> = {
  openalex: "OpenAlex",
  arxiv: "arXiv",
  library: "我的文献库",
};

const sampleQuestions = [
  "比较两篇论文的研究方法和结论。",
  "检查这段论述能否由已保存的论文支持。",
];

export function Workspace({
  conversationId,
  conversationLoading,
  onSignOut,
  onNewConversation,
  onRenameConversation,
  onDeleteConversation,
  onSelectConversation,
  conversations,
  initialHistory,
}: {
  conversationId: string | null;
  conversationLoading: boolean;
  onSignOut: () => void;
  onNewConversation: () => Promise<boolean>;
  onRenameConversation: (id: string, title: string) => Promise<boolean>;
  onDeleteConversation: (id: string) => Promise<boolean>;
  onSelectConversation: (id: string) => void;
  conversations: ConversationSummary[];
  initialHistory: AgentTurn[];
}) {
  const [source, setSource] = useState<Source>("openalex");
  const [activeWorkspace, setActiveWorkspace] = useState<
    "discover" | "assistant"
  >("discover");
  const [query, setQuery] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [results, setResults] = useState<Paper[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>("checking");
  const [libraryEntries, setLibraryEntries] = useState<LibraryEntry[]>([]);
  const [privateDocuments, setPrivateDocuments] = useState<PrivateDocument[]>(
    [],
  );
  const [privateDocumentsError, setPrivateDocumentsError] = useState(false);
  const [uploadingDocumentId, setUploadingDocumentId] = useState<string | null>(
    null,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<Paper | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showUsage, setShowUsage] = useState(false);
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<AgentTurn[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AgentResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentCancelling, setAgentCancelling] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [conversationActionError, setConversationActionError] = useState<
    string | null
  >(null);
  const [editingConversationId, setEditingConversationId] = useState<
    string | null
  >(null);
  const [editingConversationTitle, setEditingConversationTitle] = useState("");
  const [deletingConversationId, setDeletingConversationId] = useState<
    string | null
  >(null);
  const agentAbortController = useRef<AbortController | null>(null);
  const agentRunId = useRef<string | null>(null);
  const searchRequestId = useRef(0);
  const detailRequestId = useRef(0);
  const conversationEndRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => setHistory(initialHistory), [initialHistory]);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ block: "end" });
  }, [history]);

  useEffect(() => {
    if (agentAbortController.current) {
      cancelAgentRun();
      agentAbortController.current = null;
      agentRunId.current = null;
      setAgentLoading(false);
    }
    setAnswer(null);
    setAgentError(null);
    setQuestion("");
  }, [conversationId]);

  useEffect(() => setPendingQuestion(null), [conversationId]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/status", { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("unavailable");
        return response.json();
      })
      .then((value: { status?: string }) =>
        setServiceStatus(value.status === "ready" ? "ready" : "unavailable"),
      )
      .catch(() => setServiceStatus("unavailable"));
    return () => controller.abort();
  }, []);

  useEffect(
    () => () => {
      const runId = agentRunId.current;
      if (runId) {
        void fetch("/api/agent/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId }),
          keepalive: true,
        }).catch(() => undefined);
      }
      agentAbortController.current?.abort();
    },
    [],
  );

  useEffect(() => {
    fetch("/api/library", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("library_unavailable");
        return response.json();
      })
      .then((entries: LibraryEntry[]) => setLibraryEntries(entries))
      .catch(() => undefined);
    fetch("/api/documents", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("documents_unavailable");
        return response.json();
      })
      .then((documents: PrivateDocument[]) => {
        if (!Array.isArray(documents)) throw new Error("invalid_documents");
        setPrivateDocuments(documents);
        setPrivateDocumentsError(false);
      })
      .catch(() => setPrivateDocumentsError(true));
  }, []);

  useEffect(() => {
    if (
      !privateDocuments.some((document) =>
        ["queued", "processing"].includes(document.state),
      )
    ) {
      return;
    }
    const refresh = () =>
      fetch("/api/documents", { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error("documents_unavailable");
          return response.json();
        })
        .then((documents: PrivateDocument[]) => {
          if (!Array.isArray(documents)) throw new Error("invalid_documents");
          setPrivateDocuments(documents);
          setPrivateDocumentsError(false);
        })
        .catch(() => setPrivateDocumentsError(true));
    const interval = window.setInterval(refresh, 1_500);
    return () => window.clearInterval(interval);
  }, [privateDocuments]);

  async function saveToLibrary(paper: Paper) {
    try {
      const metadata = {
        ...paper,
        title: paper.title.slice(0, 2_000),
        authors: paper.authors
          .slice(0, 50)
          .map((author) => author.slice(0, 300)),
        abstract: paper.abstract?.slice(0, 8_000) ?? null,
        venue: paper.venue?.slice(0, 1_000) ?? null,
        categories: paper.categories
          .slice(0, 30)
          .map((item) => item.slice(0, 200)),
      };
      const response = await fetch("/api/library", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: paper.source,
          source_id: paper.id,
          metadata,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(readError(body));
      const entry = body as LibraryEntry;
      setLibraryEntries((current) => [
        entry,
        ...current.filter((item) => item.id !== entry.id),
      ]);
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? `保存失败：${cause.message}`
          : "保存失败，请重试。",
      );
    }
  }

  async function removeFromLibrary(entry: LibraryEntry) {
    const response = await fetch(`/api/library/${entry.id}`, {
      method: "DELETE",
    });
    if (response.ok)
      setLibraryEntries((current) =>
        current.filter((item) => item.id !== entry.id),
      );
    else setError("请先删除该论文下的私有 PDF，再移除论文记录。");
  }

  async function uploadPrivateDocument(
    event: FormEvent<HTMLFormElement>,
    entry?: LibraryEntry,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    if (entry) body.set("library_entry_id", entry.id);
    body.set(
      "rights_attested",
      body.get("rights_attested") === "true" ? "true" : "false",
    );
    setUploadingDocumentId(entry?.id ?? "personal");
    setError(null);
    try {
      const response = await fetch("/api/documents", {
        method: "POST",
        body,
      });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(readError(value));
      setPrivateDocuments((current) => [
        value as PrivateDocument,
        ...current.filter((item) => item.id !== (value as PrivateDocument).id),
      ]);
      form.reset();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "PDF 上传失败，请重试。",
      );
    } finally {
      setUploadingDocumentId(null);
    }
  }

  async function deletePrivateDocument(document: PrivateDocument) {
    const response = await fetch(`/api/documents/${document.id}`, {
      method: "DELETE",
    });
    if (response.ok) {
      setPrivateDocuments((current) =>
        current.filter((item) => item.id !== document.id),
      );
    } else {
      const body = await response.json().catch(() => ({}));
      setError(readError(body));
    }
  }

  async function retryPrivateDocument(document: PrivateDocument) {
    const response = await fetch(`/api/documents/${document.id}/retry`, {
      method: "POST",
    });
    if (response.ok) {
      setPrivateDocuments((current) =>
        current.map((item) =>
          item.id === document.id ? { ...item, state: "queued" } : item,
        ),
      );
    } else {
      const body = await response.json().catch(() => ({}));
      setError(readError(body));
    }
  }

  const visibleResults = useMemo(() => {
    const from = yearFrom ? Number(yearFrom) : null;
    const to = yearTo ? Number(yearTo) : null;
    if (from === null && to === null) return results;
    return results.filter((paper) => {
      if (paper.year === null) return false;
      return (
        (from === null || paper.year >= from) &&
        (to === null || paper.year <= to)
      );
    });
  }, [results, yearFrom, yearTo]);

  const selectedPapers = useMemo(
    () =>
      selected.flatMap((key) =>
        results.filter((paper) => paperKey(paper) === key),
      ),
    [results, selected],
  );

  async function search(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (source !== "library" && !query.trim()) {
      setError("请输入主题、关键词或论文标题。");
      return;
    }
    const requestId = ++searchRequestId.current;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    setSelected([]);
    setTotal(null);
    try {
      const params = new URLSearchParams({ source, q: query.trim() });
      const response = await fetch(`/api/search?${params.toString()}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(20_000),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(readError(body));
      if (requestId !== searchRequestId.current) return;
      const payload = body as SearchResponse;
      setResults(payload.items);
      setTotal(payload.total);
    } catch (cause) {
      if (requestId !== searchRequestId.current) return;
      setResults([]);
      setError(
        cause instanceof Error ? cause.message : "检索暂时失败，请重试。",
      );
    } finally {
      if (requestId === searchRequestId.current) setLoading(false);
    }
  }

  async function openDetails(paper: Paper) {
    const requestId = ++detailRequestId.current;
    setDetail(paper);
    setDetailError(null);
    if (source === "library") return;
    setDetailLoading(true);
    try {
      const routeSource = paper.source;
      const params = new URLSearchParams({ source: routeSource, id: paper.id });
      const response = await fetch(`/api/paper?${params.toString()}`, {
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(readError(body));
      if (requestId !== detailRequestId.current) return;
      const fullPaper =
        paper.source === "arxiv"
          ? normalizeArxiv(body)
          : normalizeOpenAlex(body);
      setDetail({ ...paper, ...fullPaper, sourceUrl: paper.sourceUrl });
    } catch (cause) {
      if (requestId !== detailRequestId.current) return;
      setDetailError(
        cause instanceof Error ? cause.message : "论文详情暂时无法读取。",
      );
    } finally {
      if (requestId === detailRequestId.current) setDetailLoading(false);
    }
  }

  function toggleCompare(paper: Paper) {
    const key = paperKey(paper);
    setSelected((current) => {
      if (current.includes(key)) return current.filter((item) => item !== key);
      if (current.length >= 3) return current;
      return [...current, key];
    });
  }

  async function askAgent(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (
      !conversationId ||
      conversationLoading ||
      agentLoading ||
      !question.trim()
    )
      return;
    const submittedQuestion = question.trim();
    setPendingQuestion(submittedQuestion);
    setQuestion("");
    setAgentLoading(true);
    setAgentError(null);
    setAnswer(null);
    const controller = new AbortController();
    const runId = crypto.randomUUID();
    agentRunId.current = runId;
    agentAbortController.current = controller;
    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: submittedQuestion,
          history,
          run_id: runId,
          ...(conversationId ? { conversation_id: conversationId } : {}),
        }),
        signal: controller.signal,
      });
      const body = await response.json();
      if (agentAbortController.current !== controller) return;
      if (!response.ok) throw new Error(readError(body));
      const completedAnswer = body as AgentResponse;
      setAnswer(completedAnswer);
      setHistory((current) =>
        appendConversation(current, submittedQuestion, completedAnswer.answer),
      );
      setPendingQuestion(null);
    } catch (cause) {
      if (agentAbortController.current !== controller) return;
      setQuestion((current) => current || submittedQuestion);
      setAgentError(
        cause instanceof DOMException && cause.name === "AbortError"
          ? "任务已取消。"
          : cause instanceof Error
            ? cause.message
            : "研究助理暂时不可用，请重试。",
      );
    } finally {
      if (agentAbortController.current === controller) {
        agentAbortController.current = null;
        setAgentLoading(false);
      }
      if (agentRunId.current === runId) agentRunId.current = null;
    }
  }

  function cancelAgentRun() {
    void confirmAgentCancellation();
  }

  async function confirmAgentCancellation() {
    const runId = agentRunId.current;
    if (!runId || agentCancelling) return;
    setAgentCancelling(true);
    try {
      const cancelResponse = await fetch("/api/agent/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId }),
      });
      if (!cancelResponse.ok) throw new Error("cancel_request_failed");
      for (let attempt = 0; attempt < 20; attempt += 1) {
        const response = await fetch(`/api/agent/runs/${runId}`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error("run_status_unavailable");
        const status = (await response.json()) as { status?: string };
        if (status.status === "cancelled") {
          agentAbortController.current?.abort();
          if (agentRunId.current === runId) setAgentError("任务已取消。");
          return;
        }
        if (
          ["completed", "failed", "interrupted"].includes(status.status ?? "")
        ) {
          if (agentRunId.current === runId)
            setAgentError("任务已结束，取消未生效。");
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      if (agentRunId.current === runId)
        setAgentError(
          "取消请求已发送，但暂时无法确认任务已停止。请检查运行状态后再重试。",
        );
    } catch {
      if (agentRunId.current === runId)
        setAgentError(
          "无法确认任务已停止；任务可能仍在运行，请检查服务状态后再重试。",
        );
    } finally {
      if (agentRunId.current === runId) setAgentCancelling(false);
    }
  }

  function useSampleQuestion(value: string) {
    setQuestion(value);
  }

  async function resetAgentConversation() {
    if (conversationId) {
      const response = await fetch(
        `/api/conversations/${conversationId}/messages`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        setAgentError("清空对话失败，请稍后重试。");
        return;
      }
    }
    setHistory([]);
    setPendingQuestion(null);
    setAnswer(null);
    setAgentError(null);
  }

  async function startNewConversation() {
    setConversationActionError(null);
    if (!(await onNewConversation())) {
      setConversationActionError("新建对话失败，请检查服务后重试。");
    }
  }

  async function saveConversationTitle(id: string) {
    const title = editingConversationTitle.trim();
    if (!title) {
      setConversationActionError("对话名称不能为空。");
      return;
    }
    setConversationActionError(null);
    if (!(await onRenameConversation(id, title))) {
      setConversationActionError("修改对话名称失败，请稍后重试。");
      return;
    }
    setEditingConversationId(null);
  }

  async function deleteConversation(id: string) {
    setConversationActionError(null);
    if (!(await onDeleteConversation(id))) {
      setConversationActionError("删除对话失败，请稍后重试。");
      return;
    }
    setDeletingConversationId(null);
    setEditingConversationId(null);
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="PaperTrail 工作区首页">
          <span className="brand-mark" aria-hidden="true">
            P<span>.</span>
          </span>
          <span>PaperTrail</span>
        </a>
        <nav className="topnav" aria-label="工作区">
          <button
            aria-pressed={activeWorkspace === "discover"}
            className={activeWorkspace === "discover" ? "active" : ""}
            onClick={() => setActiveWorkspace("discover")}
            type="button"
          >
            发现论文
          </button>
          <button
            aria-pressed={activeWorkspace === "assistant"}
            className={activeWorkspace === "assistant" ? "active" : ""}
            onClick={() => setActiveWorkspace("assistant")}
            type="button"
          >
            科研助手
          </button>
          <button
            aria-controls="usage-panel"
            aria-expanded={showUsage}
            className="usage-button"
            onClick={() => setShowUsage((open) => !open)}
            type="button"
          >
            使用说明
          </button>
        </nav>
        <div
          className={`service-pill ${serviceStatus}`}
          role="status"
          aria-live="polite"
        >
          <span className="status-dot" />
          {serviceStatus === "checking"
            ? "连接检查中"
            : serviceStatus === "ready"
              ? "后端已就绪"
              : "后端未连接"}
        </div>
        <button className="signout-button" onClick={onSignOut} type="button">
          退出
        </button>
      </header>

      {showUsage && (
        <section
          className="usage-panel"
          id="usage-panel"
          aria-labelledby="usage-title"
          role="region"
        >
          <div className="usage-heading">
            <h2 id="usage-title">使用说明</h2>
            <button
              className="text-button"
              onClick={() => setShowUsage(false)}
              type="button"
            >
              收起
            </button>
          </div>
          <div className="usage-grid">
            <article>
              <h3>查找论文</h3>
              <p>
                选择 OpenAlex 或
                arXiv，搜索主题、关键词或标题。打开结果可查看来源记录；加入个人库只保存元数据，不会下载
                PDF。
              </p>
            </article>
            <article>
              <h3>整理资料</h3>
              <p>
                在“我的文献库”搜索或移除已保存的记录。上传论文或个人稿件前，请确认自己拥有版权或已获授权；PDF
                只在当前账号的资料空间处理。
              </p>
            </article>
            <article>
              <h3>使用科研助手</h3>
              <p>
                助手可检索公开元数据和你已上传的资料。新问题会重新查找证据；有可用证据时，答案旁会显示引用和原文片段。
              </p>
            </article>
          </div>
          <p className="usage-model-note">
            云端模型启用后，你的问题和命中的论文摘录会发送到服务端配置的模型提供方。配置模型请在服务端
            .env 设置
            <code>LLM_PROVIDER</code>、<code>LLM_API_KEY</code> 和
            <code>LLM_MODEL</code>，然后重启后端；不要把密钥填进网页或聊天。
          </p>
        </section>
      )}

      <div className={`page-grid ${activeWorkspace}-mode`} id="top">
        <section className="main-column" aria-label="论文检索与比较">
          <div className="intro-block">
            <h1>查找论文，整理研究资料。</h1>
            <p>搜索 OpenAlex 和 arXiv，保存需要的文献，再到科研助手中提问。</p>
          </div>

          <section
            className="search-panel"
            id="search"
            aria-labelledby="search-title"
          >
            <div className="panel-heading">
              <div>
                <h2 id="search-title">探索论文</h2>
              </div>
            </div>
            <div className="source-tabs" role="group" aria-label="选择检索来源">
              {(["openalex", "arxiv", "library"] as Source[]).map((item) => (
                <button
                  aria-pressed={source === item}
                  className={
                    source === item ? "source-tab active" : "source-tab"
                  }
                  key={item}
                  onClick={() => {
                    setSource(item);
                    setError(null);
                    setHasSearched(false);
                    setResults([]);
                    setSelected([]);
                  }}
                  type="button"
                >
                  {sourceLabels[item]}
                </button>
              ))}
            </div>
            <form className="search-form" onSubmit={search}>
              <label className="visually-hidden" htmlFor="paper-query">
                检索主题或关键词
              </label>
              <div className="search-input-wrap">
                <span className="search-glyph" aria-hidden="true">
                  ⌕
                </span>
                <input
                  autoComplete="off"
                  id="paper-query"
                  maxLength={256}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={
                    source === "library"
                      ? "搜索本地已导入论文；留空查看全部"
                      : "试试：retrieval augmented generation"
                  }
                  value={query}
                />
                <button
                  className="search-submit"
                  disabled={loading}
                  type="submit"
                >
                  {loading ? "检索中…" : "开始检索"}
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
              <div className="search-helper">
                <span>
                  {source === "library"
                    ? "仅搜索本地已导入的元数据"
                    : `搜索 ${sourceLabels[source]} 学术元数据`}
                </span>
                <span>最多显示 10 条；不会下载论文全文</span>
              </div>
              <div className="filter-row" aria-label="发表年份筛选">
                <span>年份范围</span>
                <label>
                  <span className="visually-hidden">起始年份</span>
                  <input
                    aria-label="起始年份"
                    inputMode="numeric"
                    maxLength={4}
                    onChange={(event) =>
                      setYearFrom(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="从"
                    value={yearFrom}
                  />
                </label>
                <span aria-hidden="true">—</span>
                <label>
                  <span className="visually-hidden">结束年份</span>
                  <input
                    aria-label="结束年份"
                    inputMode="numeric"
                    maxLength={4}
                    onChange={(event) =>
                      setYearTo(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="至"
                    value={yearTo}
                  />
                </label>
                <span className="filter-explainer">仅筛选当前结果页</span>
              </div>
            </form>
          </section>

          <section
            className="results-section"
            aria-labelledby="results-heading"
          >
            <div className="results-heading">
              <div>
                <h2 id="results-heading">检索结果</h2>
              </div>
              {total !== null && (
                <span className="result-count">
                  匹配 {total.toLocaleString()} 条 · 当前显示{" "}
                  {visibleResults.length} 条
                </span>
              )}
            </div>

            {loading && (
              <div className="state-card" role="status">
                <span className="spinner" />
                正在查询 {sourceLabels[source]}…
              </div>
            )}
            {error && !loading && (
              <div className="state-card error-state" role="alert">
                <span className="state-icon">!</span>
                <div>
                  <strong>这次没有完成检索</strong>
                  <p>{error}</p>
                </div>
                <button
                  className="text-button"
                  onClick={() => void search()}
                  type="button"
                >
                  重试
                </button>
              </div>
            )}
            {!loading &&
              !error &&
              hasSearched &&
              visibleResults.length === 0 && (
                <div className="state-card empty-state" role="status">
                  <span className="empty-symbol" aria-hidden="true">
                    ∅
                  </span>
                  <div>
                    <strong>
                      {results.length
                        ? "当前年份范围内没有结果"
                        : "没有找到匹配论文"}
                    </strong>
                    <p>
                      {results.length
                        ? "调整年份范围，或清空年份筛选。"
                        : "试试更短的关键词，或换一个数据来源。"}
                    </p>
                  </div>
                </div>
              )}
            {!loading && !error && !hasSearched && (
              <div className="state-card idle-state">
                <span className="idle-mark" aria-hidden="true">
                  ↗
                </span>
                <div>
                  <strong>
                    {source === "library"
                      ? "从本地资料开始"
                      : "开始一场文献探索"}
                  </strong>
                  <p>
                    {source === "library"
                      ? "这里仅展示你已导入的研究资料。"
                      : "输入研究主题或论文标题，结果将保留来源链接与关键元数据。"}
                  </p>
                </div>
              </div>
            )}
            {!loading && !error && visibleResults.length > 0 && (
              <ol className="paper-list">
                {visibleResults.map((paper, index) => {
                  const key = paperKey(paper);
                  const checked = selected.includes(key);
                  return (
                    <li className="paper-card" key={key}>
                      <div className="paper-card-top">
                        <span className="paper-number">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div className="paper-meta">
                          <span className={`source-chip ${paper.source}`}>
                            {paper.source === "arxiv" ? "arXiv" : "OpenAlex"}
                          </span>
                          {paper.year && <span>{paper.year}</span>}
                          {paper.citationCount !== null && (
                            <span>
                              {paper.citationCount.toLocaleString()} 次引用
                            </span>
                          )}
                          {paper.synthetic && (
                            <span className="source-chip synthetic">
                              合成测试数据
                            </span>
                          )}
                        </div>
                        <label className="compare-check">
                          <input
                            aria-label={`选择比较：${paper.title}`}
                            checked={checked}
                            disabled={!checked && selected.length >= 3}
                            onChange={() => toggleCompare(paper)}
                            type="checkbox"
                          />
                          <span>比较</span>
                        </label>
                      </div>
                      <h3>{paper.title}</h3>
                      <p className="paper-authors">
                        {paper.authors.length
                          ? paper.authors.slice(0, 5).join(" · ")
                          : "作者信息未提供"}
                        {paper.authors.length > 5 ? " 等" : ""}
                      </p>
                      <p className="paper-abstract">
                        {paper.abstract ||
                          "来源未提供摘要。可打开原文页面查看更多信息。"}
                      </p>
                      <div className="paper-card-bottom">
                        <span className="paper-id">
                          {paper.id}
                          {paper.venue ? ` · ${paper.venue}` : ""}
                        </span>
                        <button
                          className="detail-button"
                          onClick={() => void openDetails(paper)}
                          type="button"
                        >
                          查看详情 <span aria-hidden="true">↗</span>
                        </button>
                        {source !== "library" && (
                          <button
                            className="detail-button"
                            disabled={libraryEntries.some(
                              (entry) =>
                                entry.source === paper.source &&
                                entry.source_id === paper.id,
                            )}
                            onClick={() => void saveToLibrary(paper)}
                            type="button"
                          >
                            {libraryEntries.some(
                              (entry) =>
                                entry.source === paper.source &&
                                entry.source_id === paper.id,
                            )
                              ? "已加入个人库"
                              : "加入个人库"}
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          <section
            className="results-section"
            aria-labelledby="personal-library-title"
          >
            <div className="results-heading">
              <div>
                <h2 id="personal-library-title">我的论文库</h2>
              </div>
              <span>{libraryEntries.length} 条元数据记录</span>
            </div>
            {privateDocumentsError && (
              <p className="state-card error-state" role="status">
                文档状态暂时无法更新，当前仍显示最近一次成功读取的记录。
              </p>
            )}
            {libraryEntries.length === 0 ? (
              <p className="state-card idle-state">
                将感兴趣的论文加入个人库。加入记录只保存元数据，不会自动下载全文。
              </p>
            ) : (
              <ul className="paper-list">
                {libraryEntries.map((entry) => (
                  <li className="paper-card" key={entry.id}>
                    <div className="library-entry-header">
                      <span className={`source-chip ${entry.source}`}>
                        {entry.source === "arxiv" ? "arXiv" : "OpenAlex"}
                      </span>
                      <span className="paper-id">{entry.source_id}</span>
                      <span className="library-paper-title">
                        {entry.metadata?.title ?? "标题尚未保存"}
                      </span>
                      <a
                        className="text-button"
                        href={
                          entry.metadata?.sourceUrl ??
                          (entry.source === "arxiv"
                            ? `https://arxiv.org/abs/${encodeURIComponent(entry.source_id)}`
                            : `https://openalex.org/${encodeURIComponent(entry.source_id)}`)
                        }
                        target="_blank"
                        rel="noreferrer"
                      >
                        打开原文页
                      </a>
                      <button
                        className="text-button"
                        onClick={() => void removeFromLibrary(entry)}
                        type="button"
                      >
                        移除
                      </button>
                    </div>
                    <div className="private-document-list">
                      {privateDocuments
                        .filter(
                          (document) => document.library_entry_id === entry.id,
                        )
                        .map((document) => (
                          <div
                            className="private-document-row"
                            key={document.id}
                          >
                            <span>
                              {document.original_filename} ·{" "}
                              {documentStateLabel(document.state)}
                              {document.state === "indexed" &&
                                ` · ${document.chunk_count} 个解析片段（图表内容暂不可用于问答）`}
                              {document.state === "failed" &&
                                ` · ${documentFailureLabel(document.error_code)}`}
                            </span>
                            {document.state === "failed" && (
                              <button
                                className="text-button"
                                onClick={() =>
                                  void retryPrivateDocument(document)
                                }
                                type="button"
                              >
                                重试解析
                              </button>
                            )}
                            <button
                              className="text-button"
                              onClick={() =>
                                void deletePrivateDocument(document)
                              }
                              type="button"
                              disabled={
                                document.state === "queued" ||
                                document.state === "processing"
                              }
                            >
                              删除 PDF
                            </button>
                          </div>
                        ))}
                    </div>
                    <form
                      className="private-document-form"
                      onSubmit={(event) =>
                        void uploadPrivateDocument(event, entry)
                      }
                    >
                      <label>
                        添加私有 PDF
                        <input
                          name="file"
                          type="file"
                          accept="application/pdf,.pdf"
                          required
                        />
                      </label>
                      <label className="rights-attestation">
                        <input
                          name="rights_attested"
                          type="checkbox"
                          value="true"
                          required
                        />
                        我拥有该文稿版权或已获得处理授权；仅在我的账号内解析和检索。
                      </label>
                      <button
                        className="text-button"
                        type="submit"
                        disabled={uploadingDocumentId === entry.id}
                      >
                        {uploadingDocumentId === entry.id
                          ? "提交中…"
                          : "上传并解析"}
                      </button>
                    </form>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section
            className="results-section"
            aria-labelledby="personal-documents-title"
          >
            <div className="results-heading">
              <div>
                <span className="section-index">私人文稿</span>
                <h2 id="personal-documents-title">我的稿件</h2>
              </div>
            </div>
            {privateDocumentsError && (
              <p className="state-card error-state" role="status">
                文档状态暂时无法更新，当前仍显示最近一次成功读取的记录。
              </p>
            )}
            <p className="compare-hint">
              上传你写的稿件，解析后可在问答中引用。文件仅当前账号可见；使用云端模型问答时，命中的摘录会发送给所配置的模型服务。
            </p>
            <form
              className="private-document-form"
              onSubmit={(event) => void uploadPrivateDocument(event)}
            >
              <label>
                稿件标题
                <input name="title" type="text" maxLength={500} required />
              </label>
              <label>
                选择 PDF
                <input
                  name="file"
                  type="file"
                  accept="application/pdf,.pdf"
                  required
                />
              </label>
              <label className="rights-attestation">
                <input
                  name="rights_attested"
                  type="checkbox"
                  value="true"
                  required
                />
                我拥有该稿件版权或已获得处理授权；仅在我的账号内解析和检索。
              </label>
              <button
                className="text-button"
                type="submit"
                disabled={uploadingDocumentId === "personal"}
              >
                {uploadingDocumentId === "personal" ? "提交中…" : "上传并解析"}
              </button>
            </form>
            {privateDocuments.some(
              (document) => document.source_type === "personal",
            ) ? (
              <div className="private-document-list">
                {privateDocuments
                  .filter((document) => document.source_type === "personal")
                  .map((document) => (
                    <div className="private-document-row" key={document.id}>
                      <span>
                        <strong>{document.title}</strong> ·{" "}
                        {document.original_filename} ·{" "}
                        {documentStateLabel(document.state)}
                        {document.state === "indexed" && (
                          <>
                            {" "}
                            · {document.chunk_count}{" "}
                            个解析片段（图表内容暂不可用于问答）
                          </>
                        )}
                        {document.state === "failed" && (
                          <> · {documentFailureLabel(document.error_code)}</>
                        )}
                      </span>
                      {document.state === "failed" && (
                        <button
                          className="text-button"
                          onClick={() => void retryPrivateDocument(document)}
                          type="button"
                        >
                          重试解析
                        </button>
                      )}
                      <button
                        className="text-button"
                        onClick={() => void deletePrivateDocument(document)}
                        type="button"
                        disabled={
                          document.state === "queued" ||
                          document.state === "processing"
                        }
                      >
                        删除 PDF
                      </button>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="state-card idle-state">还没有上传稿件。</p>
            )}
          </section>

          {selectedPapers.length > 0 && (
            <section className="compare-section" aria-label="论文比较">
              <div className="compare-heading">
                <div>
                  <h2>
                    比较论文 <small>{selectedPapers.length}/3</small>
                  </h2>
                </div>
                <button
                  className="text-button"
                  onClick={() => setSelected([])}
                  type="button"
                >
                  清除选择
                </button>
              </div>
              {selectedPapers.length < 2 ? (
                <p className="compare-hint">
                  再选择一篇论文即可比较；最多选择三篇。
                </p>
              ) : (
                <div
                  className="compare-table-wrap"
                  role="region"
                  aria-label="论文元数据对比"
                  tabIndex={0}
                >
                  <table className="compare-table">
                    <thead>
                      <tr>
                        <th scope="col">字段</th>
                        {selectedPapers.map((paper) => (
                          <th key={paperKey(paper)} scope="col">
                            {paper.title}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <CompareRow
                        label="来源"
                        values={selectedPapers.map((paper) =>
                          paper.source === "arxiv" ? "arXiv" : "OpenAlex",
                        )}
                      />
                      <CompareRow
                        label="年份"
                        values={selectedPapers.map(
                          (paper) => paper.year?.toString() ?? "未提供",
                        )}
                      />
                      <CompareRow
                        label="作者"
                        values={selectedPapers.map(
                          (paper) => paper.authors.join("、") || "未提供",
                        )}
                      />
                      <CompareRow
                        label="发表载体"
                        values={selectedPapers.map(
                          (paper) => paper.venue ?? "未提供",
                        )}
                      />
                      <CompareRow
                        label="引用数"
                        values={selectedPapers.map(
                          (paper) =>
                            paper.citationCount?.toLocaleString() ??
                            "来源未提供",
                        )}
                      />
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </section>

        <section
          className={`assistant-workspace${answer || agentLoading ? " has-evidence" : ""}`}
          id="assistant"
          aria-labelledby="assistant-title"
        >
          <aside className="conversation-sidebar" aria-label="对话列表">
            <div className="conversation-sidebar-header">
              <h2>对话</h2>
              <button
                className="new-conversation-button"
                onClick={() => void startNewConversation()}
                type="button"
              >
                新对话
              </button>
            </div>
            <nav className="conversation-list" aria-label="已保存的对话">
              {conversations.map((conversation) =>
                deletingConversationId === conversation.id ? (
                  <div
                    className="conversation-rename-form"
                    key={conversation.id}
                  >
                    <span className="conversation-delete-confirm">
                      删除这段对话？
                    </span>
                    <button
                      onClick={() => void deleteConversation(conversation.id)}
                      type="button"
                    >
                      删除
                    </button>
                    <button
                      onClick={() => setDeletingConversationId(null)}
                      type="button"
                    >
                      取消
                    </button>
                  </div>
                ) : editingConversationId === conversation.id ? (
                  <form
                    className="conversation-rename-form"
                    key={conversation.id}
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveConversationTitle(conversation.id);
                    }}
                  >
                    <input
                      aria-label="对话名称"
                      maxLength={120}
                      onChange={(event) =>
                        setEditingConversationTitle(event.target.value)
                      }
                      value={editingConversationTitle}
                    />
                    <button type="submit">保存</button>
                    <button
                      onClick={() => setEditingConversationId(null)}
                      type="button"
                    >
                      取消
                    </button>
                  </form>
                ) : (
                  <div className="conversation-row" key={conversation.id}>
                    <button
                      aria-current={
                        conversation.id === conversationId ? "page" : undefined
                      }
                      className={
                        conversation.id === conversationId
                          ? "conversation-link active"
                          : "conversation-link"
                      }
                      onClick={() => onSelectConversation(conversation.id)}
                      type="button"
                    >
                      {conversation.title}
                    </button>
                    <button
                      aria-label={`重命名：${conversation.title}`}
                      className="rename-conversation-button"
                      onClick={() => {
                        setEditingConversationId(conversation.id);
                        setDeletingConversationId(null);
                        setEditingConversationTitle(conversation.title);
                        setConversationActionError(null);
                      }}
                      type="button"
                    >
                      ⋯
                    </button>
                    <button
                      aria-label={`删除：${conversation.title}`}
                      className="rename-conversation-button"
                      onClick={() => {
                        setDeletingConversationId(conversation.id);
                        setEditingConversationId(null);
                        setConversationActionError(null);
                      }}
                      type="button"
                    >
                      ×
                    </button>
                  </div>
                ),
              )}
            </nav>
            {conversationActionError && (
              <p className="conversation-action-error" role="alert">
                {conversationActionError}
              </p>
            )}
          </aside>
          <section className="chat-panel" aria-label="对话">
            <header className="chat-header">
              <div>
                <h1 id="assistant-title">科研助手</h1>
                <p>对话保存在你的账号中；每次提问都会重新检索证据。</p>
              </div>
            </header>
            {history.length === 0 && (
              <div className="chat-welcome">
                <p>例如：</p>
                <div className="sample-prompts" aria-label="示例问题">
                  {sampleQuestions.map((sample) => (
                    <button
                      key={sample}
                      onClick={() => useSampleQuestion(sample)}
                      type="button"
                    >
                      {sample}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <ol className="conversation-history" aria-label="对话记录">
              {[
                ...history,
                ...(pendingQuestion
                  ? [{ role: "user" as const, content: pendingQuestion }]
                  : []),
              ].map((turn, index) => (
                <li className={`conversation-turn ${turn.role}`} key={index}>
                  <span className="chat-speaker">
                    {turn.role === "user" ? "你" : "PaperTrail"}
                  </span>
                  <p>{turn.content}</p>
                </li>
              ))}
              <li
                className="conversation-end"
                ref={conversationEndRef}
                aria-hidden="true"
              />
            </ol>
            <form className="agent-form" onSubmit={askAgent}>
              <label className="visually-hidden" htmlFor="agent-question">
                你的研究问题
              </label>
              <div className="chat-composer">
                <textarea
                  id="agent-question"
                  maxLength={1000}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder="输入研究问题…"
                  rows={2}
                  value={question}
                />
                <button
                  className="ask-button"
                  disabled={
                    agentLoading ||
                    !conversationId ||
                    conversationLoading ||
                    !question.trim()
                  }
                  type="submit"
                >
                  {agentLoading ? "处理中…" : "发送"}
                </button>
              </div>
              <div className="agent-form-footer">
                <span>{question.length}/1000</span>
                {history.length > 0 && (
                  <span className="context-note">
                    对话已保存 · 最近原文与研究摘要共同提供上下文
                  </span>
                )}
                {history.length > 0 && (
                  <button
                    className="text-button"
                    onClick={resetAgentConversation}
                    type="button"
                  >
                    清空对话
                  </button>
                )}
                {agentLoading && (
                  <button
                    className="cancel-button"
                    onClick={cancelAgentRun}
                    type="button"
                    disabled={agentCancelling}
                  >
                    {agentCancelling ? "正在确认取消…" : "取消"}
                  </button>
                )}
              </div>
            </form>
            {answer?.context_state?.objective && (
              <details className="research-context">
                <summary>
                  当前研究任务：{answer.context_state.objective}
                </summary>
                <p>{answer.context_state.summary || "尚无研究摘要。"}</p>
                {Object.values(answer.context_state.catalog ?? {}).map(
                  (doc, index) => (
                    <p key={index}>{doc.title}</p>
                  ),
                )}
                <small>
                  摘要用于延续目标与约束；论文结论仍需重新检索证据。清空对话会同时清除摘要。
                </small>
              </details>
            )}
            {agentError && (
              <div className="inline-error" role="alert">
                {agentError}
                <button
                  onClick={() => void askAgentFromCurrent()}
                  type="button"
                >
                  重试
                </button>
              </div>
            )}
          </section>
          {(answer || agentLoading) && (
            <aside className="evidence-pane" aria-label="引用与证据">
              <h2>引用与证据</h2>
              {agentLoading && (
                <div className="answer-state" role="status">
                  <span className="spinner" />
                  正在检索论文…
                </div>
              )}
              {answer && !agentLoading && <AgentResult answer={answer} />}
            </aside>
          )}
        </section>
      </div>

      {detail && (
        <div
          className="dialog-backdrop"
          onClick={() => setDetail(null)}
          role="presentation"
        >
          <section
            aria-labelledby="detail-title"
            aria-modal="true"
            className="detail-dialog"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setDetail(null);
            }}
            role="dialog"
            tabIndex={-1}
          >
            <div className="dialog-header">
              <span className="section-index">
                PAPER DETAIL / {detail.source.toUpperCase()}
              </span>
              <button
                aria-label="关闭论文详情"
                className="close-button"
                onClick={() => setDetail(null)}
                type="button"
              >
                ×
              </button>
            </div>
            {detailLoading ? (
              <div className="state-card" role="status">
                <span className="spinner" />
                正在读取论文详情…
              </div>
            ) : (
              <>
                <h2 id="detail-title">{detail.title}</h2>
                {detailError && (
                  <div className="inline-error" role="alert">
                    {detailError}
                  </div>
                )}
                <p className="detail-authors">
                  {detail.authors.join(" · ") || "作者信息未提供"}
                </p>
                <div className="detail-facts">
                  <span>{detail.year ?? "年份未提供"}</span>
                  <span>{detail.venue ?? "发表载体未提供"}</span>
                  <span>
                    {detail.citationCount === null
                      ? "引用数未提供"
                      : `${detail.citationCount.toLocaleString()} 次引用`}
                  </span>
                </div>
                <h3>摘要</h3>
                <p className="detail-abstract">
                  {detail.abstract || "来源未提供摘要。"}
                </p>
                <a
                  className="source-link"
                  href={detail.sourceUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  在 {detail.source === "arxiv" ? "arXiv" : "OpenAlex"}{" "}
                  查看原始记录 ↗
                </a>
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );

  async function askAgentFromCurrent() {
    if (!question.trim()) return;
    await askAgent();
  }
}

function CompareRow({ label, values }: { label: string; values: string[] }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      {values.map((value, index) => (
        <td key={`${label}-${index}`}>{value}</td>
      ))}
    </tr>
  );
}

function appendConversation(
  current: AgentTurn[],
  question: string,
  answer: string,
): AgentTurn[] {
  const turns = [
    ...current,
    { role: "user" as const, content: question },
    { role: "assistant" as const, content: answer },
  ];
  while (
    turns.length > 8 ||
    turns.reduce((total, turn) => total + turn.content.length, 0) > 8_000
  ) {
    turns.splice(0, 2);
  }
  return turns;
}

function AgentResult({ answer }: { answer: AgentResponse }) {
  const statusLabel: Record<string, string> = {
    completed: "已完成",
    insufficient_evidence: "证据不足",
    unverified_evidence: "证据核验失败",
    context_budget_exceeded: "上下文预算已用尽",
    token_budget_exceeded: "Token 预算已用尽",
    usage_unavailable: "用量无法核验，已停止调用",
    cancelled: "任务已取消",
    model_disabled: "模型未启用",
  };
  return (
    <div className="agent-result" aria-live="polite">
      <div className={`answer-status ${answer.status}`}>
        <span className="status-dot" />
        {statusLabel[answer.status] ?? answer.status}
      </div>
      {answer.claims.length > 0 && (
        <section className="claim-list" aria-label="逐条主张与证据">
          <h3>逐条主张与证据</h3>
          {answer.claims.map((claim, index) => (
            <article className="claim-card" key={`${claim.text}-${index}`}>
              {claim.evidence.map((evidence, evidenceIndex) => (
                <blockquote
                  key={`${evidence.source_id}-${evidence.chunk_id}-${evidenceIndex}`}
                >
                  {evidence.evidence_type === "visual_analysis" && (
                    <p className="license-badge">MinerU AI 图表解读 · 未核验</p>
                  )}
                  <p>{evidence.quote}</p>
                  <cite>
                    {evidence.source_id} ·{" "}
                    {evidence.evidence_type !== "metadata" && evidence.chunk_id
                      ? (answer.citations
                          .find(
                            (citation) =>
                              citation.openalex_id === evidence.source_id ||
                              citation.arxiv_id === evidence.source_id ||
                              citation.personal_id === evidence.source_id,
                          )
                          ?.evidence.find(
                            (span) =>
                              span.chunk_id === evidence.chunk_id &&
                              (span.evidence_type ?? "fulltext") ===
                                evidence.evidence_type,
                          )?.locator ?? evidence.chunk_id)
                      : `元数据字段：${evidence.source_field}`}
                  </cite>
                </blockquote>
              ))}
            </article>
          ))}
        </section>
      )}
      {answer.warnings.map((warning) => (
        <p className="answer-warning" key={warning}>
          {warning}
        </p>
      ))}
      {answer.status === "completed" && (
        <p className="answer-warning">
          已核对来源和摘录位置；系统尚未判断摘录是否在语义上充分支持主张。
        </p>
      )}
      {answer.citations.length > 0 && (
        <div className="citation-list">
          <h3>
            来源与证据 <span>{answer.citations.length}</span>
          </h3>
          {answer.citations.map((citation, index) => (
            <CitationCard
              citation={citation}
              index={index}
              key={`${citation.source}-${citation.arxiv_id ?? citation.openalex_id ?? citation.personal_id}-${index}`}
            />
          ))}
        </div>
      )}
      {answer.citations.length === 0 && (
        <p className="no-citation">本次回答没有可展示的论文引用。</p>
      )}
      <details className="run-details">
        <summary>运行记录与工程指标</summary>
        <div className="run-metrics">
          <span>耗时 {answer.duration_ms} ms</span>
          <span>工具调用 {answer.tool_calls}</span>
          <span>模型轮次 {answer.model_steps}</span>
          <span>Token {answer.total_observed_tokens}</span>
        </div>
        <ol>
          {answer.trace.map((event) => (
            <li key={event.sequence}>
              <span>{event.sequence.toString().padStart(2, "0")}</span>
              <strong>{event.name}</strong>
              <em>
                {event.status === "no_results"
                  ? "无结果"
                  : event.status === "incomplete"
                    ? "输出未完成"
                    : event.status}
              </em>
            </li>
          ))}
        </ol>
        <code>{answer.run_id ?? "未返回运行 ID"}</code>
      </details>
    </div>
  );
}

function CitationCard({
  citation,
  index,
}: {
  citation: Citation;
  index: number;
}) {
  const evidenceId =
    citation.arxiv_id ?? citation.openalex_id ?? citation.personal_id ?? "";
  return (
    <article className="citation-card">
      <div className="citation-kicker">
        <span>REF {String(index + 1).padStart(2, "0")}</span>
        <span>
          {citation.source === "personal"
            ? "我的稿件"
            : citation.source === "arxiv"
              ? "arXiv"
              : "OpenAlex"}{" "}
          · {evidenceId}
        </span>
      </div>
      <h4>
        {citation.source === "personal" || !citation.source_url ? (
          citation.title
        ) : (
          <a href={citation.source_url} rel="noreferrer" target="_blank">
            {citation.title} ↗
          </a>
        )}
      </h4>
      {citation.attribution && (
        <p className="citation-license">{citation.attribution}</p>
      )}
      {citation.license_id && (
        <p className="license-badge">全文许可：{citation.license_id}</p>
      )}
      {citation.private_processing && (
        <p className="license-badge">私有全文 · 仅当前账号可见</p>
      )}
      {citation.evidence.map((span) => (
        <blockquote
          key={`${span.chunk_id}:${span.evidence_type ?? "fulltext"}`}
        >
          {span.evidence_type === "visual_analysis" ? (
            <>
              <p className="license-badge">MinerU AI 图表解读 · 未核验</p>
              {span.excerpt && <p>原文图注：{span.excerpt}</p>}
              <p>{span.visual_description}</p>
            </>
          ) : (
            <p>{span.excerpt}</p>
          )}
          <cite>
            {span.locator}
            {span.parser_version && ` · ${span.parser_version}`} ·{" "}
            {span.chunk_id}
          </cite>
        </blockquote>
      ))}
    </article>
  );
}

function paperKey(paper: Paper): string {
  return `${paper.source}:${paper.id}`;
}

function readError(body: unknown): string {
  if (body && typeof body === "object") {
    const root = body as {
      detail?: unknown;
      status?: unknown;
      answer?: unknown;
    };
    if (
      ["model_disabled", "model_unavailable", "usage_unavailable"].includes(
        String(root.status),
      ) &&
      typeof root.answer === "string"
    ) {
      return root.answer;
    }
    if (typeof root.detail === "string") return root.detail;
    if (root.detail && typeof root.detail === "object") {
      const detail = root.detail as {
        code?: unknown;
        message?: unknown;
        run_id?: unknown;
      };
      if (detail.code === "daily_agent_token_budget_exceeded") {
        return "今日科研助手 token 额度已用完，请明日再试或联系管理员。";
      }
      if (detail.code === "agent_run_interrupted") {
        const runId = typeof detail.run_id === "string" ? detail.run_id : null;
        return runId
          ? `科研助手执行中断。若再次发生，请记录运行编号 ${runId} 并联系维护者。`
          : "科研助手执行中断，请稍后重试。";
      }
      const message = detail.message;
      if (typeof message === "string") return message;
    }
  }
  return "服务暂时无法完成请求，请检查连接后重试。";
}

function documentStateLabel(state: PrivateDocument["state"]): string {
  return {
    queued: "等待解析",
    processing: "MinerU 解析中",
    indexed: "已入库",
    failed: "解析失败",
  }[state];
}

function documentFailureLabel(code?: string | null): string {
  return (
    {
      reindex_required: "解析版本已更新，请重新解析",
      worker_interrupted: "服务重启中断，可重试",
      mineru_timeout: "解析超时",
      mineru_remote_config_forbidden: "仅支持本机 MinerU 模型",
      private_index_chunk_limit: "解析片段超过上限",
      document_integrity_error: "文件校验失败",
      mineru_parse_failed: "解析未完成，请检查 PDF 或模型",
    }[code ?? ""] ?? "解析未完成，可重试"
  );
}
