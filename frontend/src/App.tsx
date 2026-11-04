import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { ApiError, createHttpClient } from "./api";
import {
  can,
  type Permission,
  type Session,
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
import { AppShell, AsyncState, Badge } from "./components";
import { Dashboard } from "./Dashboard";
import { createOperationsClient } from "./operations";
import {
  AutomationPage,
  Customer360Page,
  FollowupsPage,
  InquiriesPage,
  InquiryDetailPage,
  ProductDetailPage,
  ProductsPage,
  QualityMaterialPage,
  QualityPage,
} from "./Workspaces";

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
  const operations = useMemo(
    () => createOperationsClient(mock, profile),
    [mock, profile],
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
            <Require session={user} permission="EXCEPTION_QUEUE_READ">
              <InquiriesPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/inquiries/:id"
          element={
            <Require session={user} permission="INQUIRY_READ">
              <InquiryDetailPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/customers/:id/360"
          element={
            <Require session={user} permission="INQUIRY_READ">
              <Customer360Page client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/followups"
          element={
            <Require session={user} permission="FOLLOWUP_READ">
              <FollowupsPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/products"
          element={
            <Require session={user} permission="PRODUCT_READ">
              <ProductsPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/products/:id"
          element={
            <Require session={user} permission="PRODUCT_READ">
              <ProductDetailPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/settings"
          element={
            <Require session={user} permission="AUTOMATION_READ">
              <AutomationPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/quality"
          element={
            <Require session={user} permission="QUALITY_REVIEW">
              <QualityPage client={operations} session={user} resourceKey={resourceKey} />
            </Require>
          }
        />
        <Route
          path="/quality/:id"
          element={
            <Require session={user} permission="QUALITY_REVIEW">
              <QualityMaterialPage client={operations} session={user} resourceKey={resourceKey} />
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
            <span>DEMO</span> 개발용 상태 시연{" "}
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
