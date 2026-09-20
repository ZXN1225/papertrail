import type { components } from "./schema";

export type PlatformStatus = components["schemas"]["PlatformStatus"];
export type ProfileInput = components["schemas"]["ProfileInput"];
export type ProfileSnapshot = components["schemas"]["ProfileSnapshot"];
export type SessionState = components["schemas"]["SessionResponse"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function sessionRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
  csrf?: string,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
    headers:
      method === "GET"
        ? {}
        : {
            "Content-Type": "application/json",
            ...(csrf ? { "X-CSRF-Token": csrf } : {}),
          },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      failure?.error?.message || "操作失败，请稍后重试。",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

// Decimal text conversion, not floating-point budget computation.
export function yuanToMinor(value: string): number {
  if (!/^\d+(\.\d{1,2})?$/.test(value))
    throw new Error("预算最多保留两位小数。");
  const [whole, fraction = ""] = value.split(".");
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(minor) || minor <= 0 || minor > 1000000000)
    throw new Error("预算超出可填写范围。");
  return minor;
}

export async function getPlatformStatus(
  signal: AbortSignal,
): Promise<PlatformStatus> {
  const response = await fetch("/api/v1/platform/status", {
    signal,
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Service unavailable");
  const value: PlatformStatus = await response.json();
  if (
    value.stage !== "foundation" ||
    value.data_status !== "not_initialized" ||
    value.recommendation_available !== false ||
    value.currency !== "CNY" ||
    value.market !== "CN"
  ) {
    throw new Error("Unexpected platform contract");
  }
  return value;
}
