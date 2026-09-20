"use client";

import { useEffect, useState } from "react";
import { getPlatformStatus } from "@/lib/api/client";

type Mode = "pc" | "laptop" | "component";
type LoadState = "loading" | "empty" | "error";
const modes: { id: Mode; title: string; hint: string; icon: string }[] = [
  { id: "pc", title: "组装台式机", hint: "按用途搭配一整套主机", icon: "▤" },
  {
    id: "laptop",
    title: "挑选笔记本",
    hint: "在性能与便携之间找到平衡",
    icon: "▱",
  },
  {
    id: "component",
    title: "选择单个零件",
    hint: "先明确需要更换的部件",
    icon: "⊞",
  },
];

export function Planner() {
  const [mode, setMode] = useState<Mode>("pc");
  const [budget, setBudget] = useState("");
  const [workload, setWorkload] = useState("办公学习");
  const [scope, setScope] = useState("仅主机");
  const [category, setCategory] = useState("CPU");
  const [summary, setSummary] = useState("");
  const [state, setState] = useState<LoadState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);
    let active = true;
    setState("loading");
    getPlatformStatus(controller.signal)
      .then(() => {
        if (active) setState("empty");
      })
      .catch(() => {
        if (active) setState("error");
      })
      .finally(() => clearTimeout(timer));
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [attempt]);

  function switchMode(next: Mode) {
    setMode(next);
    setSummary("");
    setScope(
      next === "pc" ? "仅主机" : next === "laptop" ? "笔记本整机" : "所选零件",
    );
  }

  function preview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Local text-only draft. No server profile, hard constraints, money computation or recommendation.
    setSummary(
      `${modes.find((item) => item.id === mode)?.title} · 预算上限 ${budget} 元 · ${workload} · ${mode === "component" ? category : scope}`,
    );
  }

  return (
    <section className="planner" aria-labelledby="planner-title">
      <div className="planner-heading">
        <div>
          <span className="section-kicker">开始你的选择</span>
          <h2 id="planner-title">你想选哪一种？</h2>
        </div>
        <span className="step">
          01 <span>/ 明确需求</span>
        </span>
      </div>
      <div className="mode-grid" role="group" aria-label="设备类型">
        {modes.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`mode-card ${mode === item.id ? "selected" : ""}`}
            aria-pressed={mode === item.id}
            onClick={() => switchMode(item.id)}
          >
            <span className="device-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span className="mode-text">
              <strong>{item.title}</strong>
              <span>{item.hint}</span>
            </span>
            <span className="radio-mark" aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className="workspace">
        <form
          onSubmit={preview}
          className="draft-form"
          onChange={() => setSummary("")}
        >
          <div className="form-heading">
            <h3>先写下你的需求</h3>
            <span>仅在本页预览，不会保存</span>
          </div>
          <div className="form-grid">
            <label>
              预算上限（元）
              <div className="money-input">
                <span aria-hidden="true">¥</span>
                <input
                  name="budget"
                  type="number"
                  inputMode="numeric"
                  min="1"
                  max="10000000"
                  step="1"
                  required
                  placeholder="填写你不想超过的金额"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </div>
            </label>
            <label>
              主要用途
              <select
                value={workload}
                onChange={(e) => setWorkload(e.target.value)}
              >
                <option>办公学习</option>
                <option>软件开发</option>
                <option>游戏</option>
                <option>视频剪辑</option>
                <option>3D 渲染</option>
                <option>本地 AI</option>
              </select>
            </label>
            {mode === "component" ? (
              <label>
                零件类别
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {[
                    "CPU",
                    "GPU",
                    "主板",
                    "内存",
                    "SSD",
                    "电源",
                    "机箱",
                    "散热器",
                  ].map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </label>
            ) : (
              <label>
                预算包含
                <select
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                >
                  {(mode === "pc"
                    ? ["仅主机", "主机、显示器与键鼠"]
                    : ["笔记本整机", "笔记本与外设"]
                  ).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="form-context">
              <span>地区与商品范围</span>
              <strong>中国大陆 · 全新零售</strong>
            </div>
          </div>
          <button className="primary-button" type="submit">
            预览需求 <span aria-hidden="true">→</span>
          </button>
          <p className="draft-note">
            当前可整理需求，推荐功能将在数据审核完成后开放。
          </p>
          {summary && (
            <div role="status" className="summary">
              <strong>本页需求草稿</strong>
              <p>{summary}</p>
              <p>尚未生成推荐，刷新页面将清除草稿。</p>
            </div>
          )}
        </form>
        <aside className="data-status" aria-label="数据准备状态">
          <span className="status-badge">
            <span />
            {state === "error" ? "连接待恢复" : "数据准备中"}
          </span>
          <div className="empty-symbol" aria-hidden="true">
            <span>≡</span>
            <i />
          </div>
          <div role="status" aria-live="polite">
            <h3>
              {state === "loading"
                ? "正在检查数据状态"
                : state === "error"
                  ? "暂时无法连接服务"
                  : "先核实，再推荐"}
            </h3>
            <p>
              {state === "loading"
                ? "请稍候，我们正在确认服务是否就绪。"
                : state === "error"
                  ? "暂时无法确认数据是否就绪。你仍可在左侧整理需求，稍后再试。"
                  : "商品规格与报价尚未准备好。现在不会展示未经核验的型号、价格或购买清单。"}
            </p>
          </div>
          {state === "error" ? (
            <button
              className="retry-button"
              onClick={() => setAttempt((value) => value + 1)}
            >
              重新连接
            </button>
          ) : (
            <div className="status-detail">
              <span>当前阶段</span>
              <strong>基础工程预览</strong>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
