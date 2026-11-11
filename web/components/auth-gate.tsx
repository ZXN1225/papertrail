"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Workspace } from "@/components/workspace";
import type { AgentTurn } from "@/lib/api/papers";

type AuthState = "loading" | "signed_out" | "signed_in";
type ConversationSummary = { id: string; title: string; updated_at?: string };

export function AuthGate() {
  const [state, setState] = useState<AuthState>("loading");
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [initialHistory, setInitialHistory] = useState<AgentTurn[]>([]);
  const [conversationLoading, setConversationLoading] = useState(false);
  const selectionVersion = useRef(0);

  async function refresh() {
    const response = await fetch("/api/auth", { cache: "no-store" });
    if (!response.ok) {
      setState("signed_out");
      return;
    }
    const conversations = await fetch("/api/conversations", {
      cache: "no-store",
    });
    const list = conversations.ok
      ? ((await conversations.json()) as ConversationSummary[])
      : [];
    setConversations(list);
    if (list.length) {
      setConversationId(list[0].id);
      const messages = await fetch(
        `/api/conversations/${list[0].id}/messages`,
        { cache: "no-store" },
      );
      if (messages.ok) {
        const saved = (await messages.json()) as {
          role: "user" | "assistant";
          content: string;
        }[];
        setInitialHistory(
          saved.map(({ role, content }) => ({ role, content })),
        );
      }
    } else {
      const created = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "新对话" }),
      });
      if (created.ok) {
        const conversation = (await created.json()) as ConversationSummary;
        setConversationId(conversation.id);
        setConversations([conversation]);
      }
    }
    setState("signed_in");
  }

  async function selectConversation(id: string) {
    const version = ++selectionVersion.current;
    setConversationLoading(true);
    setConversationId(id);
    setInitialHistory([]);
    try {
      const response = await fetch(`/api/conversations/${id}/messages`, {
        cache: "no-store",
      });
      if (!response.ok) return;
      const saved = (await response.json()) as {
        role: "user" | "assistant";
        content: string;
      }[];
      if (version === selectionVersion.current)
        setInitialHistory(
          saved.map(({ role, content }) => ({ role, content })),
        );
    } catch {
      // The selection stays empty until the next successful reload.
    } finally {
      if (version === selectionVersion.current) setConversationLoading(false);
    }
  }

  async function renameConversation(
    id: string,
    title: string,
  ): Promise<boolean> {
    try {
      const response = await fetch(`/api/conversations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      if (!response.ok) return false;
      const updated = (await response.json()) as ConversationSummary;
      setConversations((current) => [
        updated,
        ...current.filter((conversation) => conversation.id !== id),
      ]);
      return true;
    } catch {
      return false;
    }
  }

  async function deleteConversation(id: string): Promise<boolean> {
    try {
      const response = await fetch(`/api/conversations/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) return false;
      const remaining = conversations.filter(
        (conversation) => conversation.id !== id,
      );
      setConversations(remaining);
      if (conversationId !== id) return true;
      const version = ++selectionVersion.current;
      setConversationId(null);
      setConversationLoading(false);
      setInitialHistory([]);
      if (remaining.length > 0) {
        await selectConversation(remaining[0].id);
        return true;
      }
      const created = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "新对话" }),
      }).catch(() => null);
      if (version !== selectionVersion.current) return true;
      if (!created?.ok) {
        setConversationId(null);
        return true;
      }
      const replacement = (await created
        .json()
        .catch(() => null)) as ConversationSummary | null;
      if (!replacement || version !== selectionVersion.current) return true;
      setConversationId(replacement.id);
      setConversations([replacement]);
      return true;
    } catch {
      return false;
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: register ? "register" : "login",
        username,
        password,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setError(
        data.detail === "username_unavailable"
          ? "该账号已被使用。"
          : "账号或密码无效，请检查后重试。",
      );
      return;
    }
    if (register) {
      const loginResponse = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "login", username, password }),
      });
      if (!loginResponse.ok) {
        setError("账号已创建，请登录。 ");
        setRegister(false);
        return;
      }
    }
    await refresh();
  }

  if (state === "loading")
    return <main className="auth-screen">正在检查登录状态…</main>;
  if (state === "signed_in")
    return (
      <Workspace
        conversationId={conversationId}
        conversationLoading={conversationLoading}
        conversations={conversations}
        initialHistory={initialHistory}
        onRenameConversation={renameConversation}
        onDeleteConversation={deleteConversation}
        onNewConversation={async () => {
          try {
            const response = await fetch("/api/conversations", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ title: "新对话" }),
            });
            if (!response.ok) return false;
            const created = (await response.json()) as ConversationSummary;
            ++selectionVersion.current;
            setConversationLoading(false);
            setConversationId(created.id);
            setConversations((current) => [created, ...current]);
            setInitialHistory([]);
            return true;
          } catch {
            return false;
          }
        }}
        onSelectConversation={selectConversation}
        onSignOut={async () => {
          ++selectionVersion.current;
          await fetch("/api/auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "logout" }),
          });
          setState("signed_out");
        }}
      />
    );
  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <p className="eyebrow">PAPERTRAIL</p>
        <h1>{register ? "创建研究空间" : "登录你的研究空间"}</h1>
        <label>
          账号
          <input
            autoComplete="username"
            minLength={3}
            maxLength={40}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>
        <label>
          密码
          <input
            autoComplete={register ? "new-password" : "current-password"}
            type="password"
            minLength={12}
            maxLength={256}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}
        <button type="submit">{register ? "注册账号" : "登录"}</button>
        <button
          className="auth-toggle"
          type="button"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register ? "已有账号？登录" : "创建新账号"}
        </button>
      </form>
    </main>
  );
}
