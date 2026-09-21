"use client";

import { useState } from "react";

import {
  ApiError,
  sessionRequest,
  type AgentEvent,
  type AgentRun,
  type AgentSession,
  type ProfileSnapshot,
  type SessionState,
} from "@/lib/api/client";

type Props = {
  profile: ProfileSnapshot | null;
  session: SessionState | null;
};

const messageForMode = {
  pc: "请根据已保存的台式机需求核对可用方案。",
  laptop: "请根据已保存的笔记本需求核对可用方案。",
  component: "请根据已保存的零件需求核对可用方案。",
};

function eventSummary(events: AgentEvent[]) {
  return events.map((event) => event.type.replace(".", " · ")).join(" → ");
}

export function AgentPanel({ profile, session }: Props) {
  const [conversation, setConversation] = useState<AgentSession | null>(null);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!profile || !session) {
    return (
      <section className="agent-panel agent-unavailable" aria-label="需求核对">
        <h3>先保存需求，再开始核对</h3>
        <p>系统会以已保存的版本运行，避免未保存的填写内容被当作结论依据。</p>
      </section>
    );
  }
  const savedProfile = profile;
  const activeSession = session;

  async function readEvents(runId: string) {
    const response = await fetch(`/api/v1/agent/runs/${runId}/events`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error("无法读取运行事件。");
    const text = await response.text();
    const parsed: AgentEvent[] = [];
    for (const block of text.split("\n\n")) {
      const line = block
        .split("\n")
        .find((value) => value.startsWith("data: "));
      if (!line) continue;
      try {
        parsed.push(JSON.parse(line.slice(6)) as AgentEvent);
      } catch {
        // A malformed replay item must not become a user-facing result.
      }
    }
    setEvents(parsed);
  }

  async function start() {
    setBusy(true);
    setError("");
    setEvents([]);
    try {
      let activeConversation = conversation;
      if (!activeConversation) {
        activeConversation = await sessionRequest<AgentSession>(
          "agent/sessions",
          "POST",
          {},
          activeSession.csrf_token,
        );
        setConversation(activeConversation);
      }
      const next = await sessionRequest<AgentRun>(
        `agent/sessions/${activeConversation.id}/runs`,
        "POST",
        {
          profile_id: savedProfile.id,
          profile_revision: savedProfile.revision,
          message: messageForMode[savedProfile.profile.mode],
          expected_revision: activeConversation.revision,
          client_request_id: crypto.randomUUID(),
        },
        activeSession.csrf_token,
      );
      setRun(next);
      setConversation({ ...activeConversation, revision: next.revision });
      await readEvents(next.id);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "核对运行未能确认，请稍后重新开始。",
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const next = await sessionRequest<AgentRun>(
        `agent/runs/${run.id}/cancel`,
        "POST",
        {},
        activeSession.csrf_token,
      );
      setRun(next);
      await readEvents(next.id);
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "取消状态未能确认。",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="agent-panel" aria-labelledby="agent-title">
      <div className="agent-heading">
        <div>
          <span className="section-kicker">下一步 · 受控核对</span>
          <h3 id="agent-title">根据保存的需求核对</h3>
        </div>
        <span className="agent-version">需求版本 {savedProfile.revision}</span>
      </div>
      <p>
        只使用已保存需求和可核验工具结果。商品、价格或兼容性资料缺失时，会明确说明，不会补写结论。
      </p>
      <div className="agent-actions">
        <button
          className="primary-button"
          type="button"
          disabled={busy}
          onClick={start}
        >
          {busy ? "正在核对…" : "开始核对"}
          <span aria-hidden="true">→</span>
        </button>
        {run && ["queued", "running"].includes(run.status) && (
          <button
            className="secondary-button"
            type="button"
            disabled={busy}
            onClick={cancel}
          >
            取消本次核对
          </button>
        )}
      </div>
      {error && (
        <p className="profile-error" role="alert">
          {error}
        </p>
      )}
      {run && (
        <div className="agent-result" role="status">
          <span className="status-badge">运行状态：{run.status}</span>
          <h4>{run.answer?.summary || "正在等待经过校验的结果。"}</h4>
          {run.answer?.warnings.map((warning) => (
            <p key={warning}>提示：{warning}</p>
          ))}
          {run.answer && run.answer.candidates.length === 0 && (
            <p>目前没有可展示的已验证候选。请在资料发布后重新核对。</p>
          )}
          {events.length > 0 && <small>运行记录：{eventSummary(events)}</small>}
        </div>
      )}
    </section>
  );
}
