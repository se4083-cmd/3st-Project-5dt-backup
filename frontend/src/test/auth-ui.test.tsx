import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider, useAuthManager } from "../auth/AuthProvider";
import { AuthManager } from "../auth/store";
import { ConnectedApp, RequireCapability } from "../features/p1/Foundation";

const user = "00000000-0000-0000-0000-000000000001", team = "00000000-0000-0000-0000-000000000002";
const data = (caps: string[] = ["P1_MONITOR_READ"]) => ({ userId: user, displayName: "실제 관리자", role: "ADMIN", active: true, permissions: ["OPERATIONS_READ", "PRODUCT_READ"], allowedTeamIds: [team], scopeKey: "scope-a", capabilities: caps });
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
function login() {
  fireEvent.change(screen.getByLabelText("로그인 이름"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
}
it("uses real login/session, shows only granted menus and guards direct P1 URLs", async () => {
  const transport = vi.fn<typeof fetch>(async input => String(input).endsWith("/auth/login") ? json({ access_token: "ui-memory-token", expires_in: 60 }) : json(data()));
  vi.stubGlobal("fetch", transport);
  render(<MemoryRouter initialEntries={["/p1/voc"]}><App /></MemoryRouter>);
  login();
  await screen.findByText("이 화면을 볼 권한이 없습니다");
  expect(screen.getByRole("link", { name: "운영 모니터링" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "VOC 개선 제안" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "정책 검토" })).not.toBeInTheDocument();
  expect(transport).toHaveBeenCalledTimes(2); // no feature data is fetched by preparation pages
  fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));
  await screen.findByRole("form", { name: "백엔드 로그인" });
  expect(screen.queryByRole("navigation", { name: "P1 기능 메뉴" })).not.toBeInTheDocument();
});
it("keeps the capability-guarded VOC preparation page while monitoring develops independently", async () => {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async input => String(input).endsWith("/auth/login") ? json({ access_token: "ui-memory-token", expires_in: 60 }) : json(data(["P1_VOC_READ"]))));
  render(<MemoryRouter initialEntries={["/p1/voc"]}><App /></MemoryRouter>);
  login();
  await screen.findByText("이 단계에서는 기능별 본 화면을 구현하지 않았습니다.");
  expect(screen.queryByText("검토 대기 4건 목록")).not.toBeInTheDocument();
});
it("distinguishes disabled P1 from failed login and permits manual session retry", async () => {
  let enabled = false;
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async input => String(input).endsWith("/auth/login") ? json({ access_token: "ui-memory-token", expires_in: 60 }) : enabled ? json(data()) : json({ error: { code: "P1_DISABLED", request_id: "disabled-id" } }, 503)));
  render(<MemoryRouter initialEntries={["/p1"]}><App /></MemoryRouter>);
  login();
  await screen.findByText("P1 기능이 비활성화되어 있습니다");
  expect(screen.queryByText("P1 연결 상태", { selector: "h1" })).not.toBeInTheDocument();
  enabled = true; fireEvent.click(screen.getByRole("button", { name: "권한·팀 다시 확인" }));
  await screen.findByRole("heading", { name: "P1 연결 상태" });
  expect(screen.getByText(`허용 팀 UUID: ${team}`)).toBeInTheDocument();
});
it("removes protected children immediately for refresh, revocation and 401", async () => {
  let sessionCount = 0, release!: (r: Response) => void;
  const auth = new AuthManager(async input => {
    const path = String(input);
    if (path.endsWith("/auth/login")) return json({ access_token: "ui-memory-token", expires_in: 60 });
    if (path.endsWith("/p1/session")) {
      if (sessionCount++ === 0) return json(data());
      return new Promise(resolve => { release = resolve; });
    }
    return json({ error: { code: "INVALID_CREDENTIALS" } }, 401);
  });
  function Probe() {
    const manager = useAuthManager();
    return <><button onClick={() => void manager.login("admin", "password")}>Authenticate</button>
      <button onClick={() => void manager.refresh()}>Refresh</button>
      <button onClick={() => void manager.request("/api/v1/admin/p1/monitoring/summary").catch(() => {})}>Protected request</button>
      <RequireCapability capability="P1_MONITOR_READ"><div>PRIVATE-PROTECTED-DATA</div></RequireCapability></>;
  }
  render(<MemoryRouter><AuthProvider manager={auth}><Probe /></AuthProvider></MemoryRouter>);
  fireEvent.click(screen.getByText("Authenticate")); await screen.findByText("PRIVATE-PROTECTED-DATA");
  fireEvent.click(screen.getByText("Refresh"));
  expect(screen.queryByText("PRIVATE-PROTECTED-DATA")).not.toBeInTheDocument();
  await act(async () => { release(json(data([]))); });
  expect(screen.queryByText("PRIVATE-PROTECTED-DATA")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Protected request"));
  await waitFor(() => expect(auth.getSnapshot().phase).toBe("anonymous"));
  expect(auth.getSnapshot().session).toBeNull();
});
it("keeps existing mock dashboard and its KPI available with a separate P1 login entry", async () => {
  const transport = vi.fn(); vi.stubGlobal("fetch", transport);
  render(<MemoryRouter><App /></MemoryRouter>);
  await screen.findByText("78.3%");
  expect(screen.getByRole("link", { name: "P1 API 로그인" })).toBeInTheDocument();
  expect(transport).not.toHaveBeenCalled();
});


it("works under the actual StrictMode root without duplicate login writes", async () => {
  const transport = vi.fn<typeof fetch>(async input => String(input).endsWith("/auth/login") ? json({ access_token: "strict-mode-token", expires_in: 60 }) : json(data()));
  vi.stubGlobal("fetch", transport);
  render(<StrictMode><MemoryRouter initialEntries={["/p1"]}><App /></MemoryRouter></StrictMode>);
  login();
  await screen.findByRole("heading", { name: "P1 연결 상태" });
  expect(transport.mock.calls.filter(c => String(c[0]).endsWith("/auth/login"))).toHaveLength(1);
});

it("can cancel an in-flight login and ignores its late response", async () => {
  let release!: (r: Response) => void;
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => new Promise(resolve => { release = resolve; })));
  render(<MemoryRouter initialEntries={["/p1"]}><App /></MemoryRouter>);
  login();
  fireEvent.click(await screen.findByRole("button", { name: "로그인 취소" }));
  await screen.findByRole("form", { name: "백엔드 로그인" });
  await act(async () => { release(json({ access_token: "cancelled-token", expires_in: 60 })); });
  expect(screen.queryByRole("navigation", { name: "P1 기능 메뉴" })).not.toBeInTheDocument();
});
