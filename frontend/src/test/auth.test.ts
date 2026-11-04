import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, errorText } from "../api";
import { AuthManager } from "../auth/store";
import { hasCapability, parseP1Session } from "../auth/session";
import { createP1Client } from "../features/p1/client";

const user = "00000000-0000-0000-0000-000000000001", team = "00000000-0000-0000-0000-000000000002";
export const session = (capabilities = ["P1_MONITOR_READ"]) => ({ userId: user, displayName: "관리자", role: "ADMIN", active: true, permissions: ["OPERATIONS_READ", "PRODUCT_READ"], allowedTeamIds: [team], scopeKey: "scope-a", capabilities });
const json = (data: unknown, status = 200, headers: Record<string,string> = {}) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...headers } });
const managers: AuthManager[] = [];
const manager = (transport: typeof fetch) => { const auth = new AuthManager(transport); managers.push(auth); return auth; };
afterEach(() => { managers.forEach(m => m.dispose()); managers.length = 0; vi.useRealTimers(); vi.restoreAllMocks(); });
function backend(extra?: (path: string, init?: RequestInit) => Promise<Response>) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const path = String(input);
    if (path.endsWith("/auth/login")) return json({ access_token: "memory-only-test-token", token_type: "bearer", expires_in: 60 });
    if (path.endsWith("/p1/session")) return json(session());
    return extra ? extra(path, init) : json({ ok: true });
  });
}

describe("P1 memory authentication", () => {
  it("logs in with JSON then loads Bearer SQL scopes/capabilities without browser storage", async () => {
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const transport = backend(); const auth = manager(transport);
    await auth.login("admin", "synthetic-password");
    expect(auth.getSnapshot().phase).toBe("ready");
    expect(auth.getSnapshot().session?.allowedTeamIds).toEqual([team]);
    expect(hasCapability(auth.getSnapshot().session, "P1_MONITOR_READ")).toBe(true);
    expect(storage).not.toHaveBeenCalled();
    expect(JSON.stringify(auth.getSnapshot())).not.toContain("memory-only-test-token");
    expect(JSON.parse(transport.mock.calls[0][1]!.body as string)).toEqual({ login_name: "admin", password: "synthetic-password" });
    expect(new Headers(transport.mock.calls[1][1]!.headers).get("Authorization")).toBe("Bearer memory-only-test-token");
    expect(transport.mock.calls[1][1]?.credentials).toBe("omit");
    auth.logout();
    expect(auth.getSnapshot().session).toBeNull();
    await expect(auth.request("/api/v1/admin/p1/session")).rejects.toMatchObject({ status: 401 });
    expect(transport).toHaveBeenCalledTimes(2); // no imaginary server logout
  });
  it("expires in memory without a refresh-token endpoint", async () => {
    vi.useFakeTimers();
    const transport = backend(); const auth = manager(transport);
    await auth.login("admin", "password");
    vi.advanceTimersByTime(60_000);
    expect(auth.getSnapshot().phase).toBe("anonymous");
    expect(auth.getSnapshot().error?.code).toBe("SESSION_EXPIRED");
    expect(transport).toHaveBeenCalledTimes(2);
  });
  it("clears the token, session and in-flight data on current 401", async () => {
    const auth = manager(backend(async () => json({ error: { code: "INVALID_CREDENTIALS", request_id: "request-401" } }, 401)));
    await auth.login("admin", "password");
    await expect(auth.request("/api/v1/admin/p1/monitoring/summary")).rejects.toMatchObject({ status: 401, traceId: "request-401" });
    expect(auth.getSnapshot().phase).toBe("anonymous"); expect(auth.getSnapshot().session).toBeNull();
  });
  it.each([200, 401])("ignores old %s responses after a new login even if fetch ignores abort", async status => {
    let release!: (response: Response) => void;
    const transport = backend(() => new Promise(resolve => { release = resolve; }));
    const auth = manager(transport); await auth.login("one", "password");
    const old = auth.request("/api/v1/admin/p1/monitoring/summary").catch(e => e);
    await auth.login("two", "password");
    release(json({ private_old_result: true }, status));
    expect((await old).name).toBe("AbortError");
    expect(auth.getSnapshot().phase).toBe("ready");
  });
  it("clears old scopes immediately on refresh and accepts current capability revocation", async () => {
    let release!: (response: Response) => void, count = 0;
    const transport = backend();
    const fake = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith("/p1/session") && count++ > 0) return new Promise(resolve => { release = resolve; });
      return transport(url, init);
    });
    const auth = manager(fake); await auth.login("admin", "password");
    const oldEpoch = auth.getSnapshot().epoch;
    const refresh = auth.refresh();
    expect(auth.getSnapshot().phase).toBe("loading"); expect(auth.getSnapshot().session).toBeNull();
    release(json({ ...session([]), allowedTeamIds: ["00000000-0000-0000-0000-000000000003"], scopeKey: "scope-b" }));
    await refresh;
    expect(auth.getSnapshot().epoch).toBeGreaterThan(oldEpoch);
    expect(hasCapability(auth.getSnapshot().session, "P1_MONITOR_READ")).toBe(false);
    expect(auth.getSnapshot().session?.scopeKey).toBe("scope-b");
  });
  it.each([403, 503])("removes previous data when session returns %s without inventing grants", async status => {
    let revoked = false;
    const good = backend();
    const auth = manager(async (input, init) => revoked && String(input).endsWith("/p1/session") ? json({ error: { code: status === 503 ? "P1_DISABLED" : "P1_TEAM_SCOPE_DENIED" } }, status) : good(input, init));
    await auth.login("admin", "password"); revoked = true; await auth.refresh();
    expect(auth.getSnapshot().phase).toBe("blocked"); expect(auth.getSnapshot().session).toBeNull();
    expect(auth.getSnapshot().error?.status).toBe(status);
  });
  it("rejects malformed session roles/scopes and never infers capabilities from ADMIN", () => {
    expect(hasCapability(parseP1Session(session([])), "P1_POLICY_REVIEW")).toBe(false);
    for (const invalid of [{ role: "AGENT" }, { active: false }, { allowedTeamIds: [] }, { allowedTeamIds: ["DELIVERY"] }, { capabilities: [9] }, { capabilities: undefined }]) {
      expect(() => parseP1Session({ ...session(), ...invalid })).toThrow(ApiError);
    }
    expect(parseP1Session(session(["P1_POLICY_READ"])).permissions).not.toContain("INQUIRY_READ");
  });
});

