import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App";
import fixture from "./voc-synthetic.json";
import { AuthManager } from "../auth/store";
import { mutations } from "../features/workspace/mutations";
import { parseVOC } from "../features/voc/contracts";
const original = fixture.proposal, team = original.team_ids[0], id = original.request_id;
const caps = ["P1_VOC_READ", "P1_VOC_GENERATE", "P1_VOC_REVIEW"];
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { "X-Request-ID": "restore-test-id" } });
const session = (capabilities = caps) => ({ userId: original.created_by, displayName: "합성 관리자", role: "ADMIN", active: true, permissions: ["OPERATIONS_READ"], capabilities, allowedTeamIds: [team], scopeKey: "restore-test" });
function proposal(status = "PENDING_REVIEW") {
  const p = structuredClone(original), terminal = ["APPROVED", "REJECTED"].includes(status);
  return { ...p, status, revision: terminal ? 2 : 1, proposal: ["FAILED", "INSUFFICIENT_DATA"].includes(status) ? null : p.proposal, reason_code: status === "FAILED" ? "AI_TIMEOUT" : status === "INSUFFICIENT_DATA" ? "LOW_SAMPLE" : null, reviews: terminal ? [{ review_id: "00000000-0000-0000-0000-000000000099", reviewed_by: p.created_by, decision: status, reason: "실험 후보 검토", created_at: p.created_at }] : [] };
}
type Handler = (url: URL, init?: RequestInit) => Promise<Response | undefined>;
function mount(path = "/p1/voc", handler?: Handler, capabilities = caps) {
  const transport = vi.fn<typeof fetch>(async (input, init) => {
    const u = new URL(String(input), "http://local");
    if (u.pathname.endsWith("/auth/login")) return json({ access_token: "synthetic-ui-token", expires_in: 3600 });
    if (u.pathname.endsWith("/p1/session")) return json(session(capabilities));
    const custom = await handler?.(u, init); if (custom) return custom;
    if (u.pathname.includes("/analytics/voc/")) return json(u.pathname.endsWith("unavailable") ? { ...fixture.products, items: [] } : fixture.products);
    if (u.pathname.endsWith("/voc-proposals")) return json({ items: [], next_cursor: null });
    return json(proposal());
  });
  vi.stubGlobal("fetch", transport); render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("로그인 이름"), { target: { value: "admin" } }); fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "synthetic-password" } }); fireEvent.click(screen.getByRole("button", { name: "로그인" })); return transport;
}
const managers: AuthManager[] = [];
afterEach(() => { vi.unstubAllGlobals(); managers.forEach(a => a.dispose()); managers.length = 0; });
it.each(["PENDING_REVIEW", "APPROVED", "REJECTED", "INSUFFICIENT_DATA", "FAILED"])("validates actual %s contract", status => {
  const p = parseVOC(proposal(status), [team]); expect(p.status).toBe(status); expect(p.proposal === null).toBe(["INSUFFICIENT_DATA", "FAILED"].includes(status));
});
it("rejects foreign teams, inconsistent periods, invented ratios and unknown evidence", () => {
  expect(() => parseVOC(original, ["00000000-0000-0000-0000-000000000001"])).toThrow();
  const p = structuredClone(original); p.evidence.facts.rate.cohort_inquiry_ratio = 2; expect(() => parseVOC(p, [team])).toThrow();
  const q = structuredClone(original); q.evidence.facts.trend.windows.window_end = q.created_at; expect(() => parseVOC(q, [team])).toThrow();
});
it("uses only API-verified product options and sends JSON/key; insufficient is not AI success", async () => {
  const transport = mount("/p1/voc", async (_u, init) => init?.method === "POST" ? json(proposal("INSUFFICIENT_DATA"), 201) : undefined);
  fireEvent.change(await screen.findByLabelText("확인된 상품 UUID"), { target: { value: original.product_id } }); fireEvent.click(screen.getByRole("button", { name: "개선 제안 생성" }));
  await screen.findByText("INSUFFICIENT_DATA"); expect(screen.getByText("사유 코드: LOW_SAMPLE")).toBeInTheDocument();
  const write = transport.mock.calls.find(c => String(c[0]).endsWith("/voc-proposals") && c[1]?.method === "POST")!;
  expect(JSON.parse(write[1]!.body as string)).toEqual({ product_id: original.product_id, team_ids: [team] }); expect(new Headers(write[1]?.headers).get("Idempotency-Key")).toMatch(/^p1-/);
});
it("keeps original key/body across uncertain POST, session refresh and explicit retry", async () => {
  let attempts = 0;
  const transport = mount("/p1/voc", async (_u, init) => { if (init?.method === "POST") { if (!attempts++) throw new TypeError("synthetic lost response"); return json(original, 200); } });
  fireEvent.change(await screen.findByLabelText("확인된 상품 UUID"), { target: { value: original.product_id } }); fireEvent.click(screen.getByRole("button", { name: "개선 제안 생성" })); await screen.findByRole("button", { name: "동일 요청 재시도" });
  fireEvent.click(screen.getByRole("button", { name: "권한·팀 다시 확인" })); fireEvent.click(await screen.findByRole("button", { name: "동일 요청 재시도" })); await screen.findByRole("link", { name: "저장 결과 상세 보기" });
  const posts = transport.mock.calls.filter(c => String(c[0]).endsWith("/voc-proposals") && c[1]?.method === "POST"); expect(posts).toHaveLength(2); expect(posts[0][1]?.body).toBe(posts[1][1]?.body); expect(new Headers(posts[0][1]?.headers).get("Idempotency-Key")).toBe(new Headers(posts[1][1]?.headers).get("Idempotency-Key"));
});
it("displays server-provided ratios, dates and synthetic origins without filling missing dates", async () => {
  mount(`/p1/voc/${id}`); await screen.findByText("서버 N/S"); expect(screen.getByText("서버 N/S").parentElement).toHaveTextContent("4%"); expect(screen.getByText("게시 raw_rate").parentElement).toHaveTextContent("5%"); expect(screen.getByText("LOCAL_SYNTHETIC")).toBeInTheDocument(); expect(screen.queryByText("2026-10-28")).not.toBeInTheDocument(); expect(screen.getByText(/Fabric 연결은 UNVERIFIED/)).toBeInTheDocument();
});
it.each(["APPROVED", "REJECTED"])("reviews %s with current revision/reason and fetches latest detail", async decision => {
  let state = "PENDING_REVIEW"; const transport = mount(`/p1/voc/${id}`, async (_u, init) => { if (init?.method === "POST") state = decision; return json(proposal(state)); });
  fireEvent.change(await screen.findByLabelText("검토 결정"), { target: { value: decision } }); fireEvent.change(screen.getByLabelText("검토 사유"), { target: { value: "근거 확인" } }); fireEvent.click(screen.getByRole("button", { name: "검토 제출" })); await screen.findByText("검토 대기 상태에서만 검토할 수 있습니다.");
  const post = transport.mock.calls.find(c => String(c[0]).endsWith("/reviews"))!; expect(JSON.parse(post[1]!.body as string)).toEqual({ expected_revision: 1, decision, reason: "근거 확인" }); expect(transport.mock.calls.filter(c => String(c[0]).endsWith(`/${id}`))).toHaveLength(2);
});
it("re-GETs after 409 without auto retry", async () => {
  let reviewed = false; const transport = mount(`/p1/voc/${id}`, async (_u, init) => { if (init?.method === "POST") { reviewed = true; return json({ error: { code: "VOC_REVIEW_CONFLICT" } }, 409); } return json(proposal(reviewed ? "APPROVED" : "PENDING_REVIEW")); });
  fireEvent.change(await screen.findByLabelText("검토 사유"), { target: { value: "경합 검토" } }); fireEvent.click(screen.getByRole("button", { name: "검토 제출" })); await screen.findByText("검토 대기 상태에서만 검토할 수 있습니다."); expect(screen.getByText(/409 충돌/)).toBeInTheDocument(); expect(transport.mock.calls.filter(c => String(c[0]).endsWith("/reviews"))).toHaveLength(1);
});
it.each(["FAILED", "INSUFFICIENT_DATA"])("does not render proposal/review for %s", async status => { mount(`/p1/voc/${id}`, async () => json(proposal(status))); await screen.findByText(/생성된 제안이 없습니다/); expect(screen.queryByRole("form", { name: "VOC 검토" })).not.toBeInTheDocument(); });
it("denies direct URL without READ and hides REVIEW from read-only users", async () => { const transport = mount(`/p1/voc/${id}`, undefined, []); await screen.findByText("이 화면을 볼 권한이 없습니다"); expect(transport).toHaveBeenCalledTimes(2); });
it("distinguishes disabled from empty and clears protected screen on 401", async () => {
  const transport = mount("/p1/voc", async u => u.pathname.includes("voc-proposals") ? json({ error: { code: "VOC_DISABLED" } }, 503) : undefined); await screen.findByText("VOC 기능이 비활성화되어 있습니다"); expect(screen.queryByText(/정상 조회된 0건/)).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "개선 제안 생성" })).not.toBeInTheDocument();
  transport.mockImplementation(async () => json({ error: { code: "INVALID_CREDENTIALS" } }, 401)); fireEvent.click(screen.getByRole("button", { name: "이력 새로고침" })); await screen.findByRole("form", { name: "백엔드 로그인" });
});
it("uses opaque history cursors and does not invent totals", async () => {
  const transport = mount("/p1/voc", async u => u.pathname.endsWith("voc-proposals") ? json({ items: [original], next_cursor: u.searchParams.has("cursor") ? null : "cursor+/=" }) : undefined, ["P1_VOC_READ"]);
  const next = await screen.findByRole("button", { name: "다음 이력 페이지" }); await waitFor(() => expect(next).toBeEnabled()); fireEvent.click(next); await screen.findByText("2페이지"); await waitFor(() => expect(next).toBeDisabled()); expect(transport.mock.calls.some(c => new URL(String(c[0]), "http://local").searchParams.get("cursor") === "cursor+/=")).toBe(true);
});
it("drops late mutation results on logout", async () => {
  let release!: (r: Response) => void;
  const auth = new AuthManager(async input => String(input).endsWith("/auth/login") ? json({ access_token: "synthetic-unit-token", expires_in: 60 }) : String(input).endsWith("/p1/session") ? json(session()) : new Promise(resolve => { release = resolve; })); managers.push(auth); await auth.login("admin", "local-password"); const store = mutations(auth);
  const pending = store.start("test", { value: 1 }, [team], "P1_VOC_GENERATE", "P1_VOC_READ", async (body, key) => { await auth.request("/api/v1/admin/p1/voc-proposals", { method: "POST", body, idempotencyKey: key }); return { href: "/p1/voc" }; });
  auth.logout(); release(json(original)); await pending; expect(store.getSnapshot()).toEqual({});
});
