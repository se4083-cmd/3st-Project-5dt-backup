import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App";
import fixture from "./policy-synthetic.json";
import { contentError, prepare, registerError } from "../features/policy/input";
import { parseComparison, parsePolicy, parseVersions } from "../features/policy/contracts";
const p = fixture.policy, c = fixture.comparison, pid = p.policy_id, cid = c.comparison_id, team = p.team_ids[0], caps = ["P1_POLICY_READ", "P1_POLICY_WRITE", "P1_POLICY_REVIEW"];
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { "X-Request-ID": "policy-test-id" } });
const session = (capabilities = caps) => ({ userId: p.created_by, displayName: "합성 정책 관리자", role: "ADMIN", active: true, permissions: ["OPERATIONS_READ"], capabilities, allowedTeamIds: [team], scopeKey: "policy-restore" });
const content = { title: "배송 안내", body: "첫 줄\n기존 절차\n", source_document_id: null };
const registerBody = { ...content, policy_key: "DELIVERY", team_ids: [team] };
function version(n: number) { const v = structuredClone(p.versions.find(v => v.version_no === n) ?? p.versions[0]); return { ...v, version_no: n, version_id: n <= 2 ? v.version_id : `00000000-0000-0000-0000-${String(n).padStart(12, "0")}` }; }
function policy(latest = 2) { return { ...structuredClone(p), latest_version: latest, versions: Array.from({ length: Math.min(latest, 100) }, (_, i) => version(latest - i)), versions_truncated: latest > 100 }; }
function comparison(state = "PENDING_REVIEW", recorded = true) {
  const r = structuredClone(c), terminal = state !== "PENDING_REVIEW";
  if (!recorded) { r.impact.source_validation = "UNCONFIRMED"; r.impact.scanned_count = 0; for (const domain of [r.impact.faq, r.impact.auto_replies, r.impact.automation_rules]) { domain.links = []; domain.observed_reference_count = 0; domain.status = "UNCONFIRMED"; } }
  return { ...r, status: state, candidate_status: state, reviewable: !terminal, revision: terminal ? 2 : 1, reviews: terminal ? [{ review_id: "00000000-0000-0000-0000-000000000088", comparison_id: cid, version_id: r.to_version_id, reviewed_by: p.created_by, decision: state, reason: "미확인 범위 검토", created_at: r.created_at }] : [] };
}
type Handler = (url: URL, init?: RequestInit) => Promise<Response | undefined>;
function mount(path = "/p1/policies", handler?: Handler, capabilities = caps) {
  const transport = vi.fn<typeof fetch>(async (input, init) => {
    const u = new URL(String(input), "http://local");
    if (u.pathname.endsWith("/auth/login")) return json({ access_token: "synthetic-policy-token", expires_in: 3600 });
    if (u.pathname.endsWith("/p1/session")) return json(session(capabilities));
    const custom = await handler?.(u, init); if (custom) return custom;
    if (u.pathname.endsWith("/policies")) return json({ items: [], next_cursor: null });
    if (u.pathname.endsWith("/versions")) return json({ items: [version(2), version(1)], next_before_version: null });
    if (u.pathname.endsWith("/comparisons")) return json({ items: [], next_cursor: null });
    if (u.pathname.includes("/policy-comparisons/")) return json(comparison());
    return json(policy());
  });
  vi.stubGlobal("fetch", transport); render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("로그인 이름"), { target: { value: "admin" } }); fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "local-policy-password" } }); fireEvent.click(screen.getByRole("button", { name: "로그인" })); return transport;
}
afterEach(() => vi.unstubAllGlobals());
async function fillRegister() { fireEvent.change(await screen.findByLabelText("정책 key"), { target: { value: "DELIVERY" } }); fireEvent.change(screen.getByLabelText("제목"), { target: { value: content.title } }); fireEvent.change(screen.getByLabelText("정책 본문"), { target: { value: content.body } }); }
it("applies actual nonblank, NUL, Unicode character/line count, UUID and key rules", () => {
  expect(prepare({ ...content, body: " a\r\nb\r" }).body).toBe(" a\nb\n");
  expect(contentError({ ...content, body: "a\n".repeat(500) })).toBeNull(); expect(contentError({ ...content, body: "a\n".repeat(501) })).not.toBeNull();
  for (const body of ["   ", "a\0b", "x".repeat(20001)]) expect(contentError({ ...content, body })).not.toBeNull();
  expect(contentError({ ...content, title: "x".repeat(201) })).not.toBeNull(); expect(contentError({ ...content, source_document_id: "invented" })).not.toBeNull();
  expect(registerError({ ...registerBody, policy_key: "9bad" })).not.toBeNull(); expect(registerError({ ...registerBody, team_ids: [team, team] })).not.toBeNull();
});
it("checks policy ownership, latest version order and numeric exclusive page boundaries", () => {
  expect(parsePolicy(policy(101), [team]).versions_truncated).toBe(true); expect(() => parsePolicy(policy(), ["00000000-0000-0000-0000-000000000001"])).toThrow();
  expect(parseVersions({ items: [version(3), version(2)], next_before_version: 2 }, pid, null, 2).next_before_version).toBe(2);
  expect(() => parseVersions({ items: [version(2)], next_before_version: null }, pid, 2)).toThrow(); expect(() => parseVersions({ items: [version(2)], next_before_version: "2" }, pid, null)).toThrow();
});
it("checks end-exclusive diff lengths, null actual effects and activation boundary", () => {
  expect(parseComparison(c).impact.automation_rules.links[0].relation).toBe("RULE_CO_USED_WITH_POLICY_CITATION");
  const d = structuredClone(c); d.diff.changes[0].old_end++; expect(() => parseComparison(d)).toThrow();
  expect(() => parseComparison({ ...c, activation: "SUPPORTED" })).toThrow();
  expect(() => parseComparison({ ...c, impact: { ...c.impact, faq: { ...c.impact.faq, actual_affected_count: 0 } } })).toThrow();
  expect(() => parseComparison({ ...c, impact: { ...c.impact, rag_index: "VERIFIED" } })).toThrow();
});
it("registers the required fields only and does not offer activation", async () => {
  const transport = mount("/p1/policies", async (_u, init) => init?.method === "POST" ? json({ ...policy(1), policy_key: "DELIVERY" }, 201) : undefined);
  await fillRegister(); fireEvent.click(screen.getByRole("button", { name: "정책 등록" })); await screen.findByRole("link", { name: "저장 결과 상세 보기" });
  const post = transport.mock.calls.find(a => a[1]?.method === "POST" && String(a[0]).endsWith("/policies"))!; expect(JSON.parse(post[1]!.body as string)).toEqual(registerBody); expect(new Headers(post[1]?.headers).get("Idempotency-Key")).toMatch(/^p1-/); expect(screen.queryByRole("button", { name: /운영 적용|활성화/ })).not.toBeInTheDocument();
});
it("keeps original registration body/key on lost-response retry through session revalidation", async () => {
  let count = 0; const transport = mount("/p1/policies", async (_u, init) => { if (init?.method === "POST") { if (!count++) throw new TypeError("mock lost reply"); return json({ ...policy(1), policy_key: "DELIVERY" }, 200); } });
  await fillRegister(); fireEvent.click(screen.getByRole("button", { name: "정책 등록" })); await screen.findByRole("button", { name: "동일 요청 재시도" }); fireEvent.click(screen.getByRole("button", { name: "권한·팀 다시 확인" })); fireEvent.click(await screen.findByRole("button", { name: "동일 요청 재시도" })); await screen.findByRole("link", { name: "저장 결과 상세 보기" });
  const posts = transport.mock.calls.filter(a => a[1]?.method === "POST" && String(a[0]).endsWith("/policies")); expect(posts).toHaveLength(2); expect(posts[0][1]?.body).toBe(posts[1][1]?.body); expect(new Headers(posts[0][1]?.headers).get("Idempotency-Key")).toBe(new Headers(posts[1][1]?.headers).get("Idempotency-Key"));
});
it("blocks invalid content before POST", async () => { const t = mount(); await fillRegister(); fireEvent.change(screen.getByLabelText("정책 본문"), { target: { value: "a\n".repeat(501) } }); expect(screen.getByRole("button", { name: "정책 등록" })).toBeDisabled(); expect(t.mock.calls.some(a => a[1]?.method === "POST" && String(a[0]).endsWith("/policies"))).toBe(false); });
it("paginates by before_version and retains cross-page selection", async () => {
  const t = mount(`/p1/policies/${pid}`, async u => u.pathname.endsWith("/versions") ? json(u.searchParams.has("before_version") ? { items: [version(1)], next_before_version: null } : { items: Array.from({ length: 20 }, (_, i) => version(21 - i)), next_before_version: 2 }) : u.pathname.endsWith(`/${pid}`) ? json(policy(21)) : undefined);
  fireEvent.click(await screen.findByRole("button", { name: "v21 대상 선택" })); fireEvent.click(screen.getByRole("button", { name: "다음 버전 페이지" })); fireEvent.click(await screen.findByRole("button", { name: "v1 기준 선택" })); expect(screen.getByRole("button", { name: "비교 생성" })).toBeEnabled(); expect(t.mock.calls.some(a => String(a[0]).includes("before_version=2"))).toBe(true); fireEvent.click(screen.getByRole("button", { name: "이전 버전 페이지" })); await screen.findByRole("button", { name: "v21 대상 선택" }); expect(screen.getByText(`기준: v1 · ${version(1).version_id}`)).toBeInTheDocument();
});
it("appends using current head and explicit null source", async () => {
  let latest = 2; const t = mount(`/p1/policies/${pid}`, async (u, init) => { if (init?.method === "POST") { latest = 3; return json(version(3), 201); } if (u.pathname.endsWith(`/${pid}`)) return json(policy(latest)); });
  fireEvent.change(await screen.findByLabelText("정책 본문"), { target: { value: "새 절차\n" } }); fireEvent.click(screen.getByRole("button", { name: "새 버전 등록" })); await screen.findByText("최신 버전: 3"); const post = t.mock.calls.find(a => a[1]?.method === "POST" && String(a[0]).endsWith("/versions"))!; expect(JSON.parse(post[1]!.body as string)).toMatchObject({ expected_previous_version: 2, body: "새 절차\n", source_document_id: null });
});
it("gets the new head after append conflict and requires explicit new intent", async () => {
  let latest = 2; const t = mount(`/p1/policies/${pid}`, async (u, init) => { if (init?.method === "POST") { latest = 3; return json({ error: { code: "POLICY_VERSION_CONFLICT" } }, 409); } if (u.pathname.endsWith(`/${pid}`)) return json(policy(latest)); });
  fireEvent.click(await screen.findByRole("button", { name: "새 버전 등록" })); await screen.findByText("최신 버전: 3"); fireEvent.click(await screen.findByRole("button", { name: "최신 상태로 다시 작성" })); await screen.findByText("기준 최신 버전: 3"); expect(t.mock.calls.filter(a => a[1]?.method === "POST" && String(a[0]).endsWith("/versions"))).toHaveLength(1);
});
it("sends actual selected IDs and prevents reverse version pairs", async () => {
  const t = mount(`/p1/policies/${pid}`, async (_u, init) => init?.method === "POST" ? json(c, 201) : undefined);
  fireEvent.click(await screen.findByRole("button", { name: "v2 기준 선택" })); fireEvent.click(screen.getByRole("button", { name: "v1 대상 선택" })); expect(screen.getByRole("button", { name: "비교 생성" })).toBeDisabled(); fireEvent.click(screen.getByRole("button", { name: "v1 기준 선택" })); fireEvent.click(screen.getByRole("button", { name: "v2 대상 선택" })); fireEvent.click(screen.getByRole("button", { name: "비교 생성" })); await screen.findByRole("link", { name: "저장 결과 상세 보기" });
  const post = t.mock.calls.find(a => a[1]?.method === "POST" && String(a[0]).endsWith("/comparisons"))!; expect(JSON.parse(post[1]!.body as string)).toEqual({ from_version_id: version(1).version_id, to_version_id: version(2).version_id });
});
it("retains and displays the original comparison pair/key after uncertain POST and session remount", async () => {
  let attempts = 0; const t = mount(`/p1/policies/${pid}`, async (_u, init) => { if (init?.method === "POST") { if (!attempts++) throw new TypeError("synthetic lost comparison reply"); return json(c, 200); } });
  fireEvent.click(await screen.findByRole("button", { name: "v1 기준 선택" })); fireEvent.click(screen.getByRole("button", { name: "v2 대상 선택" })); fireEvent.click(screen.getByRole("button", { name: "비교 생성" })); await screen.findByRole("button", { name: "동일 요청 재시도" }); fireEvent.click(screen.getByRole("button", { name: "권한·팀 다시 확인" }));
  const retry = await screen.findByRole("button", { name: "동일 요청 재시도" }); expect(screen.getByText(`기준: ${version(1).version_id}`)).toBeInTheDocument(); expect(screen.getByText(`대상: ${version(2).version_id}`)).toBeInTheDocument(); fireEvent.click(retry); await screen.findByRole("link", { name: "저장 결과 상세 보기" });
  const posts = t.mock.calls.filter(a => a[1]?.method === "POST" && String(a[0]).endsWith("/comparisons")); expect(posts).toHaveLength(2); expect(posts[0][1]?.body).toBe(posts[1][1]?.body); expect(new Headers(posts[0][1]?.headers).get("Idempotency-Key")).toBe(new Headers(posts[1][1]?.headers).get("Idempotency-Key"));
});
it("renders a 0-based insertion without a phantom old line", async () => {
  const r = comparison(); r.diff.changes = [{ operation: "insert", old_start: 0, old_end: 0, new_start: 0, new_end: 1, before: [], after: ["추가\n"] }]; mount(`/p1/policy-comparisons/${cid}`, async u => u.pathname.includes("/policy-comparisons/") ? json(r) : undefined); await screen.findByRole("region", { name: "이전 범위 [0, 0)" }); expect(screen.getByText("빈 구간")).toBeInTheDocument(); expect(screen.getByLabelText("이후 줄 0")).toBeInTheDocument(); expect(screen.queryByLabelText("이전 줄 0")).not.toBeInTheDocument();
});
it.each([true, false])("keeps historical records and future impact distinct (recorded=%s)", async recorded => {
  mount(`/p1/policy-comparisons/${cid}`, async u => u.pathname.includes("/policy-comparisons/") ? json(comparison("PENDING_REVIEW", recorded)) : undefined); await screen.findByRole("region", { name: "정책 영향 분석" }); expect(screen.getAllByText(recorded ? "과거 연결 기록 확인 · RECORDED_LINKS" : "영향 미확인 · UNCONFIRMED")).toHaveLength(3); expect(screen.getByText("RAG 인덱스: UNCONFIRMED")).toBeInTheDocument(); expect(screen.queryByText("실제 영향 건수: 0건")).not.toBeInTheDocument(); expect(screen.getByText("운영 활성화 미지원 · activation=NOT_SUPPORTED")).toBeInTheDocument();
});
it.each(["APPROVED", "REJECTED"])("reviews %s with revision/reason and refreshes parent/detail", async decision => {
  let state = "PENDING_REVIEW"; const t = mount(`/p1/policy-comparisons/${cid}`, async (u, init) => { if (init?.method === "POST") { state = decision; return json(comparison(state)); } if (u.pathname.includes("/policy-comparisons/")) return json(comparison(state)); });
  fireEvent.change(await screen.findByLabelText("검토 결정"), { target: { value: decision } }); fireEvent.change(screen.getByLabelText("검토 사유"), { target: { value: "미확인 영향 범위 검토" } }); fireEvent.click(screen.getByRole("button", { name: "검토 제출" })); await screen.findByText(/현재 검토할 수 없습니다/);
  const post = t.mock.calls.find(a => String(a[0]).endsWith("/reviews"))!; expect(JSON.parse(post[1]!.body as string)).toEqual({ expected_revision: 1, decision, reason: "미확인 영향 범위 검토" }); expect(t.mock.calls.filter(a => String(a[0]).endsWith(`/${cid}`))).toHaveLength(2);
});
it("409 refreshes status and does not auto submit again", async () => {
  let state = "PENDING_REVIEW"; const t = mount(`/p1/policy-comparisons/${cid}`, async (u, init) => { if (init?.method === "POST") { state = "APPROVED"; return json({ error: { code: "POLICY_REVIEW_CONFLICT" } }, 409); } if (u.pathname.includes("/policy-comparisons/")) return json(comparison(state)); });
  fireEvent.change(await screen.findByLabelText("검토 사유"), { target: { value: "동시 검토" } }); fireEvent.click(screen.getByRole("button", { name: "검토 제출" })); await screen.findByText(/현재 검토할 수 없습니다/); expect(screen.getByText("비교 revision").parentElement).toHaveTextContent("2"); expect(screen.getByText(/409 충돌/)).toBeInTheDocument(); expect(t.mock.calls.filter(a => String(a[0]).endsWith("/reviews"))).toHaveLength(1);
});
it("does not review pending but superseded/already-reviewed candidates", async () => { mount(`/p1/policy-comparisons/${cid}`, async u => u.pathname.includes("/policy-comparisons/") ? json({ ...comparison(), reviewable: false, candidate_status: "APPROVED" }) : undefined); await screen.findByText(/현재 검토할 수 없습니다/); expect(screen.queryByRole("form", { name: "정책 검토" })).not.toBeInTheDocument(); });
it("guards direct URL with READ and renders no feature data without it", async () => { const t = mount(`/p1/policy-comparisons/${cid}`, undefined, []); await screen.findByText("이 화면을 볼 권한이 없습니다"); expect(t).toHaveBeenCalledTimes(2); });
it("separates disabled from successful empty data", async () => { mount("/p1/policies", async () => json({ error: { code: "POLICY_DISABLED" } }, 503)); await screen.findByText("정책 기능이 비활성화되어 있습니다"); expect(screen.queryByRole("form", { name: "정책 등록" })).not.toBeInTheDocument(); expect(screen.queryByText(/정상 조회된 0건/)).not.toBeInTheDocument(); });
it("refuses foreign parent scope and clears on 401", async () => {
  const t = mount(`/p1/policy-comparisons/${cid}`, async u => u.pathname.endsWith(`/${pid}`) ? json({ ...policy(), team_ids: ["00000000-0000-0000-0000-000000000001"] }) : undefined); await screen.findByText("응답 형식을 확인해 주세요"); expect(screen.queryByRole("region", { name: "정책 영향 분석" })).not.toBeInTheDocument(); t.mockImplementation(async () => json({ error: { code: "INVALID_CREDENTIALS" } }, 401)); fireEvent.click(screen.getByRole("button", { name: "비교 상세 새로고침" })); await screen.findByRole("form", { name: "백엔드 로그인" });
});
