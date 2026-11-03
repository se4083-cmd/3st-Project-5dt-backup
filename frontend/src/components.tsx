import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { ApiError, errorText } from "./api";
import {
  can,
  kst,
  overdueMinutes,
  type Permission,
  type Session,
  type TicketPreview,
} from "./domain";

const paths = {
  home: "M3 10 12 3l9 7M5 9v12h14V9M9 21v-8h6v8",
  chat: "M21 15a3 3 0 0 1-3 3H8l-5 3V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3z",
  check: "M9 3H4v18h16V3h-5M9 3v3h6V3zM8 13l3 3 5-6",
  box: "m3 7 9-4 9 4v11l-9 4-9-4zM3 7l9 4 9-4M12 11v11M7 5l10 4",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2l3 2 4 1 1 4 2 3-2 3-1 4-4 1-3 2-3-2-4-1-1-4-2-3 2-3 1-4 4-1z",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2",
  person: "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M4 21v-3a8 6 0 0 1 16 0v3",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3z",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6zM8 12l3 3 5-6",
};
export type IconName = keyof typeof paths;
export function Icon({ name }: { name: IconName }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "purple" | "red" | "green" | "amber";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function DataTimestamp({
  value,
  label = "기준 시각",
}: {
  value: string;
  label?: string;
}) {
  return (
    <span className="timestamp">
      {label} <time dateTime={value}>{kst(value)} KST</time>
    </span>
  );
}
export function AsyncState({
  kind,
  error,
  onRetry,
  onRecover,
}: {
  kind: "loading" | "empty" | "error";
  error?: ApiError;
  onRetry?: () => void;
  onRecover?: () => void;
}) {
  if (kind === "loading")
    return (
      <section
        className="state-panel"
        role="status"
        aria-label="데이터 불러오는 중"
        aria-busy="true"
      >
        <span className="spinner" />
        <h2>업무를 불러오고 있습니다</h2>
        <p>허용된 범위의 최신 상태를 확인합니다.</p>
        <div className="skeleton" />
        <div className="skeleton short" />
      </section>
    );
  if (kind === "empty")
    return (
      <section className="state-panel" role="status">
        <span className="state-icon">
          <Icon name="check" />
        </span>
        <h2>지금 확인할 문의가 없습니다</h2>
        <p>
          정상적으로 조회된 0건입니다. 새로운 문의가 접수되면 이곳에 표시됩니다.
        </p>
      </section>
    );
  const e = error ?? new ApiError(0, "NETWORK_ERROR"),
    copy = errorText(e);
  return (
    <section className="state-panel" role="alert">
      <span className="state-icon error">
        <Icon name="shield" />
      </span>
      <h2>{copy.title}</h2>
      <p>{copy.message}</p>
      {e.traceId && <p className="small">문의용 추적 ID: {e.traceId}</p>}
      <div className="actions">
        {copy.retry && onRetry && (
          <button className="button" onClick={onRetry}>
            다시 불러오기
          </button>
        )}
        {e.status === 401 && onRecover && (
          <button className="button" onClick={onRecover}>
            시연 로그인 복구
          </button>
        )}
        <Link className="button secondary" to="/">
          운영 홈으로
        </Link>
      </div>
    </section>
  );
}
export const navigation: {
  to: string;
  label: string;
  icon: IconName;
  permission: Permission;
}[] = [
  { to: "/", label: "운영 홈", icon: "home", permission: "OPERATIONS_READ" },
  { to: "/inquiries", label: "문의", icon: "chat", permission: "INQUIRY_READ" },
  {
    to: "/followups",
    label: "후속",
    icon: "check",
    permission: "FOLLOWUP_READ",
  },
  { to: "/products", label: "제품", icon: "box", permission: "PRODUCT_READ" },
  {
    to: "/settings",
    label: "운영 설정",
    icon: "settings",
    permission: "AUTOMATION_MANAGE",
  },
];
export function AppShell({
  session,
  mock,
  children,
}: {
  session: Session | null;
  mock: boolean;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <span className="brand-icon">C</span>
          <span>
            CS Flow <small>AI</small>
          </span>
        </Link>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="주 메뉴">
          {navigation
            .filter((n) => can(session, n.permission))
            .map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "active" : ""}`
                }
              >
                <Icon name={n.icon} />
                <span>{n.label}</span>
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="store">
            <span className="store-icon">S</span>
            <div>
              <strong>스토어 A</strong>
              <small>
                {session
                  ? `허용 팀 ${session.allowedTeamIds.length}개`
                  : "인증 확인 필요"}
              </small>
            </div>
          </div>
          <div className="demo-note">
            <strong>{mock ? "DEVELOPMENT DEMO" : "BACKEND CONNECTION"}</strong>
            <p>
              {mock
                ? "합성 응답으로 1주차 화면을 검토합니다."
                : "서버의 인증과 업무 범위에 따라 표시합니다."}
            </p>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            WORKSPACE <span>/</span> 운영 관리
          </div>
          <div className="manager">
            <span className="avatar">M</span>
            <div>
              <strong>
                {session?.role === "ADMIN" ? "E-commerce Manager" : "계정 확인"}
              </strong>
              <small>
                {session?.displayName ?? "로그인 상태 확인 중"} ·{" "}
                {mock ? "개발용 계정" : "서버 인증"}
              </small>
            </div>
          </div>
        </header>
        <main id="main" className="main" tabIndex={-1}>
          {children}
          <footer>
            CS Flow AI · React Frontend / Week 01{" "}
            <span>
              {mock ? "합성 데이터 · 실제 발송 없음" : "서버 권한 검증 필요"}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
export function PageHeading({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">YOUR OPERATIONS, AT A GLANCE</p>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
export function TicketList({
  items,
  asOf,
  total = items.length,
}: {
  items: TicketPreview[];
  asOf: string;
  total?: number;
}) {
  if (!items.length)
    return total === 0 ? (
      <AsyncState kind="empty" />
    ) : (
      <p className="notice">
        검토 대기 {total}건의 미리보기가 제공되지 않았습니다. 전체 업무 수는 위
        카드에서 확인하세요.
      </p>
    );
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label="우선 확인 문의 목록"
    >
      <table>
        <caption className="sr-only">
          기한 초과와 마감 시각 순의 문의 미리보기
        </caption>
        <thead>
          <tr>
            <th scope="col">문의 / 고객 요청</th>
            <th scope="col">확인할 이유</th>
            <th scope="col">첫 응답 기한</th>
            <th scope="col">
              <span className="sr-only">문의 열기</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => {
            const minutes = overdueMinutes(t.firstResponseDueAt, asOf);
            return (
              <tr key={t.id}>
                <td>
                  <Link
                    to={`/inquiries/${encodeURIComponent(t.id)}`}
                    className="ticket-link"
                  >
                    <strong>{t.id}</strong>
                    <span>{t.subject}</span>
                  </Link>
                </td>
                <td>{t.reason}</td>
                <td>
                  <Badge tone={minutes ? "red" : "neutral"}>
                    {minutes
                      ? `${minutes}분 초과`
                      : `${Math.ceil((Date.parse(t.firstResponseDueAt) - Date.parse(asOf)) / 60_000)}분 남음`}
                  </Badge>
                </td>
                <td>
                  <Link
                    aria-label={`${t.id} 문의 열기`}
                    to={`/inquiries/${encodeURIComponent(t.id)}`}
                    className="icon-link"
                  >
                    <Icon name="arrow" />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