describe("P1 transport boundary", () => {
  it("sends JSON, Bearer, AbortSignal and a caller-stable idempotency key; retains response metadata", async () => {
    const transport = backend(async () => json({ request_id: "request-data" }, 201, { "X-Request-ID": "request-header", "Idempotency-Replayed": "true" }));
    const auth = manager(transport); await auth.login("admin", "password");
    const client = createP1Client(auth); const signal = new AbortController().signal;
    const result = await client.post("/api/v1/admin/p1/voc-proposals", { product_id: user, team_ids: [team] }, "same-action-001", signal);
    const init = transport.mock.calls.at(-1)![1]!; const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer memory-only-test-token");
    expect(headers.get("Idempotency-Key")).toBe("same-action-001"); expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.signal).toBeInstanceOf(AbortSignal); expect(init.cache).toBe("no-store"); expect(init.redirect).toBe("error");
    expect(result).toMatchObject({ status: 201, requestId: "request-header", idempotencyReplayed: true });
    expect(JSON.parse(init.body as string)).toEqual({ product_id: user, team_ids: [team] });
    await expect(client.post("/api/v1/admin/p1/voc-proposals", {}, "bad")).rejects.toMatchObject({ code: "INVALID_IDEMPOTENCY_KEY" });
  });
  it("propagates abort and refuses late protected results", async () => {
    let release!: (r: Response) => void;
    const auth = manager(backend(() => new Promise(resolve => { release = resolve; })));
    await auth.login("admin", "password"); const controller = new AbortController();
    const pending = auth.request("/api/v1/admin/p1/monitoring/summary", { signal: controller.signal }).catch(e => e);
    controller.abort(); release(json({ old: true }));
    expect((await pending).name).toBe("AbortError");
  });
  it("rejects external or normalized non-P1 paths before sending credentials", async () => {
    const transport = backend(); const auth = manager(transport); await auth.login("admin", "password"); const client = createP1Client(auth);
    for (const path of ["https://evil.invalid/api/v1/admin/p1/session", "/api/v1/admin/p1/../../auth/login", "/api/v1/admin/p1/../../../outside", "/api/v1/admin/p1/session#fragment"]) {
      expect(() => client.get(path)).toThrow(ApiError);
    }
    expect(transport).toHaveBeenCalledTimes(2);
  });
  it("keeps safe error/request IDs and distinguishes disabled features from network errors", async () => {
    const auth = manager(backend(async () => json({ error: { code: "VOC_DISABLED", request_id: "body-id", message: "PRIVATE" } }, 503, { "X-Request-ID": "header-id" })));
    await auth.login("admin", "password");
    const error = await auth.request("/api/v1/admin/p1/voc-proposals").catch(e => e);
    expect(error).toMatchObject({ code: "VOC_DISABLED", traceId: "body-id" });
    expect(errorText(error).title).toContain("비활성화"); expect(errorText(error).retry).toBe(false); expect(error.message).not.toContain("PRIVATE");
    expect(auth.getSnapshot().phase).toBe("ready");
  });
  it("uses X-Request-ID for non-JSON errors and fails closed on invalid successful JSON", async () => {
    let malformed = false;
    const auth = manager(backend(async () => new Response("<html>PRIVATE</html>", { status: malformed ? 200 : 502, headers: { "X-Request-ID": "proxy-error" } })));
    await auth.login("admin", "password");
    await expect(auth.request("/api/v1/admin/p1/session?probe=1")).rejects.toMatchObject({ status: 502, traceId: "proxy-error" });
    malformed = true;
    await expect(auth.request("/api/v1/admin/p1/session?probe=1")).rejects.toMatchObject({ code: "INVALID_RESPONSE", traceId: "proxy-error" });
  });
});


it("does not retain credentials for failed or malformed login responses", async () => {
  for (const response of [json({ error: { code: "INVALID_CREDENTIALS", message: "PRIVATE" } }, 401), json({ access_token: "", expires_in: -1 })]) {
    const transport = vi.fn<typeof fetch>(async () => response);
    const auth = manager(transport);
    await auth.login("admin", "password");
    expect(auth.getSnapshot().phase).toBe("anonymous");
    expect(auth.getSnapshot().session).toBeNull();
    expect(auth.getSnapshot().error?.message).not.toContain("PRIVATE");
    expect(transport).toHaveBeenCalledTimes(1);
  }
});

it("clears protected data when a session refresh itself returns 401", async () => {
  let expired = false;
  const good = backend();
  const auth = manager(async (path, init) => expired && String(path).endsWith("/p1/session") ? json({ error: { code: "INVALID_CREDENTIALS" } }, 401) : good(path, init));
  await auth.login("admin", "password");
  expired = true; await auth.refresh();
  expect(auth.getSnapshot().phase).toBe("anonymous");
  expect(auth.getSnapshot().session).toBeNull();
  expect(auth.getSnapshot().error?.code).toBe("SESSION_EXPIRED");
});
