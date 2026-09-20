import type { components } from "./schema";

export type PlatformStatus = components["schemas"]["PlatformStatus"];

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
