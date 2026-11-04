/**
 * The browser talks only to this boundary. The local reference server owns state,
 * permissions, retrieval, approval and finalization. A production adapter must
 * replace demo headers with the team's authenticated session and DTO mapping.
 */
export type JsonObject = Record<string, any>;
export type DemoRole = "admin" | "agent" | "customer";

export class ApiError extends Error {
  constructor(message: string, public code: string, public status = 0) {
    super(message);
    this.name = "ApiError";
  }
}

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const demoCustomer = "DEMO-CUSTOMER-001";

export function requestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  }
  // An idempotency identifier, never a credential.
  return `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function requestJson(path: string, options: {
  role?: DemoRole;
  method?: "GET" | "POST";
  body?: JsonObject;
  signal?: AbortSignal;
} = {}): Promise<JsonObject> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  const forwardAbort = () => controller.abort();
  options.signal?.addEventListener("abort", forwardAbort, { once: true });
  if (options.signal?.aborted) controller.abort();
  try {
    const response = await fetch(apiBase + path, {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        "X-Demo-Role": options.role ?? "admin",
        "X-Demo-Customer": demoCustomer,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}),
      signal: controller.signal,
      cache: "no-store",
    });
    let data: JsonObject;
    try {
      data = await response.json();
    } catch {
      throw new ApiError("API 응답 형식을 확인하지 못했습니다. 서버 실행 상태를 확인해 주세요.", "INVALID_API_RESPONSE", response.status);
    }
    if (!response.ok) {
      throw new ApiError(data.error?.message ?? "요청을 처리하지 못했습니다.", data.error?.code ?? `HTTP_${response.status}`, response.status);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new ApiError("API 응답 형식이 올바르지 않습니다.", "INVALID_API_RESPONSE", response.status);
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    throw new ApiError(
      controller.signal.aborted
        ? "서버 응답을 기다리는 시간이 지났습니다. 처리 결과를 다시 확인해 주세요."
        : "로컬 API에 연결하지 못했습니다. 실행 터미널을 확인해 주세요.",
      controller.signal.aborted ? "REQUEST_TIMEOUT" : "NETWORK_UNAVAILABLE",
    );
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
}

export const operationsApi = {
  state: (signal?: AbortSignal) => requestJson("/api/v2/state", { signal }),
  customerTickets: (signal?: AbortSignal) => requestJson("/api/v2/customer", { role: "customer", signal }),
  customerTicket: (id: string, signal?: AbortSignal) => requestJson(`/api/v2/customer/${encodeURIComponent(id)}`, { role: "customer", signal }),
  orders: (signal?: AbortSignal) => requestJson("/api/v2/orders", { role: "customer", signal }),
  knowledge: (signal?: AbortSignal) => requestJson("/api/v2/rag/documents", { signal }),
  productOperations: (id: string, signal?: AbortSignal) => requestJson(`/api/v2/products/${encodeURIComponent(id)}/operations`, { signal }),
  act: (body: JsonObject, role: DemoRole = "admin") => requestJson("/api/v2/actions", { method: "POST", body, role }),
  rag: (body: JsonObject, role: DemoRole = "admin") => requestJson("/api/v2/rag/ask", { method: "POST", body, role }),
};

export const analyticsApi = {
  status: (signal?: AbortSignal) => requestJson("/api/status", { signal }),
  generate: (body: JsonObject, signal?: AbortSignal) => requestJson("/api/insights", { method: "POST", body, signal }),
};
