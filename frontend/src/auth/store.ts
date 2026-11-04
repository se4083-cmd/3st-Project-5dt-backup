import { ApiError } from "../api";
import { parseP1Session, type P1Session } from "./session";
import { aborted, apiPath, decodeResponse, type ApiResponse } from "./transport";

export type AuthState = {
  phase: "anonymous" | "authenticating" | "loading" | "ready" | "blocked";
  epoch: number; session: P1Session | null; error?: ApiError;
};

export class AuthManager {
  private token: string | null = null;
  private version = 0;
  private state: AuthState = { phase: "anonymous", epoch: 0, session: null };
  private listeners = new Set<() => void>();
  private controllers = new Set<AbortController>();
  private loginController?: AbortController;
  private expiry?: ReturnType<typeof setTimeout>;
  private refreshing = false;
  constructor(private readonly transport: typeof fetch = (...args) => fetch(...args)) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private emit(phase: AuthState["phase"], session: P1Session | null = null, error?: ApiError) {
    this.state = { phase, session, error, epoch: this.state.epoch + 1 };
    for (const listener of this.listeners) listener();
  }
  private cancel() {
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
  }
  logout = (expired = false) => {
    this.version++; this.token = null; this.refreshing = false;
    clearTimeout(this.expiry); this.loginController?.abort(); this.cancel();
    this.emit("anonymous", null, expired ? new ApiError(401, "SESSION_EXPIRED") : undefined);
  };
  dispose = () => this.logout();

  login = async (loginName: string, password: string) => {
    this.logout();
    const version = this.version;
    const controller = new AbortController(); this.loginController = controller;
    this.emit("authenticating");
    try {
      const raw = await this.transport("/api/v1/auth/login", { method: "POST", credentials: "omit", cache: "no-store", redirect: "error",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ login_name: loginName, password }), signal: controller.signal });
      const { data } = await decodeResponse(raw);
      if (version !== this.version || controller.signal.aborted) return;
      const v = data as Record<string, unknown>;
      if (!v || typeof v.access_token !== "string" || !v.access_token ||
          (v.token_type !== undefined && v.token_type !== "bearer") ||
          !Number.isSafeInteger(v.expires_in) || (v.expires_in as number) <= 0 || (v.expires_in as number) > 86400) {
        throw new ApiError(0, "INVALID_RESPONSE");
      }
      this.token = v.access_token;
      this.expiry = setTimeout(() => { if (version === this.version) this.logout(true); }, (v.expires_in as number) * 1000);
      await this.refresh();
    } catch (error) {
      if (version !== this.version || controller.signal.aborted) return;
      this.token = null; clearTimeout(this.expiry);
      this.emit("anonymous", null, error instanceof ApiError ? error : new ApiError(0, "NETWORK_ERROR"));
    } finally { if (this.loginController === controller) this.loginController = undefined; }
  };

  // Also usable by the existing P0 read adapters. Override credentials/headers
  // explicitly, and scope credentials to local /api/v1 URLs only.
  fetch: typeof fetch = async (input, init) => {
    if (typeof input !== "string") throw new ApiError(0, "INVALID_API_PATH");
    apiPath(input);
    if (!this.token) throw new ApiError(401, "AUTHENTICATION_REQUIRED");
    const version = this.version, epoch = this.state.epoch;
    const controller = new AbortController();
    const abort = () => controller.abort();
    const signal = init?.signal;
    if (signal?.aborted) throw aborted();
    signal?.addEventListener("abort", abort, { once: true });
    this.controllers.add(controller);
    const headers = new Headers(init?.headers); headers.set("Authorization", `Bearer ${this.token}`);
    try {
      const response = await this.transport(input, { ...init, headers, signal: controller.signal, credentials: "omit", cache: "no-store", redirect: "error" });
      if (controller.signal.aborted || version !== this.version || epoch !== this.state.epoch) throw aborted();
      if (response.status === 401) this.logout(true);
      return response;
    } catch (error) {
      if (controller.signal.aborted || version !== this.version || epoch !== this.state.epoch) throw aborted();
      throw error instanceof ApiError ? error : new ApiError(0, "NETWORK_ERROR");
    } finally {
      signal?.removeEventListener("abort", abort); this.controllers.delete(controller);
    }
  };
  request = async (path: string, options: { method?: "GET" | "POST"; body?: object; signal?: AbortSignal; idempotencyKey?: string } = {}): Promise<ApiResponse> => {
    const version = this.version, epoch = this.state.epoch;
    const method = options.method ?? "GET";
    const headers = new Headers({ Accept: "application/json" });
    if (method === "POST") {
      if (!options.idempotencyKey || !/^[A-Za-z0-9._:-]{8,128}$/.test(options.idempotencyKey)) throw new ApiError(422, "INVALID_IDEMPOTENCY_KEY");
      headers.set("Idempotency-Key", options.idempotencyKey);
      headers.set("Content-Type", "application/json");
    }
    const response = await this.fetch(path, { method, headers, signal: options.signal,
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}) });
    const result = await decodeResponse(response);
    if (version !== this.version || epoch !== this.state.epoch || options.signal?.aborted) throw aborted();
    return result;
  };
  refresh = async () => {
    if (!this.token || this.refreshing) return;
    this.refreshing = true; this.cancel(); this.emit("loading");
    const version = this.version, epoch = this.state.epoch;
    try {
      const result = await this.request("/api/v1/admin/p1/session");
      if (version !== this.version || epoch !== this.state.epoch) return;
      this.emit("ready", parseP1Session(result.data));
    } catch (error) {
      if (version !== this.version || epoch !== this.state.epoch) return;
      this.cancel(); this.emit("blocked", null, error instanceof ApiError ? error : new ApiError(0, "INVALID_RESPONSE"));
    } finally { if (version === this.version) this.refreshing = false; }
  };
}
