import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App";
import { aiCalls, analyticsMeta, job, json, monitorSession, page, summary, teamA, teamB } from "./monitoring-fixtures";

afterEach(() => { vi.unstubAllGlobals(); });
function mount(handler?: (url: URL, init?: RequestInit) => Promise<Response>, teams = [teamA], caps = ["P1_MONITOR_READ"]) {
  const transport = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), "http://local.invalid");
    if (url.pathname.endsWith("/auth/login")) return json({ access_token: "monitor-ui-test-token", expires_in: 3600 });
    if (url.pathname.endsWith("/p1/session")) return json(monitorSession(teams, caps));
    if (handler) return handler(url, init);
    return response(url, teams);
  });
  vi.stubGlobal("fetch", transport);
  render(<MemoryRouter initialEntries={["/p1/monitoring"]}><App /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("로그인 이름"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "synthetic-test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  return transport;
}
function response(url: URL, teams = [teamA]) {
  if (url.pathname.endsWith("/summary")) return json(summary(teams, url.searchParams.get("job_kind") ?? ""));
  if (url.pathname.endsWith("/jobs")) return json(page(teams));
  return json(aiCalls(teams));
}
const section = (name: string) => within(screen.getByRole("region", { name }));
it("renders successful zeros separately from unobserved AI, unpublished analytics, and unknown control", async () => {
  const transport = mount();
  await screen.findByText("정상 조회된 0건입니다.", { exact: false });
  expect(section("작업 현황").getByText("현재 실패").parentElement).toHaveTextContent("0건");
  expect(section("작업 현황").getByText("자동화 세대 불일치").parentElement).toHaveTextContent("미확인");
  expect(screen.getByText("미게시")).toBeInTheDocument();
  expect(screen.getByText("제어 조회 권한 필요")).toBeInTheDocument();
  expect(section("AI 호출 상태").getByText("에러율").parentElement).toHaveTextContent("미관측");
  expect(screen.queryByText("0%")).not.toBeInTheDocument();
  expect(screen.getAllByText("조회 요청 ID: monitor-test-request")).toHaveLength(3);
  const requests = transport.mock.calls.filter(c => String(c[0]).includes("/monitoring/"));
  expect(requests).toHaveLength(3);
  requests.forEach(c => expect(new Headers(c[1]?.headers).get("Authorization")).toBe("Bearer monitor-ui-test-token"));
});
it("applies team/kind/status to supported endpoints only, pages with opaque cursors and resets paging on filters", async () => {
  const transport = mount(async url => {
    const teams = url.searchParams.get("team_ids") ? [url.searchParams.get("team_ids")!] : [teamA, teamB];
    if (!url.pathname.endsWith("/jobs")) return response(url, teams);
    const item = { ...job(), job_kind: url.searchParams.get("job_kind") || "AUTO", status: url.searchParams.get("status") || "FAILED" };
    return json(page(teams, [item], url.searchParams.has("cursor") ? null : "opaque+/=cursor"));
  }, [teamA, teamB]);
  const next = await screen.findByRole("button", { name: "다음 페이지" });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  await screen.findByText("2페이지");
  await waitFor(() => expect(next).toBeDisabled());
  expect(transport.mock.calls.some(c => new URL(String(c[0]), "http://local").searchParams.get("cursor") === "opaque+/=cursor")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "이전 페이지" }));
  await screen.findByText("1페이지");
  fireEvent.change(screen.getByLabelText("팀 범위"), { target: { value: teamB } });
  await waitFor(() => expect(section("작업 이력").getByText("TIMEOUT")).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("작업 종류"), { target: { value: "HANDOFF" } });
  await waitFor(() => expect(section("작업 이력").getByText("상담 인계")).toBeInTheDocument());
  const before = transport.mock.calls.length;
  fireEvent.change(screen.getByLabelText("상태 (작업 목록만)"), { target: { value: "RUNNING" } });
  await waitFor(() => expect(section("작업 이력").getByText("실행 중")).toBeInTheDocument());
  const changes = transport.mock.calls.slice(before);
  expect(changes).toHaveLength(1);
  const url = new URL(String(changes[0][0]), "http://local");
  expect(url.searchParams.get("status")).toBe("RUNNING");
  expect(url.searchParams.get("team_ids")).toBe(teamB);
  expect(url.searchParams.get("job_kind")).toBe("HANDOFF");
  expect(url.searchParams.has("cursor")).toBe(false);
  fireEvent.change(screen.getByLabelText("페이지당 작업"), { target: { value: "50" } });
  await waitFor(() => expect(String(transport.mock.calls.at(-1)?.[0])).toContain("limit=50"));
});
it.each([true, false])("uses server freshness (stale=%s), retains source dates and labels synthetic origin", async stale => {
  mount(async url => url.pathname.endsWith("/summary") ? json({ ...summary(), analytics: { availability: "AVAILABLE", reason: null, meta: analyticsMeta([teamA], stale), connection_status: "UNOBSERVED" } }) : response(url));
  await screen.findByText(stale ? "오래된 데이터" : "서버 최신성 기준 충족");
  expect(screen.getByText("합성 분석 데이터")).toBeInTheDocument();
  expect(document.querySelector('time[datetime="2026-10-31T03:00:00Z"]')).toBeInTheDocument();
  expect(screen.getByText(/실제 Fabric 연결은 미관측/)).toBeInTheDocument();
});
it("distinguishes missing scope from unpublished analytics", async () => {
  mount(async url => url.pathname.endsWith("/summary") ? json({ ...summary(), analytics: { ...summary().analytics, reason: "SCOPE_NOT_PROVIDED" } }) : response(url));
  await screen.findByText("선택 팀 데이터 없음");
  expect(screen.queryByText("미게시")).not.toBeInTheDocument();
});
it("shows failed summary with request ID without fabricating zeros and keeps successful panels", async () => {
  let failed = true;
  mount(async url => failed && url.pathname.endsWith("/summary") ? json({ error: { code: "INTERNAL_ERROR" } }, 500, "failure-request-id") : response(url));
  await screen.findByText("문의용 추적 ID: failure-request-id");
  expect(section("작업 현황").queryByText("현재 실패")).not.toBeInTheDocument();
  expect(section("AI 호출 상태").getByText("에러율")).toBeInTheDocument();
  failed = false;
  fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
  await waitFor(() => expect(section("작업 현황").getByText("현재 실패")).toBeInTheDocument());
});
it("handles a server feature flag disabled after login without treating it as a network failure", async () => {
  mount(async () => json({ error: { code: "P1_DISABLED" } }, 503));
  await waitFor(() => expect(screen.getAllByText("P1 기능이 비활성화되어 있습니다")).toHaveLength(3));
  expect(screen.queryByText("현재 실패")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "다시 불러오기" })).not.toBeInTheDocument();
});
it("denies direct URL and menu without capability and issues no monitoring requests", async () => {
  const transport = mount(undefined, [teamA], []);
  await screen.findByText("이 화면을 볼 권한이 없습니다");
  expect(screen.queryByRole("link", { name: "운영 모니터링" })).not.toBeInTheDocument();
  expect(transport).toHaveBeenCalledTimes(2);
});
it("clears the monitoring screen and token on a current endpoint 401", async () => {
  mount(async () => json({ error: { code: "INVALID_CREDENTIALS" } }, 401));
  await screen.findByText("세션이 만료되어 보호 데이터를 제거했습니다.");
  expect(screen.getByRole("form", { name: "백엔드 로그인" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "운영 모니터링" })).not.toBeInTheDocument();
});
it("aborts old team queries and never displays a late response for the previous scope", async () => {
  let release!: (response: Response) => void, priorSignal: AbortSignal | undefined;
  mount(async (url, init) => {
    if (url.pathname.endsWith("/summary") && !url.searchParams.has("team_ids")) {
      priorSignal = init?.signal as AbortSignal;
      return new Promise(resolve => { release = resolve; });
    }
    return response(url, [teamB]);
  }, [teamA, teamB]);
  await screen.findByLabelText("팀 범위");
  await waitFor(() => expect(release).toBeTypeOf("function"));
  fireEvent.change(screen.getByLabelText("팀 범위"), { target: { value: teamB } });
  await screen.findByText("현재 실패");
  expect(priorSignal?.aborted).toBe(true);
  const old = summary([teamA, teamB]); old.jobs.current_failed = 987654;
  await act(async () => release(json(old)));
  expect(screen.queryByText("987,654")).not.toBeInTheDocument();
});
it("removes loaded monitoring data when a refreshed session revokes capability", async () => {
  const transport = mount();
  await screen.findByText("현재 실패");
  transport.mockImplementation(async input => String(input).endsWith("/p1/session") ? json(monitorSession([teamB], [])) : json({}));
  fireEvent.click(screen.getByRole("button", { name: "권한·팀 다시 확인" }));
  expect(screen.queryByText("현재 실패")).not.toBeInTheDocument();
  await screen.findByText("이 화면을 볼 권한이 없습니다");
});
