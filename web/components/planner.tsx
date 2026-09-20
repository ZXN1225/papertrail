"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getPlatformStatus,
  sessionRequest,
  yuanToMinor,
  type ProfileInput,
  type ProfileSnapshot,
  type SessionState,
} from "@/lib/api/client";

type Mode = ProfileInput["mode"];
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
const workloadOptions = {
  office: "办公学习",
  development: "软件开发",
  gaming: "游戏",
  video: "视频剪辑",
  rendering: "3D 渲染",
  ai: "本地 AI",
};
const categories = {
  cpu: "CPU",
  gpu: "GPU",
  motherboard: "主板",
  memory: "内存",
  ssd: "SSD",
  psu: "电源",
  case: "机箱",
  cooler: "散热器",
};
const scopeOptions = {
  tower: "主机",
  laptop: "笔记本整机",
  component: "所选零件",
  monitor: "显示器",
  peripherals: "键鼠等外设",
  os: "系统许可",
  assembly: "装机服务",
  shipping: "运费",
};
const basicScope = (mode: Mode): ProfileInput["budget_scope"] => [
  mode === "pc" ? "tower" : mode,
];
type FormState = {
  mode: Mode;
  budget: string;
  workloads: ProfileInput["workloads"];
  scope: ProfileInput["budget_scope"];
  category: NonNullable<ProfileInput["component_category"]>;
  exclusions: string;
  wifi: boolean;
  weight: string;
};
const emptyForm = (): FormState => ({
  mode: "pc",
  budget: "",
  workloads: ["office"],
  scope: ["tower"],
  category: "cpu",
  exclusions: "",
  wifi: false,
  weight: "",
});
const moneyText = (minor: number) =>
  `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;
function fromProfile(profile: ProfileInput): FormState {
  return {
    mode: profile.mode,
    budget: moneyText(profile.budget_max_minor),
    workloads: profile.workloads,
    scope: profile.budget_scope,
    category: profile.component_category || "cpu",
    exclusions: profile.excluded_brands?.join("，") || "",
    wifi: profile.pc_constraints?.wifi_required === true,
    weight: profile.laptop_constraints?.max_weight_g?.toString() || "",
  };
}
function toProfile(form: FormState): ProfileInput {
  return {
    mode: form.mode,
    market: "CN",
    currency: "CNY",
    budget_max_minor: yuanToMinor(form.budget),
    workloads: form.workloads,
    budget_scope: form.scope,
    excluded_brands: form.exclusions
      .split(/[,，]/)
      .map((x) => x.trim())
      .filter(Boolean),
    pc_constraints: form.mode === "pc" ? { wifi_required: form.wifi } : null,
    laptop_constraints:
      form.mode === "laptop"
        ? { max_weight_g: form.weight ? Number(form.weight) : null }
        : null,
    component_category: form.mode === "component" ? form.category : null,
  };
}

export function Planner() {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [session, setSession] = useState<SessionState | null>(null);
  const [saved, setSaved] = useState<ProfileSnapshot | null>(null);
  const [busy, setBusy] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [needsReload, setNeedsReload] = useState(false);
  const [status, setStatus] = useState<"loading" | "empty" | "error">(
    "loading",
  );
  const [attempt, setAttempt] = useState(0);

  function accept(value: SessionState | null) {
    setSession(value);
    setSaved(value?.profile || null);
    setForm(value?.profile ? fromProfile(value.profile.profile) : emptyForm());
    setDirty(false);
    setNeedsReload(false);
    setError("");
  }
  useEffect(() => {
    let active = true;
    sessionRequest<SessionState>("sessions/current")
      .then((value) => {
        if (active) accept(value);
      })
      .catch((reason) => {
        if (active && !(reason instanceof ApiError && reason.status === 404)) {
          setError("暂时无法读取保存的需求，请重新读取后再保存。");
          setNeedsReload(true);
        }
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);
    let active = true;
    setStatus("loading");
    getPlatformStatus(controller.signal)
      .then(() => {
        if (active) setStatus("empty");
      })
      .catch(() => {
        if (active) setStatus("error");
      })
      .finally(() => clearTimeout(timer));
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [attempt]);

  function change(values: Partial<FormState>) {
    setForm((old) => ({ ...old, ...values }));
    setDirty(true);
    setNotice("");
  }
  function switchMode(mode: Mode) {
    if (mode !== form.mode)
      change({
        mode,
        scope: basicScope(mode),
        wifi: false,
        weight: "",
        category: "cpu",
      });
  }
  function fail(reason: unknown) {
    setError(
      reason instanceof ApiError
        ? reason.message
        : "连接失败，保存结果尚未确认，请读取最新需求后再操作。",
    );
    if (
      !(reason instanceof ApiError) ||
      [403, 404, 409, 503].includes(reason.status)
    )
      setNeedsReload(true);
  }
  async function reload() {
    setBusy(true);
    setNotice("");
    try {
      accept(await sessionRequest<SessionState>("sessions/current"));
      setNotice("已读取最新保存的需求。");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 404) {
        accept(null);
        setNotice("会话已结束，可以开始新的需求。");
      } else fail(reason);
    } finally {
      setBusy(false);
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!form.workloads.length) {
      setError("请至少选择一种用途。");
      return;
    }
    let input: ProfileInput;
    try {
      input = toProfile(form);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预算格式不正确。");
      return;
    }
    setBusy(true);
    try {
      let active = session;
      if (!active) {
        active = await sessionRequest<SessionState>("sessions", "POST", {});
        setSession(active);
        if (active.profile) {
          setSaved(active.profile);
          setNeedsReload(true);
          setError("已有保存的需求，请读取最新版本后再修改。");
          return;
        }
      }
      let result: ProfileSnapshot;
      if (saved) {
        const patch: Record<string, unknown> = {};
        for (const [key, value] of Object.entries(input)) {
          if (
            JSON.stringify(value) !==
            JSON.stringify(saved.profile[key as keyof ProfileInput])
          )
            patch[key] = value;
        }
        if (!Object.keys(patch).length) {
          setDirty(false);
          setNotice("需求没有变化，已保留当前版本。");
          return;
        }
        result = await sessionRequest<ProfileSnapshot>(
          `profiles/${saved.id}`,
          "PATCH",
          { expected_revision: saved.revision, patch },
          active.csrf_token,
        );
      } else
        result = await sessionRequest<ProfileSnapshot>(
          "profiles",
          "POST",
          input,
          active.csrf_token,
        );
      accept({ ...active, profile: result });
      setNotice(`需求已保存 · 版本 ${result.revision}`);
    } catch (reason) {
      fail(reason);
    } finally {
      setBusy(false);
    }
  }
  async function clear(action: "reset" | "delete") {
    if (
      !window.confirm(
        action === "reset"
          ? "开始新需求会删除当前会话与所有已保存版本，是否继续？"
          : "删除当前会话及所有已保存需求版本，是否继续？",
      )
    )
      return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (session) {
        if (action === "reset")
          accept(
            await sessionRequest<SessionState>(
              "sessions/reset",
              "POST",
              {},
              session.csrf_token,
            ),
          );
        else {
          await sessionRequest(
            "sessions/current",
            "DELETE",
            {},
            session.csrf_token,
          );
          accept(null);
        }
      } else accept(null);
      setNotice(
        action === "reset"
          ? "已开始新需求，旧需求已清除。"
          : "已删除保存的需求与会话。",
      );
    } catch (reason) {
      fail(reason);
    } finally {
      setBusy(false);
    }
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
            disabled={busy}
            key={item.id}
            type="button"
            className={`mode-card ${form.mode === item.id ? "selected" : ""}`}
            aria-pressed={form.mode === item.id}
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
        <form onSubmit={save} className="draft-form">
          <div className="form-heading">
            <h3>先写下你的需求</h3>
            <span>
              {busy
                ? "正在处理…"
                : dirty
                  ? "有未保存修改"
                  : saved
                    ? `已保存 · 版本 ${saved.revision}`
                    : "尚未保存"}
            </span>
          </div>
          <fieldset disabled={busy} className="profile-fields">
            <div className="form-grid">
              <label>
                预算上限（元）
                <div className="money-input">
                  <span aria-hidden="true">¥</span>
                  <input
                    name="budget"
                    type="number"
                    inputMode="decimal"
                    min="0.01"
                    max="10000000"
                    step="0.01"
                    required
                    placeholder="填写你不想超过的金额"
                    value={form.budget}
                    onChange={(e) => change({ budget: e.target.value })}
                  />
                </div>
              </label>
              <label>
                不考虑的品牌
                <input
                  className="text-input"
                  maxLength={1600}
                  placeholder="可选，多个品牌用逗号分隔"
                  value={form.exclusions}
                  onChange={(e) => change({ exclusions: e.target.value })}
                />
              </label>
            </div>
            <fieldset className="choice-fields">
              <legend>主要用途（可多选）</legend>
              <div className="check-grid">
                {Object.entries(workloadOptions).map(([key, label]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={form.workloads.includes(
                        key as ProfileInput["workloads"][number],
                      )}
                      onChange={(e) =>
                        change({
                          workloads: e.target.checked
                            ? [
                                ...form.workloads,
                                key as ProfileInput["workloads"][number],
                              ]
                            : form.workloads.filter((item) => item !== key),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="choice-fields">
              <legend>预算包含</legend>
              <div className="check-grid">
                {[
                  ...basicScope(form.mode),
                  "monitor",
                  "peripherals",
                  "os",
                  "assembly",
                  "shipping",
                ].map((key) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      disabled={basicScope(form.mode).includes(
                        key as ProfileInput["budget_scope"][number],
                      )}
                      checked={form.scope.includes(
                        key as ProfileInput["budget_scope"][number],
                      )}
                      onChange={(e) =>
                        change({
                          scope: e.target.checked
                            ? [
                                ...form.scope,
                                key as ProfileInput["budget_scope"][number],
                              ]
                            : form.scope.filter((item) => item !== key),
                        })
                      }
                    />
                    {scopeOptions[key as keyof typeof scopeOptions]}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="form-grid">
              {form.mode === "pc" && (
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={form.wifi}
                    onChange={(e) => change({ wifi: e.target.checked })}
                  />
                  需要无线网络
                </label>
              )}
              {form.mode === "laptop" && (
                <label>
                  重量上限（克，可选）
                  <input
                    className="text-input"
                    type="number"
                    min="100"
                    max="10000"
                    step="1"
                    value={form.weight}
                    onChange={(e) => change({ weight: e.target.value })}
                  />
                </label>
              )}
              {form.mode === "component" && (
                <label>
                  零件类别
                  <select
                    value={form.category}
                    onChange={(e) =>
                      change({
                        category: e.target.value as FormState["category"],
                      })
                    }
                  >
                    {Object.entries(categories).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="form-context">
                <span>地区与商品范围</span>
                <strong>中国大陆 · 全新零售 · 人民币</strong>
              </div>
            </div>
            <button
              className="primary-button"
              type="submit"
              disabled={needsReload}
            >
              {busy ? "正在处理…" : "保存需求"}
              <span aria-hidden="true">→</span>
            </button>
          </fieldset>
          <p className="draft-note">
            匿名保存至会话创建后 24 小时，同一浏览器可恢复。尚未开放商品推荐。
          </p>
          {session && (
            <p className="draft-note">
              本次有效至 {new Date(session.expires_at).toLocaleString("zh-CN")}
            </p>
          )}
          {notice && (
            <div role="status" className="summary">
              {notice}
            </div>
          )}
          {error && (
            <div role="alert" className="profile-error">
              <p>{error}</p>
              <button
                type="button"
                className="retry-button"
                disabled={busy}
                onClick={reload}
              >
                读取最新需求
              </button>
              {needsReload && (
                <p>读取会替换本页未保存修改，不会自动覆盖服务端版本。</p>
              )}
            </div>
          )}
          <div className="session-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => clear("reset")}
            >
              开始新需求
            </button>
            {session && (
              <button
                type="button"
                disabled={busy}
                onClick={() => clear("delete")}
              >
                删除已保存需求
              </button>
            )}
          </div>
        </form>
        <aside className="data-status" aria-label="数据准备状态">
          <span className="status-badge">
            <span />
            {status === "error" ? "连接待恢复" : "数据准备中"}
          </span>
          <div className="empty-symbol" aria-hidden="true">
            <span>≡</span>
            <i />
          </div>
          <div role="status" aria-live="polite">
            <h3>
              {status === "loading"
                ? "正在检查数据状态"
                : status === "error"
                  ? "暂时无法连接服务"
                  : "先核实，再推荐"}
            </h3>
            <p>
              {status === "error"
                ? "暂时无法确认服务状态。请保留未保存内容，连接恢复后重试。"
                : "商品规格与报价尚未准备好。现在不会展示未经核验的型号、价格或购买清单。"}
            </p>
          </div>
          {status === "error" ? (
            <button
              className="retry-button"
              onClick={() => setAttempt((value) => value + 1)}
            >
              重新连接
            </button>
          ) : (
            <div className="status-detail">
              <span>当前阶段</span>
              <strong>需求保存与会话隔离</strong>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
