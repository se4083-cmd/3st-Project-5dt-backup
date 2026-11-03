import { useCallback, useMemo, useState, type ReactNode } from "react";
import {
  Link,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { ApiError, createHttpClient } from "./api";
import {
  can,
  workLabels,
  workStates,
  type Permission,
  type Session,
  type WorkState,
} from "./domain";
import {
  createMockClient,
  scenarios,
  scenarioLabels,
  profileLabels,
  type Profile,
  type Scenario,
} from "./fixtures";
import { useResource } from "./useResource";
import { AppShell, AsyncState, Badge, PageHeading } from "./components";
import { Dashboard } from "./Dashboard";

function Require({
  session,
  permission,
  children,
}: {
  session: Session;
  permission: Permission;
  children: ReactNode;
}) {
  return can(session, permission) ? (
    children
  ) : (
    <AsyncState kind="error" error={new ApiError(403, "FORBIDDEN")} />
  );
}
function PlannedPage({
  title,
  week,
  description,
}: {
  title: string;
  week: number;
  description: string;
}) {
  const [query] = useSearchParams();
  const { id } = useParams();
  const filter = query.get("state");
  if (filter && !workStates.includes(filter as WorkState))
    return (
      <AsyncState kind="error" error={new ApiError(422, "INVALID_FILTER")} />
    );
  return (
    <>
      <PageHeading
        title={title}
        subtitle="공통 메뉴와 화면 연결을 확인하는 1주차 구현입니다."
      />
      <section className="card planned">
        <Badge tone="purple">{week}주차 연결 예정</Badge>
        <h2>
          {id ? `문의 ${id}` : filter ? workLabels[filter as WorkState] : title}
        </h2>
        <p>{description}</p>
        {filter && (
          <p className="notice">
            선택한 목록 조건: <strong>{workLabels[filter as WorkState]}</strong>
            <br />
            목록 API 연결 전입니다. 현재 화면을 조회 결과 0건으로 해석하지
            않습니다.
          </p>
        )}
        <p className="small muted">
          원장 변경·고객 발송·자동화 제어는 이 단계에서 실행하지 않습니다.
        </p>
        <Link className="button secondary" to="/">
          운영 홈으로
        </Link>
      </section>
    </>
  );
}
export default function App() {
  const mock = (import.meta.env.VITE_DATA_MODE ?? "mock") === "mock";
  const [profile, setProfile] = useState<Profile>("manager");
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [revision, setRevision] = useState(0);
  const client = useMemo(
    () =>
      mock
        ? createMockClient(profile, scenario)
        : createHttpClient({
            sessionPath: import.meta.env.VITE_SESSION_PATH,
            overviewPath: import.meta.env.VITE_OVERVIEW_PATH,
          }),
    [mock, profile, scenario],
  );
  const loadSession = useCallback(
    (signal: AbortSignal) => client.getSession(signal),
    [client],
  );
  const resourceKey = `${profile}:${scenario}:${revision}`;
  const session = useResource(`session:${resourceKey}`, loadSession);
  const retry = () => setRevision((n) => n + 1);
  const recover = () => {
    setProfile("manager");
    setScenario("normal");
    retry();
  };
  let content: ReactNode;
  if (session.status === "loading") content = <AsyncState kind="loading" />;
  else if (session.status === "error")
    content = (
      <AsyncState
        kind="error"
        error={session.error}
        onRetry={retry}
        onRecover={mock ? recover : undefined}
      />
    );
  else if (!can(session.data, "OPERATIONS_READ"))
    content = (
      <AsyncState kind="error" error={new ApiError(403, "FORBIDDEN")} />
    );
  else {
    const user = session.data;
    content = (
      <Routes>
        <Route
          path="/"
          element={
            <Dashboard
              key={resourceKey}
              session={user}
              client={client}
              resourceKey={resourceKey}
              retry={retry}
              recover={mock ? recover : undefined}
            />
          }
        />
        <Route
          path="/inquiries"
          element={
            <Require session={user} permission="INQUIRY_READ">
              <PlannedPage
                title="문의 관리"
                week={2}
                description="예외 큐, 담당 인수, 초안 검토·승인·발송은 Backend A/B 계약 확정 후 연결합니다."
              />
            </Require>
          }
        />
        <Route
          path="/inquiries/:id"
          element={
            <Require session={user} permission="INQUIRY_READ">
              <PlannedPage
                title="문의 작업"
                week={2}
                description="현재는 선택한 문의의 경로만 연결했습니다. 고객 원문과 주문 상세는 담당·범위 검사를 포함한 API 연결 후 표시합니다."
              />
            </Require>
          }
        />
        <Route
          path="/followups"
          element={
            <Require session={user} permission="FOLLOWUP_READ">
              <PlannedPage
                title="후속 관리"
                week={3}
                description="티켓 공개 후속과 제품 내부 조치를 공통 폼으로 연결합니다. 문의 수와 후속 업무 수는 별도 집계합니다."
              />
            </Require>
          }
        />
        <Route
          path="/products"
          element={
            <Require session={user} permission="PRODUCT_READ">
              <PlannedPage
                title="제품"
                week={3}
                description="기본 제품 목록·상세, VOC TOP 10과 상세 근거를 같은 제품·범위·배치로 연결합니다."
              />
            </Require>
          }
        />
        <Route
          path="/settings"
          element={
            <Require session={user} permission="AUTOMATION_MANAGE">
              <PlannedPage
                title="운영 설정"
                week={4}
                description="자동화 중지·재개는 별도의 서버 실행 권한, 사유 기록과 감사 이력을 연결한 뒤 제공합니다."
              />
            </Require>
          }
        />
        <Route
          path="*"
          element={
            <AsyncState kind="error" error={new ApiError(404, "NOT_FOUND")} />
          }
        />
      </Routes>
    );
  }
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        본문으로 건너뛰기
      </a>
      {mock && (
        <details className="dev-controls">
          <summary>
            <span>WEEK 01</span> 개발용 상태 시연{" "}
            <Badge tone="purple">합성 데이터</Badge>
          </summary>
          <div>
            <label>
              응답 상태
              <select
                aria-label="응답 상태"
                value={scenario}
                onChange={(e) => setScenario(e.target.value as Scenario)}
              >
                {scenarios.map((s) => (
                  <option key={s} value={s}>
                    {scenarioLabels[s]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              권한 프로필
              <select
                aria-label="권한 프로필"
                value={profile}
                onChange={(e) => setProfile(e.target.value as Profile)}
              >
                {Object.entries(profileLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary" onClick={recover}>
              시연 초기화
            </button>
            <p>
              개발용 선택기입니다. 실제 권한을 부여하거나 서버에 로그인하지
              않습니다.
            </p>
          </div>
        </details>
      )}
      <AppShell
        session={session.status === "ready" ? session.data : null}
        mock={mock}
      >
        {content}
      </AppShell>
    </>
  );
}
