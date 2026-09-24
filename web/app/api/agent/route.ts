import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  tooLargeResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const MAX_REQUEST_BYTES = 16_384;

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
    Object.keys(body).some((key) => key !== "question")
  ) {
    return invalidResponse("问题需为 1–1000 个字符。");
  }
  try {
    return await jsonResponse(
      await backendRequest("/api/v1/agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify({
          question: (body as { question: string }).question.trim(),
        }),
      }),
    );
  } catch {
    return unavailableResponse();
  }
}
