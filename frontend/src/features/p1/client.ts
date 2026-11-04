import { ApiError } from "../../api";
import { apiPath } from "../../auth/transport";
import type { AuthManager } from "../../auth/store";

export function createP1Client(auth: AuthManager) {
  const path = (value: string) => {
    apiPath(value);
    if (!value.startsWith("/api/v1/admin/p1/") || !new URL(value, "http://local.invalid").pathname.startsWith("/api/v1/admin/p1/")) throw new ApiError(0, "INVALID_API_PATH");
    return value;
  };
  return {
    get: (url: string, signal?: AbortSignal) => auth.request(path(url), { signal }),
    post: (url: string, body: object, idempotencyKey: string, signal?: AbortSignal) =>
      auth.request(path(url), { method: "POST", body, idempotencyKey, signal }),
  };
}
