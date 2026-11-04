import { useCallback } from "react";
import { Link } from "react-router-dom";
import type { ApiClient } from "./api";
import {
  can,
  countTotal,
  percent,
  sessionKey,
  workLabels,
  workStates,
  type Session,
  type Overview,
  type WorkState,
} from "./domain";
import {
  AsyncState,
  Badge,
  DataTimestamp,
  Icon,
  PageHeading,
  TicketList,
  type IconName,
} from "./components";
import { useResource } from "./useResource";

const icons: Record<WorkState, IconName> = {
  REVIEW: "chat",
  WORKING: "person",
  FOLLOWUP_PENDING: "check",
  AI_RUNNING: "spark",
};
function AnalyticsCard({ data }: { data: Overview["analytics"] }) {
  if (data.status === "not_ready")
    return (
      <section className="card">
        <div className="card-heading">
          <h2>AI가 처리한 결과</h2>
          <Badge>미집계</Badge>
        </div>
        <div className="analytics-empty">
          <Icon name="clock" />
          <strong>아직 분석 결과가 없습니다</strong>
          <p>
            최초 정상 배치 전입니다.
            <br />
            완료율을 0%로 표시하지 않습니다.
          </p>
        </div>
      </section>
    );
  const value = percent(data.numerator, data.denominator);
  return (
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>AI가 처리한 결과</h2>
          <p>{data.periodLabel}</p>
        </div>
        <Badge tone={data.status === "stale" ? "amber" : "purple"}>
          {data.status === "stale" ? "이전 정상 결과" : "기간 성과"}
        </Badge>
      </div>
      {data.status === "stale" && (
        <p className="notice amber" role="status">
          갱신이 지연되어 이전 정상 결과를 유지합니다.
        </p>
      )}
      <div className="analytics-chart">
        <div
          className="ring"
          style={{
            background: `conic-gradient(#5844e8 0 ${value ?? 0}%, #eeeaff ${value ?? 0}% 100%)`,
          }}
        >
          <div>
            <strong>{value === null ? "—" : `${value}%`}</strong>
            <small>자동 안내 완료율</small>
          </div>
        </div>
        <div className="fraction">
          <strong>
            {data.numerator} <span>/ {data.denominator}</span>
          </strong>
          <p>
            적격 회차 중<br />
            자동 안내 완료
          </p>
        </div>
      </div>
      {value === null && (
        <p className="notice">적격 회차가 없어 완료율을 산정하지 않습니다.</p>
      )}
      <div className="card-bottom">
        <DataTimestamp value={data.asOf} label="분석 기준" />
        <p>현재 대기 건수와 합산하지 않습니다.</p>
      </div>
    </section>
  );
}
export function Dashboard({
  session,
  client,
  resourceKey,
  retry,
  recover,
}: {
  session: Session;
  client: ApiClient;
  resourceKey: string;
  retry: () => void;
  recover?: () => void;
}) {
  const load = useCallback(
    (signal: AbortSignal) => client.getOverview(session, signal),
    [client, session],
  );
  const state = useResource(`${sessionKey(session)}:${resourceKey}`, load);
  const heading = (
    <PageHeading
      title="오늘의 운영"
      subtitle="지금 확인할 문의와 남은 업무를 한곳에 모았어요."
      action={
        <button className="button secondary" onClick={retry}>
          <Icon name="clock" /> 새로고침
        </button>
      }
    />
  );
  if (state.status === "loading")
    return (
      <>
        {heading}
        <AsyncState kind="loading" />
      </>
    );
  if (state.status === "error")
    return (
      <>
        {heading}
        <AsyncState
          kind="error"
          error={state.error}
          onRetry={retry}
          onRecover={recover}
        />
      </>
    );
  const data = state.data;
  return (
    <>
      {heading}
      <div className="data-meta">
        <Badge tone="purple">
          {data.source === "synthetic" ? "합성 UI 데이터" : "현재 업무 데이터"}
        </Badge>
        <span>
          범위 {session.scopeKey} · {session.allowedTeamIds.length}개 팀
        </span>
        <DataTimestamp value={data.asOf} />
      </div>
      <section className="hero">
        <div>
          <p className="eyebrow">NEEDS YOUR ATTENTION</p>
          <h2>
            {data.workload.REVIEW
              ? `관리자 확인이 필요한 문의가 ${data.workload.REVIEW}건 있습니다`
              : "지금 검토할 문의를 모두 확인했습니다"}
          </h2>
          <p>
            {data.reviewOverdue
              ? `첫 응답 기한을 넘긴 ${data.reviewOverdue}건부터 확인해 주세요.`
              : "남은 후속과 자동 안내 상태를 확인해 주세요."}
          </p>
        </div>
        {can(session, "INQUIRY_READ") && (
          <Link className="button hero-button" to="/inquiries?state=REVIEW">
            검토 목록 <Icon name="arrow" />
          </Link>
        )}
      </section>
      <section className="workload-grid" aria-label="현재 문의 수">
        {workStates.map((key) => {
          const content = (
            <>
              <span className="stat-label">
                {workLabels[key]}
                <span className="icon-box">
                  <Icon name={icons[key]} />
                </span>
              </span>
              <strong
                className={`stat-value ${key === "REVIEW" ? "red-text" : key === "AI_RUNNING" ? "green-text" : ""}`}
              >
                {data.workload[key]}
                <small>건</small>
              </strong>
              <span className="stat-note">
                {key === "REVIEW"
                  ? `첫 응답 기한 초과 ${data.reviewOverdue}건`
                  : key === "WORKING"
                    ? "현재 담당자의 문의"
                    : key === "FOLLOWUP_PENDING"
                      ? "추가 확인 중인 문의 수"
                      : "현재 자동 안내 작업"}
              </span>
            </>
          );
          return can(session, "INQUIRY_READ") ? (
            <Link
              key={key}
              className="stat-card"
              to={`/inquiries?state=${key}`}
              aria-label={`${workLabels[key]} ${data.workload[key]}건 목록`}
            >
              {content}
            </Link>
          ) : (
            <div className="stat-card" key={key}>
              {content}
            </div>
          );
        })}
      </section>
      <p className="count-note">
        현재 업무 문의 합계 <strong>{countTotal(data.workload)}건</strong> ·
        같은 기준 시각의 중복 없는 현재 회차 기준
      </p>
      <div className="dashboard-grid">
        <section className="card">
          <div className="card-heading">
            <div>
              <h2>지금 확인할 문의</h2>
              <p>기한 초과 → 마감 시각 → 접수 시각 순</p>
            </div>
            {can(session, "INQUIRY_READ") && (
              <Link className="text-link" to="/inquiries?state=REVIEW">
                목록 연결 →
              </Link>
            )}
          </div>
          {can(session, "INQUIRY_READ") ? (
            <TicketList
              items={data.previewTickets}
              asOf={data.asOf}
              total={data.workload.REVIEW}
            />
          ) : (
            <p className="notice">문의 목록 조회 권한이 없습니다.</p>
          )}
          <div className="card-bottom">
            <span>
              미리보기 {data.previewTickets.length}건 · 전체 업무 수는 위 카드
              기준
            </span>
            <Icon name="shield" />
          </div>
        </section>
        <AnalyticsCard data={data.analytics} />
        <section className="card">
          <div className="card-heading">
            <div>
              <h2>남은 후속 업무</h2>
              <p>문의 수와 다른 단위인 ‘업무 수’입니다</p>
            </div>
            <span className="icon-box">
              <Icon name="check" />
            </span>
          </div>
          <div className="followup-count">
            <strong>
              {data.openFollowupTasks}
              <small>개 업무</small>
            </strong>
            <Badge tone="amber">미완료 후속</Badge>
          </div>
          <p className="card-description">
            후속 대기 문의 {data.workload.FOLLOWUP_PENDING}건과 별도로
            집계합니다. 하나의 문의에 여러 업무가 연결될 수 있습니다.
          </p>
          {can(session, "FOLLOWUP_READ") && (
            <Link className="text-link" to="/followups">
              후속 화면 연결 →
            </Link>
          )}
        </section>
        <section className="card">
          <div className="card-heading">
            <div>
              <h2>반복되는 문의 살펴보기</h2>
              <p>제품 정보와 VOC 근거를 연결합니다</p>
            </div>
            <span className="icon-box">
              <Icon name="box" />
            </span>
          </div>
          <p className="card-description">
            게시된 VOC TOP 10과 점수 산정 불가 제품을 같은 분석 배치로 확인합니다.
            기본 상품 카탈로그는 별도 API 계약이 필요합니다.
          </p>
          {can(session, "PRODUCT_READ") && (
            <Link className="text-link" to="/products">
              제품·VOC 보기 →
            </Link>
          )}
        </section>
      </div>
    </>
  );
}
