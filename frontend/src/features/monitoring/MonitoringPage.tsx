import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useAuth, useAuthManager } from "../../auth/AuthProvider";
import { AsyncState, Badge, DataTimestamp, PageHeading } from "../../components";
import { useResource, type Resource } from "../../useResource";
import { createMonitoringClient } from "./api";
import { jobStatuses, type AiCalls, type JobKind, type JobPage, type JobStatus, type MonitorSummary } from "./contracts";
import "./monitoring.css";

export const statusLabels: Record<JobStatus, string> = {
  PENDING: "대기", RUNNING: "실행 중", RETRY: "재시도 대기", SUCCEEDED: "성공", FAILED: "실패", HANDED_OFF: "인계 완료", CANCELLED: "취소",
};
const kindLabel = (kind: JobKind) => kind === "AUTO" ? "자동응답" : "상담 인계";
type Result<T> = { data: T; requestId?: string };
function ResultPanel<T>({ title, resource, retry, children }: { title: string; resource: Resource<Result<T>>; retry: () => void; children: (data: T) => ReactNode }) {
  return <section className="card monitoring-panel" aria-label={title}>
    <h2>{title}</h2>
    {resource.status === "loading" ? <AsyncState kind="loading" /> : resource.status === "error"
      ? <AsyncState kind="error" error={resource.error} onRetry={retry} />
      : <>{children(resource.data.data)}{resource.data.requestId && <p className="small monitoring-id">조회 요청 ID: {resource.data.requestId}</p>}</>}
  </section>;
}
function Metric({ title, value, description, alert = false }: { title: string; value: number | null; description: string; alert?: boolean }) {
  return <div className="monitoring-metric"><dt>{title}</dt><dd className={alert && value ? "monitoring-danger" : ""}>
    {value === null ? "미확인" : <>{value.toLocaleString("ko-KR")}<small>건</small></>}
  </dd><p>{description}</p></div>;
}
function Summary({ data }: { data: MonitorSummary }) {
  const j = data.jobs;
  return <>
    <DataTimestamp value={data.as_of} label="작업 집계 기준" />
    <p className="small">선택한 팀·작업 종류의 집계입니다. 상태 필터는 적용되지 않습니다. 단위는 문의 수가 아닌 작업 수입니다.</p>
    <dl className="monitoring-metrics">
      <Metric title="실행 가능 대기" value={j.eligible_pending} description="현재 회차·버전, 실행 시각 도달, 자동응답 제어 조건 충족. 실제 실행 보장은 아닙니다." />
      <Metric title="실행 중" value={j.active_running} description="현재 회차·버전이며 임대가 만료되지 않은 작업" />
      <Metric title="재시도 대기" value={j.retry_wait} description="현재 회차·버전의 RETRY 작업" />
      <Metric title="현재 실패" value={j.current_failed} description="현재 회차·버전의 FAILED 작업" alert />
      <Metric title="실행 임대 만료" value={j.expired_running} description="현재 RUNNING 작업 중 임대가 만료된 작업" alert />
      <Metric title="자동화 세대 불일치" value={j.generation_mismatch} description="자동응답 대기·실행·재시도 중 제어 세대 불일치. 제어 정보가 없으면 미확인." alert />
      <Metric title="이전 회차·버전" value={j.superseded} description="문의의 현재 회차 또는 버전과 일치하지 않는 작업" />
    </dl>
    <p className="notice">팀 미배정·접근 불가 팀은 집계에서 제외됩니다. 임대 만료와 세대 불일치 등은 겹칠 수 있어 합산하지 않습니다.</p>
    <p>자동화 제어: {data.automation.availability === "AVAILABLE"
      ? <Badge tone={data.automation.paused ? "amber" : "green"}>{data.automation.paused ? "일시 정지" : "활성"}</Badge>
      : <Badge>{data.automation.reason === "PERMISSION_REQUIRED" ? "제어 조회 권한 필요" : "제어 정보 미확인"}</Badge>}
      <span className="small"> · 변경 조작은 제공하지 않습니다.</span></p>
    <details><summary>작업 종류·상태별 원본 집계 (이전 이력 포함)</summary>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="원본 작업 집계"><table>
        <caption className="sr-only">현재 작업과 이전 이력을 포함한 상태별 작업 수</caption>
        <thead><tr><th scope="col">작업 종류</th>{jobStatuses.map(s => <th scope="col" key={s}>{statusLabels[s]}</th>)}</tr></thead>
        <tbody>{j.raw_counts.map(row => <tr key={row.job_kind}><th scope="row">{kindLabel(row.job_kind)}</th>{row.counts.map(c => <td key={c.status}>{c.count.toLocaleString("ko-KR")}건</td>)}</tr>)}</tbody>
      </table></div>
    </details>
    <h3>분석 데이터 최신성</h3>
    <Analytics data={data.analytics} />
    <p className="small">P1 백그라운드 작업 집계: 집계 불가 · 연결된 작업 생산자가 없습니다. VOC·정책 API의 사용 가능 여부를 뜻하지 않습니다.</p>
  </>;
}
function Analytics({ data }: { data: MonitorSummary["analytics"] }) {
  if (data.availability === "UNAVAILABLE") return <p className="notice"><Badge tone="amber">{data.reason === "NO_PUBLISHED_BATCH" ? "미게시" : "선택 팀 데이터 없음"}</Badge>
    {data.reason === "NO_PUBLISHED_BATCH" ? " 공개된 분석 배치가 없습니다." : " 공개 배치에 선택한 팀 조합의 분석 데이터가 없습니다."} 최신성을 판단할 수 없습니다.</p>;
  const m = data.meta;
  return <>
    <p><Badge tone={m.stale ? "amber" : "green"}>{m.stale ? "오래된 데이터" : "서버 최신성 기준 충족"}</Badge>
      {" "}<Badge>{m.source === "LOCAL_SYNTHETIC" ? "합성 분석 데이터" : "FABRIC 출처 (서비스 선언)"}</Badge></p>
    <dl className="monitoring-timestamps">
      <div><dt>원천 데이터 기준</dt><dd><DataTimestamp value={m.source_as_of} label="" /></dd></div>
      <div><dt>생성 시각</dt><dd><DataTimestamp value={m.generated_at} label="" /></dd></div>
      <div><dt>게시 시각</dt><dd><DataTimestamp value={m.published_at} label="" /></dd></div>
      <div><dt>분석 기간 종료</dt><dd><DataTimestamp value={m.window_end} label="" /></dd></div>
    </dl>
    <p className="small monitoring-id">배치 ID: {m.batch_id}</p>
    <p className="notice">원천 출처는 서비스가 선언한 값입니다. 실제 Fabric 연결은 미관측이며 별도로 검증되지 않았습니다.</p>
  </>;
}
function AiStatus({ data }: { data: AiCalls }) {
  return <>
    <p><Badge tone="amber">미관측</Badge> 계측된 공급자가 없어 AI 호출 상태를 확인할 수 없습니다.</p>
    <DataTimestamp value={data.as_of} label="AI 조회 기준" />
    <p><DataTimestamp value={data.from} label="관측 기간 시작" /> · <DataTimestamp value={data.to} label="종료" /></p>
    <dl className="monitoring-ai-values">{["호출 시도", "실패 시도", "재시도", "에러율"].map(label => <div key={label}><dt>{label}</dt><dd>미관측</dd></div>)}</dl>
    <p className="small">관측되지 않은 값은 0건 또는 0%가 아닙니다. 서버 기본 관측 기간은 최근 24시간이며, 작업 종류·상태 필터는 적용되지 않습니다.</p>
    <p className="small">미관측 구성요소: {data.unobserved_components.join(", ")}</p>
  </>;
}
function Jobs({ data, hasCursor }: { data: JobPage; hasCursor: boolean }) {
  return <>
    <DataTimestamp value={data.as_of} label="목록 조회 기준" />
    <p className="small">이 페이지 {data.items.length}건 · 최신 갱신 순. 전체 건수는 API에서 제공하지 않습니다. 페이지마다 독립적으로 조회됩니다.</p>
    {!data.items.length ? <p role="status" className="notice">{hasCursor ? "이 페이지는 정상 조회된 0건입니다. 첫 페이지에서 다시 조회할 수 있습니다." : "선택한 조건에 해당하는 작업이 없습니다. 정상 조회된 0건입니다."}</p>
      : <div className="table-scroll" tabIndex={0} role="region" aria-label="작업 목록"><table>
        <caption className="sr-only">선택한 팀·작업 종류·상태의 작업 목록</caption>
        <thead><tr><th scope="col">작업 / 문의 ID</th><th scope="col">종류 / 상태</th><th scope="col">유효 범위 / 출처</th><th scope="col">시도 / 오류 코드</th><th scope="col">시각 (KST)</th></tr></thead>
        <tbody>{data.items.map(j => <tr key={j.job_id}>
          <td className="monitoring-id"><strong>{j.job_id}</strong><small>문의 {j.ticket_id}</small></td>
          <td>{kindLabel(j.job_kind)}<small><Badge tone={j.status === "FAILED" ? "red" : j.status === "SUCCEEDED" ? "green" : "neutral"}>{statusLabels[j.status]}</Badge></small></td>
          <td><Badge tone={j.scope_status === "SUPERSEDED" ? "amber" : "neutral"}>{j.scope_status === "CURRENT" ? "현재 회차·버전" : "이전 회차·버전"}</Badge><small>회차 {j.cycle_no} · 기대 버전 {j.expected_ticket_version}</small><small>{j.data_origin === "SYNTHETIC" ? "합성 작업" : `출처: ${j.data_origin}`}</small></td>
          <td>{j.attempt}회<small>{j.error_code ?? "오류 코드 없음"}</small></td>
          <td><DataTimestamp value={j.updated_at} label="갱신" /><small><DataTimestamp value={j.next_attempt_at} label="다음 시도" /></small><small>{j.lease_expires_at ? <DataTimestamp value={j.lease_expires_at} label="임대 만료" /> : "임대 시각 없음"}</small></td>
        </tr>)}</tbody>
      </table></div>}
  </>;
}
export function MonitoringPage() {
  const auth = useAuthManager(), { session, epoch } = useAuth();
  const client = useMemo(() => createMonitoringClient(auth), [auth]);
  const [filters, setFilters] = useState({ team: "", kind: "" as "" | JobKind, status: "" as "" | JobStatus, limit: 20 });
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [revision, setRevision] = useState(0);
  const cursor = cursors[cursors.length - 1];
  const allowedKey = session!.allowedTeamIds.join(",");
  const teams = useMemo(() => filters.team ? [filters.team] : allowedKey.split(","), [allowedKey, filters.team]);
  const summaryKey = JSON.stringify([epoch, teams, filters.kind, revision]);
  const aiKey = JSON.stringify([epoch, teams, revision]);
  const jobsKey = JSON.stringify([summaryKey, filters.status, filters.limit, cursor]);
  const loadSummary = useCallback((signal: AbortSignal) => client.summary(filters.team, teams, filters.kind || undefined, signal), [client, filters.team, filters.kind, teams, revision]);
  const loadAi = useCallback((signal: AbortSignal) => client.aiCalls(filters.team, teams, signal), [client, filters.team, teams, revision]);
  const loadJobs = useCallback((signal: AbortSignal) => client.jobs(filters.team, teams, filters.kind || undefined, filters.status || undefined, filters.limit, cursor, signal), [client, filters.team, filters.kind, filters.status, filters.limit, teams, cursor, revision]);
  const summary = useResource(summaryKey, loadSummary), ai = useResource(aiKey, loadAi), jobs = useResource(jobsKey, loadJobs);
  const refresh = () => { setCursors([null]); setRevision(r => r + 1); };
  const change = (patch: Partial<typeof filters>) => { setFilters(f => ({ ...f, ...patch })); setCursors([null]); };
  return <div className="monitoring-page">
    <PageHeading title="운영 모니터링" subtitle="허용 팀의 백엔드 작업과 관측 범위를 확인합니다. 운영 홈 KPI와는 별도 집계입니다." action={<button className="button secondary" onClick={refresh}>전체 새로고침</button>} />
    <section className="card monitoring-filters" aria-label="모니터링 필터">
      <label>팀 범위<select value={filters.team} onChange={e => change({ team: e.target.value })}><option value="">모든 허용 팀 ({session!.allowedTeamIds.length}개)</option>{session!.allowedTeamIds.map(id => <option key={id} value={id}>팀 {id}</option>)}</select></label>
      <label>작업 종류<select value={filters.kind} onChange={e => change({ kind: e.target.value as typeof filters.kind })}><option value="">전체 종류</option><option value="AUTO">자동응답</option><option value="HANDOFF">상담 인계</option></select></label>
      <label>상태 (작업 목록만)<select value={filters.status} onChange={e => change({ status: e.target.value as typeof filters.status })}><option value="">전체 상태</option>{jobStatuses.map(s => <option key={s} value={s}>{statusLabels[s]}</option>)}</select></label>
      <label>페이지당 작업<select value={filters.limit} onChange={e => change({ limit: Number(e.target.value) })}>{[20, 50, 100].map(n => <option value={n} key={n}>{n}건</option>)}</select></label>
      <p className="small">팀 범위는 모든 조회에, 작업 종류는 집계·목록에 적용됩니다. 팀 이름 조회 API가 없어 서버에서 허용한 UUID로 표시합니다.</p>
    </section>
    <ResultPanel title="작업 현황" resource={summary} retry={refresh}>{data => <Summary data={data} />}</ResultPanel>
    <ResultPanel title="AI 호출 상태" resource={ai} retry={refresh}>{data => <AiStatus data={data} />}</ResultPanel>
    <ResultPanel title="작업 이력" resource={jobs} retry={refresh}>{data => <Jobs data={data} hasCursor={cursor !== null} />}</ResultPanel>
    <nav className="monitoring-pagination" aria-label="작업 페이지 탐색">
      <button className="button secondary" disabled={cursors.length === 1} onClick={() => setCursors(c => c.slice(0, -1))}>이전 페이지</button>
      <span aria-live="polite">{cursors.length}페이지</span>
      <button className="button secondary" disabled={jobs.status !== "ready" || !jobs.data.data.next_cursor || cursors.includes(jobs.data.data.next_cursor)} onClick={() => {
        if (jobs.status === "ready" && jobs.data.data.next_cursor) setCursors(c => [...c, jobs.data.data.next_cursor]);
      }}>다음 페이지</button>
      <button className="button secondary" onClick={refresh}>첫 페이지 새로 조회</button>
    </nav>
  </div>;
}
