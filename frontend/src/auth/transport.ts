import { ApiError } from "../api";

export type ApiResponse<T = unknown> = {
  data: T; status: number; requestId?: string; idempotencyReplayed: boolean;
};
const safeId = (value: unknown): string | undefined =>
  typeof value === "string" && /^[\w-]{1,80}$/.test(value) ? value : undefined;
export function apiPath(path: string): string {
  const url = new URL(path, "http://local.invalid");
  if (!path.startsWith("/api/v1/") || /[\\\r\n]/.test(path) ||
      url.origin !== "http://local.invalid" || !url.pathname.startsWith("/api/v1/") || url.hash) {
    throw new ApiError(0, "INVALID_API_PATH");
  }
  return path;
}
export async function decodeResponse(response: Response): Promise<ApiResponse> {
  const headerId = safeId(response.headers.get("X-Request-ID"));
  if (!response.ok) {
    let code = "HTTP_ERROR", requestId = headerId;
    try {
      const body = await response.json();
      const error = body && typeof body === "object" ? body.error : undefined;
      if (error && typeof error.code === "string" && /^[A-Z0-9_]{1,80}$/.test(error.code)) code = error.code;
      requestId = safeId(error?.request_id) ?? safeId(error?.trace_id) ?? headerId;
    } catch { /* Never expose upstream HTML, messages or credentials. */ }
    throw new ApiError(response.status, code, requestId);
  }
  try {
    return { data: await response.json(), status: response.status, requestId: headerId,
      idempotencyReplayed: response.headers.get("Idempotency-Replayed") === "true" };
  } catch { throw new ApiError(0, "INVALID_RESPONSE", headerId); }
}
export const aborted = () => new DOMException("Superseded or aborted request", "AbortError");
