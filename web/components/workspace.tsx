"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type {
  AgentResponse,
  Citation,
  Paper,
  SearchResponse,
  Source,
} from "@/lib/api/papers";
import { normalizeArxiv, normalizeOpenAlex } from "@/lib/api/papers";

type ServiceStatus = "checking" | "ready" | "unavailable";

const sourceLabels: Record<Source, string> = {
  openalex: "OpenAlex",
  arxiv: "arXiv",
  library: "我的文献库",
};

const sampleQuestions = [
  "这篇论文如何让 Agent 判断是否需要继续读取知识库？",
  "总结论文提出的知识库分层设计，并给出原文证据。",
];

export function Workspace() {
  const [source, setSource] = useState<Source>("openalex");
  const [query, setQuery] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [results, setResults] = useState<Paper[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>("checking");
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<Paper | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AgentResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

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
      const payload = body as SearchResponse;
      setResults(payload.items);
      setTotal(payload.total);
    } catch (cause) {
      setResults([]);
      setError(
        cause instanceof Error ? cause.message : "检索暂时失败，请重试。",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openDetails(paper: Paper) {
    setDetail(paper);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const routeSource = source === "library" ? "library" : paper.source;
      const params = new URLSearchParams({ source: routeSource, id: paper.id });
      const response = await fetch(`/api/paper?${params.toString()}`, {
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(readError(body));
      const fullPaper =
        paper.source === "arxiv"
          ? normalizeArxiv(body)
          : normalizeOpenAlex(body);
      setDetail({ ...paper, ...fullPaper, sourceUrl: paper.sourceUrl });
    } catch (cause) {
      setDetailError(
        cause instanceof Error ? cause.message : "论文详情暂时无法读取。",
      );
    } finally {
      setDetailLoading(false);
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
    if (!question.trim()) return;
    setAgentLoading(true);
    setAgentError(null);
    setAnswer(null);
    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(readError(body));
      setAnswer(body as AgentResponse);
    } catch (cause) {
      setAgentError(
        cause instanceof Error ? cause.message : "研究助理暂时不可用，请重试。",
      );
    } finally {
      setAgentLoading(false);
    }
  }

  function useSampleQuestion(value: string) {
    setQuestion(value);
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="PaperTrail 工作区首页">
          <span className="brand-mark" aria-hidden="true">
            P<span>.</span>
          </span>
          <span>PaperTrail</span>
          <span className="brand-caption">RESEARCH DESK</span>
        </a>
        <nav className="topnav" aria-label="主导航">
          <a className="active" href="#search">
            探索文献
          </a>
          <a href="#assistant">研究助理</a>
          <a href="#principles">使用说明</a>
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
              ? "研究服务在线"
              : "服务未连接"}
        </div>
      </header>

      <div className="page-grid" id="top">
        <section className="main-column" aria-label="论文检索与比较">
          <div className="intro-block">
            <div className="eyebrow">
              <span>研究工作区</span>
              <i />
              从问题出发，沿证据前进
            </div>
            <h1>
              把文献线索，<em>变成研究脉络。</em>
            </h1>
            <p>
              搜索可信学术来源，比较关键研究，并让每个回答都能回到原文证据。
            </p>
          </div>

          <section
            className="search-panel"
            id="search"
            aria-labelledby="search-title"
          >
            <div className="panel-heading">
              <div>
                <span className="section-index">01 / DISCOVER</span>
                <h2 id="search-title">探索论文</h2>
              </div>
              <span className="panel-note">元数据来自公开学术来源</span>
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
                  {item === "library" && (
                    <span className="local-tag">LOCAL</span>
                  )}
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
                <span>最多展示 10 条 · 不会自动下载全文</span>
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
                <span className="section-index">02 / RESULTS</span>
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
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {selectedPapers.length > 0 && (
            <section className="compare-section" aria-label="论文比较">
              <div className="compare-heading">
                <div>
                  <span className="section-index">03 / COMPARE</span>
                  <h2>
                    并列比较 <small>{selectedPapers.length}/3</small>
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

          <section className="principles" id="principles">
            <span className="section-index">EVIDENCE FIRST</span>
            <p>
              论文记录来自 OpenAlex、arXiv
              或你的本地资料。未授权的全文不会被检索；信息缺失时会明确标注。
            </p>
          </section>
        </section>

        <aside
          className="assistant-column"
          id="assistant"
          aria-labelledby="assistant-title"
        >
          <div className="assistant-card">
            <div className="assistant-topline">
              <span className="assistant-icon" aria-hidden="true">
                ✳
              </span>
              <span>READ-ONLY RESEARCH AGENT</span>
            </div>
            <span className="section-index">04 / SYNTHESIZE</span>
            <h2 id="assistant-title">研究助理</h2>
            <p className="assistant-intro">
              围绕论文提出问题。回答将基于本轮工具实际读取到的资料，并列出可追溯引用。
            </p>
            <div className="sample-prompts" aria-label="示例问题">
              {sampleQuestions.map((sample) => (
                <button
                  key={sample}
                  onClick={() => useSampleQuestion(sample)}
                  type="button"
                >
                  “{sample}”
                </button>
              ))}
            </div>
            <form className="agent-form" onSubmit={askAgent}>
              <label htmlFor="agent-question">你的研究问题</label>
              <textarea
                id="agent-question"
                maxLength={1000}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="例如：这篇研究的主要贡献与局限是什么？"
                rows={4}
                value={question}
              />
              <div className="agent-form-footer">
                <span>{question.length}/1000</span>
                <button
                  className="ask-button"
                  disabled={agentLoading || !question.trim()}
                  type="submit"
                >
                  {agentLoading ? "正在研究…" : "询问研究助理"}
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
            </form>
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
            {agentLoading && (
              <div className="answer-state" role="status">
                <span className="spinner" />
                正在检索证据并组织回答…
              </div>
            )}
            {answer && !agentLoading && <AgentResult answer={answer} />}
            {!answer && !agentLoading && !agentError && (
              <div className="assistant-empty">
                <span>↳</span>
                <p>引用与证据片段会显示在这里。若证据不足，助理会说明缺口。</p>
              </div>
            )}
            <div className="assistant-boundary">
              <span>权限边界</span>
              <p>
                仅可使用已登记的只读论文工具。不能抓取任意网页，也不能修改或写入论文资料。
              </p>
            </div>
          </div>
        </aside>
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
      <footer className="site-footer">
        <span>PaperTrail · 研究工作区</span>
        <span>来源可查 · 证据优先 · 只读工具</span>
      </footer>
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

function AgentResult({ answer }: { answer: AgentResponse }) {
  return (
    <div className="agent-result" aria-live="polite">
      <div className={`answer-status ${answer.status}`}>
        <span className="status-dot" />
        {answer.status === "completed"
          ? "已完成"
          : answer.status === "insufficient_evidence"
            ? "证据不足"
            : answer.status === "model_disabled"
              ? "模型未启用"
              : answer.status}
      </div>
      <p className="answer-text">{answer.answer}</p>
      {answer.warnings.map((warning) => (
        <p className="answer-warning" key={warning}>
          {warning}
        </p>
      ))}
      {answer.citations.length > 0 && (
        <div className="citation-list">
          <h3>
            来源与证据 <span>{answer.citations.length}</span>
          </h3>
          {answer.citations.map((citation, index) => (
            <CitationCard
              citation={citation}
              index={index}
              key={`${citation.source}-${citation.arxiv_id ?? citation.openalex_id}-${index}`}
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
          <span>
            Token {answer.model_input_tokens + answer.model_output_tokens}
          </span>
        </div>
        <ol>
          {answer.trace.map((event) => (
            <li key={event.sequence}>
              <span>{event.sequence.toString().padStart(2, "0")}</span>
              <strong>{event.name}</strong>
              <em>{event.status}</em>
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
  const evidenceId = citation.arxiv_id ?? citation.openalex_id ?? "";
  return (
    <article className="citation-card">
      <div className="citation-kicker">
        <span>REF {String(index + 1).padStart(2, "0")}</span>
        <span>
          {citation.source === "arxiv" ? "arXiv" : "OpenAlex"} · {evidenceId}
        </span>
      </div>
      <h4>
        <a href={citation.source_url} rel="noreferrer" target="_blank">
          {citation.title} ↗
        </a>
      </h4>
      {citation.attribution && (
        <p className="citation-license">{citation.attribution}</p>
      )}
      {citation.license_id && (
        <p className="license-badge">全文许可：{citation.license_id}</p>
      )}
      {citation.evidence.map((span) => (
        <blockquote key={span.chunk_id}>
          <p>{span.excerpt}</p>
          <cite>
            {span.locator} · {span.chunk_id}
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
    const root = body as { detail?: unknown };
    if (typeof root.detail === "string") return root.detail;
    if (root.detail && typeof root.detail === "object") {
      const message = (root.detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return "服务暂时无法完成请求，请检查连接后重试。";
}
