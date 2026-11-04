import { Link, NavLink, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api";
import { AppShell, AsyncState, PageHeading } from "../../components";
import { useAuth, useAuthManager } from "../../auth/AuthProvider";
import { LoginPanel } from "../../auth/LoginPanel";
import { hasCapability } from "../../auth/session";
import type { P1Session } from "../../auth/session";
import { MonitoringPage } from "../monitoring/MonitoringPage";
import "./foundation.css";

const features = [
  { path: "/p1/monitoring", label: "운영 모니터링", capability: "P1_MONITOR_READ" },
  { path: "/p1/voc", label: "VOC 개선 제안", capability: "P1_VOC_READ" },
  { path: "/p1/policies", label: "정책 검토", capability: "P1_POLICY_READ" },
];
export function RequireCapability({ capability, children }: { capability: string; children: ReactNode }) {
  const state = useAuth();
  return state.phase === "ready" && hasCapability(state.session, capability)
    ? children : <AsyncState kind="error" error={new ApiError(403, "EXPLICIT_PERMISSION_REQUIRED")} />;
}
function Preparation({ title }: { title: string }) {
  return <section className="card"><PageHeading title={title} subtitle="인증·통신 연결 준비" />
    <p>이 단계에서는 기능별 본 화면을 구현하지 않았습니다.</p>
    <p className="notice">API 요청은 서버에서 현재 권한과 팀 범위를 다시 검사합니다.</p></section>;
}
function Toolbar() {
  const auth = useAuthManager(), state = useAuth();
  return <section className="p1-foundation-bar" aria-label="실제 백엔드 인증">
    <span>HTTP · 서버 인증</span>
    <Link to="/p1">P1 연결 상태</Link>
    <nav aria-label="P1 기능 메뉴">{features.filter(f => hasCapability(state.session, f.capability)).map(f =>
      <NavLink key={f.path} to={f.path}>{f.label}</NavLink>)}</nav>
    <button className="button secondary" onClick={() => void auth.refresh()}>권한·팀 다시 확인</button>
    <button className="button secondary" onClick={() => auth.logout()}>로그아웃</button>
  </section>;
}
function ConnectionStatus() {
  const { session } = useAuth();
  return <section className="card"><PageHeading title="P1 연결 상태" subtitle="실제 로그인·P1 세션 조회 결과입니다. 외부 Azure/RAG 연동 확인을 뜻하지 않습니다." />
    <p>{session?.displayName} · ADMIN</p>
    <p>허용 팀 UUID: {session?.allowedTeamIds.join(", ")}</p>
    <p>현재 capability: {session?.capabilities.join(", ") || "없음"}</p>
    <p className="notice">P0 운영 홈의 KPI와 P1 집계는 별도 계약입니다. 연결되지 않은 API를 합성 응답으로 대체하지 않습니다.</p>
    <Link className="button secondary" to="/">기존 운영 홈</Link>
  </section>;
}
export function ConnectedApp({ p1Route, renderLegacy }: { p1Route: boolean; renderLegacy: (session: P1Session, transport: typeof fetch, epoch: number, toolbar: ReactNode) => ReactNode }) {
  const auth = useAuthManager(), state = useAuth();
  if (state.phase !== "ready" || !state.session) return <AppShell session={null} mock={false}>
    {state.phase === "anonymous" ? <LoginPanel /> : state.phase === "authenticating" || state.phase === "loading" ? <AsyncState kind="loading" /> : <>
      <AsyncState kind="error" error={state.error} onRetry={() => void auth.refresh()} />
      <button className="button secondary" onClick={() => auth.logout()}>다른 계정으로 로그인</button>
      <button className="button secondary" onClick={() => void auth.refresh()}>권한·팀 다시 확인</button>
    </>}
    {(state.phase === "authenticating" || state.phase === "loading") && <button className="button secondary" onClick={() => auth.logout()}>로그인 취소</button>}
    <p><Link to="/">운영 홈으로</Link></p>
  </AppShell>;
  if (!p1Route) return renderLegacy(state.session, auth.fetch, state.epoch, <Toolbar />);
  return <AppShell session={state.session} mock={false}><div key={state.epoch}>
    <Toolbar />
    <Routes>
      <Route path="/p1" element={<ConnectionStatus />} />
      <Route path="/p1/monitoring" element={<RequireCapability capability="P1_MONITOR_READ"><MonitoringPage /></RequireCapability>} />
      {features.filter(f => f.path !== "/p1/monitoring").map(f => <Route key={f.path} path={`${f.path}/*`} element={<RequireCapability capability={f.capability}><Preparation title={f.label} /></RequireCapability>} />)}
      <Route path="/p1/policy-comparisons/*" element={<RequireCapability capability="P1_POLICY_READ"><Preparation title="정책 비교 검토" /></RequireCapability>} />
      <Route path="*" element={<AsyncState kind="error" error={new ApiError(404, "NOT_FOUND")} />} />
    </Routes>
  </div></AppShell>;
}
