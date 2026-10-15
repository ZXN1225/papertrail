import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  tooLargeResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const MAX_REQUEST_BYTES = 32_768;

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    const reader = request.body?.getReader();
    if (!reader) return invalidResponse("请求内容不是有效 JSON。");
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > MAX_REQUEST_BYTES) {
        await reader.cancel();
        return tooLargeResponse();
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    return invalidResponse("请求内容不是有效 JSON。");
  }
  if (
    !body ||
    typeof body !== "object" ||
    typeof (body as { question?: unknown }).question !== "string" ||
    !(body as { question: string }).question.trim() ||
    (body as { question: string }).question.length > 1_000 ||
    Object.keys(body).some(
      (key) => key !== "question" && key !== "run_id" && key !== "history",
    ) ||
    !isAgentHistory((body as { history?: unknown }).history) ||
    ((body as { run_id?: unknown }).run_id !== undefined &&
      (typeof (body as { run_id: unknown }).run_id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
          (body as { run_id: string }).run_id,
        )))
  ) {
    return invalidResponse("问题或历史上下文格式不符合限制。");
  }
  try {
    return await jsonResponse(
      await backendRequest("/api/v1/agent/ask", {
        method: "POST",
        signal: request.signal,
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify({
          question: (body as { question: string }).question.trim(),
          history: (body as { history?: AgentTurn[] }).history ?? [],
          ...((body as { run_id?: string }).run_id
            ? { run_id: (body as { run_id: string }).run_id }
            : {}),
        }),
      }),
    );
  } catch {
    return unavailableResponse();
  }
}

type AgentTurn = { role: "user" | "assistant"; content: string };

function isAgentHistory(value: unknown): value is AgentTurn[] {
  if (value === undefined) return true;
  if (!Array.isArray(value) || value.length > 8 || value.length % 2 !== 0) {
    return false;
  }
  let totalCharacters = 0;
  for (const [index, turn] of value.entries()) {
    if (
      !turn ||
      typeof turn !== "object" ||
      Object.keys(turn).some((key) => key !== "role" && key !== "content") ||
      typeof (turn as { role?: unknown }).role !== "string" ||
      typeof (turn as { content?: unknown }).content !== "string"
    ) {
      return false;
    }
    const typedTurn = turn as { role: string; content: string };
    if (
      typedTurn.role !== (index % 2 === 0 ? "user" : "assistant") ||
      !typedTurn.content.trim() ||
      typedTurn.content.length > 4_000
    ) {
      return false;
    }
    totalCharacters += typedTurn.content.length;
  }
  return totalCharacters <= 8_000;
}
