import { useCallback, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "./api";
import { can, kst, type Session } from "./domain";
import { AsyncState, Badge, DataTimestamp, PageHeading } from "./components";
import { useResource } from "./useResource";
import type { OperationsClient, VocList } from "./operations";

type Props = { client: OperationsClient; session: Session; resourceKey: string };
const reasons = ["", "UNASSIGNED", "AUTO_FAILED", "ROUTING_FAILED", "HUMAN_REQUEST"] as const;
const reasonLabel: Record<string, string> = {
  UNASSIGNED: "유효 배정 없음", AUTO_FAILED: "자동 처리 실패",
  ROUTING_FAILED: "경로 지정 실패", HUMAN_REQUEST: "사람 연결 요청",
};
const stateLabel: Record<string, string> = {
  PAUSED: "자동 처리 일시 중지", RECLAIM_REQUIRED: "새 작업 인수 필요",
  HUMAN_REVIEW_REQUIRED: "사람 검토 필요", CONTROL_UNAVAILABLE: "제어 상태 확인 불가",
  READY: "자동 처리 가능", NOT_APPLICABLE: "자동 처리 대상 아님",
};
const stageLabel: Record<string, string> = {
  RECEIVED: "접수", PROCESSING: "자동 처리 중", NEEDS_INFORMATION: "추가 정보 필요",
  WAITING_FOR_SUPPORT: "상담사 연결 대기", IN_SUPPORT: "상담사 처리 중",
  FOLLOWUP: "후속 확인", COMPLETED: "완료", CANCELLED: "취소",
};
const dataLabel: Record<string, string> = {
  ELIGIBLE: "점수 산정", LOW_SAMPLE: "표본 부족", DATA_MISSING: "자료 누락",
  QUALITY_BLOCKED: "품질 검증 보류", SYNTHETIC_ONLY: "합성 기록만 있음",
  RECORDED_FACTS: "기록된 사실", MISSING: "기록 없음",
  INSUFFICIENT_MATERIAL: "평가 자료 부족", MATERIAL_CHANGED: "자료 변경",
  RECORDED_MATERIAL: "기록 자료",
};
const workStateLabel: Record<string, string> = {
  REVIEW: "검토 대기", WORKING: "내가 처리 중",
  FOLLOWUP_PENDING: "후속 대기", AI_RUNNING: "AI 안내 진행",
};
function PageError({ error }: { error: ApiError }) {
  return <AsyncState kind="error" error={error} />;
}
function SourceNotice({ data }: { data: VocList }) {
  if (data.availability === "UNAVAILABLE")
    return <p className="notice" role="status">게시된 분석 결과가 없습니다: {data.reason}. 0건이나 0점으로 해석하지 않습니다.</p>;
  return (
    <div className="data-meta">
      <Badge tone={data.meta!.source === "LOCAL_SYNTHETIC" ? "amber" : "purple"}>
        {data.meta!.source === "LOCAL_SYNTHETIC" ? "합성 분석" : "서비스 선언 데이터"}
      </Badge>
      {data.meta!.stale && <Badge tone="amber">이전 게시 결과</Badge>}
      <span>배치 {data.meta!.batch_id}</span>
      <DataTimestamp value={data.meta!.source_as_of} label="원천 기준" />
    </div>
  );
}
export function InquiriesPage({ client, session, resourceKey }: Props) {
  const [query, setQuery] = useSearchParams();
  const scope = query.get("queue_scope") ?? "ROUTED";
  const reason = query.get("reason") ?? "";
  const cursor = query.get("cursor") ?? "";
  const workState = query.get("state") ?? "";
  const valid = (scope === "ROUTED" || scope === "UNROUTED") &&
    reasons.includes(reason as (typeof reasons)[number]) &&
    (!workState || workState in workStateLabel);
  const load = useCallback((signal: AbortSignal) => {
    if (!valid) return Promise.reject(new ApiError(422, "INVALID_FILTER"));
    if (scope === "UNROUTED" && !can(session, "UNROUTED_QUEUE_READ"))
      return Promise.reject(new ApiError(403, "FORBIDDEN"));
    return client.getQueue(scope as "ROUTED" | "UNROUTED", reason, cursor, signal);
  }, [client, scope, reason, cursor, valid, session]);
  const result = useResource(`queue:${resourceKey}:${scope}:${reason}:${cursor}`, load);
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(query);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("cursor");
    setQuery(next);
  };
  return (
    <>
      <PageHeading title="문의 예외 큐" subtitle="현재 경로·팀 권한 안에서 배정과 자동 처리 예외를 확인합니다." />
      {workState && workState !== "REVIEW" && <p className="notice">
        운영 홈의 ‘{workStateLabel[workState]}’는 업무량 분류입니다. 이 화면의 예외 큐와 같은 집합이 아니므로 해당 건수를 필터 결과로 사용하지 않습니다.
      </p>}
      <div className="filter-bar">
        <label>큐 범위
          <select value={scope} onChange={(e) => update("queue_scope", e.target.value)}>
            <option value="ROUTED">허용 팀 경로</option>
            {can(session, "UNROUTED_QUEUE_READ") && <option value="UNROUTED">미라우팅</option>}
          </select>
        </label>
        <label>사유
          <select value={reason} onChange={(e) => update("reason", e.target.value)}>
            <option value="">전체 사유</option>
            {reasons.slice(1).map((x) => <option value={x} key={x}>{reasonLabel[x]}</option>)}
          </select>
        </label>
      </div>
      {!valid ? <PageError error={new ApiError(422, "INVALID_FILTER")} /> :
        scope === "UNROUTED" && !can(session, "UNROUTED_QUEUE_READ") ?
          <PageError error={new ApiError(403, "FORBIDDEN")} /> :
          result.status === "loading" ? <AsyncState kind="loading" /> :
          result.status === "error" ? <PageError error={result.error} /> :
          <>
            <div className="data-meta"><Badge tone="purple">{result.data.total}건</Badge>
              <DataTimestamp value={result.data.as_of} />
              <span>목록은 현재 권한에 따라 매번 다시 조회됩니다.</span>
            </div>
            {result.data.total === 0 ? <AsyncState kind="empty" /> :
              <section className="card">
                <div className="card-heading"><h2>처리할 예외</h2><span>페이지 {result.data.items.length}건</span></div>
                <div className="table-scroll" tabIndex={0} role="region" aria-label="문의 예외 큐">
                  <table><thead><tr><th>문의</th><th>사유</th><th>현재 단계</th><th>자동 처리</th><th>대기</th></tr></thead>
                    <tbody>{result.data.items.map((item) =>
                      <tr key={item.ticket_id}>
                        <td><Link className="ticket-link" to={`/inquiries/${encodeURIComponent(item.ticket_id)}`}>{item.ticket_id} →</Link></td>
                        <td>{reasonLabel[item.reason_code] ?? item.reason_code}</td>
                        <td>{stageLabel[item.stage] ?? item.stage}</td>
                        <td>{stateLabel[item.automatic_state] ?? item.automatic_state}</td>
                        <td>{Math.ceil(item.waiting_seconds / 60)}분</td>
                      </tr>)}</tbody>
                  </table>
                </div>
              </section>}
            {result.data.next_cursor && <button className="button secondary" onClick={() => {
              const next = new URLSearchParams(query);
              next.set("cursor", result.data.next_cursor!);
              setQuery(next);
            }}>다음 페이지</button>}
          </>}
      <p className="small muted">큐 노출은 문의 원문·고객 360 접근 권한을 부여하지 않습니다. 상세에서 별도 검사를 받습니다.</p>
    </>
  );
}
export function InquiryDetailPage({ client, resourceKey }: Props) {
  const { id = "" } = useParams();
  const load = useCallback((signal: AbortSignal) => client.getStaffDetail(id, signal), [client, id]);
  const result = useResource(`detail:${resourceKey}:${id}`, load);
  return <>
    <PageHeading title="문의 근거 확인" subtitle="현재 회차의 기록된 사실을 확인합니다. 이 화면은 실행 승인이나 고객 발송을 수행하지 않습니다." />
    <Link className="text-link" to="/inquiries">← 예외 큐</Link>
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      <div className="panel-grid">
        <section className="card">
          <div className="card-heading"><h2>{result.data.ticket_id}</h2><Badge tone="purple">회차 {result.data.cycle_no}</Badge></div>
          <dl className="fact-list">
            <div><dt>문의 revision</dt><dd>{result.data.revision}</dd></div>
            <div><dt>자료 상태</dt><dd>{dataLabel[result.data.material_status] ?? result.data.material_status}</dd></div>
            <div><dt>기준 시각</dt><dd>{kst(result.data.as_of)} KST</dd></div>
          </dl>
          <p className="notice">고객 원문·초안 본문은 이 내부 근거 API에 포함되지 않습니다.</p>
          <Link className="text-link" to={`/customers/${result.data.customer_ref}/360`}>허용된 고객 360 보기 →</Link>
        </section>
        <section className="card">
          <div className="card-heading"><h2>AI 제안 근거</h2><Badge tone="amber">표시용 사실</Badge></div>
          {result.data.current_proposals.length === 0 ? <p className="notice">현재 회차에 기록된 제안이 없습니다.</p> :
            result.data.current_proposals.map((p) => <div className="mini-row" key={p.suggestion_id}>
              <strong>{p.record_state}</strong><span>근거 {p.evidence_state}</span>
              {p.synthetic && <Badge tone="amber">합성 기록</Badge>}
              <small>승인 기록 {p.approvals.length}건 · 실행 권한 없음</small>
            </div>)}
          <p className="small muted">CURRENT_RECORDED도 실행 승인 판정이 아닙니다. 승인·발송은 별도 계약과 서버 검사 이후 연결합니다.</p>
        </section>
      </div>}
  </>;
}
export function Customer360Page({ client, resourceKey }: Props) {
  const { id = "" } = useParams();
  const load = useCallback((signal: AbortSignal) => client.getCustomer360(id, signal), [client, id]);
  const result = useResource(`customer360:${resourceKey}:${id}`, load);
  return <>
    <PageHeading title="고객 360" subtitle="현재 담당·팀 권한으로 볼 수 있는 문의와 후속만 표시합니다." />
    <Link className="text-link" to="/inquiries">← 문의 예외 큐</Link>
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      <div className="panel-grid">
        <section className="card">
          <div className="card-heading"><h2>허용된 이력</h2><Badge tone="purple">{result.data.scope_policy}</Badge></div>
          <dl className="fact-list">
            <div><dt>문의</dt><dd>{result.data.total_ticket_count}건</dd></div>
            <div><dt>미해결</dt><dd>{result.data.unresolved_ticket_count}건</dd></div>
            <div><dt>재문의</dt><dd>{result.data.reopened_ticket_count}건</dd></div>
            <div><dt>후속 업무</dt><dd>{result.data.followup_count}건</dd></div>
          </dl>
          <DataTimestamp value={result.data.as_of} />
          <p className="notice">최근 문의는 일부만 제공됩니다. 수치를 고객 전체 이력으로 해석하지 않습니다.</p>
        </section>
        <section className="card">
          <div className="card-heading"><h2>정형 사실</h2><Badge tone="amber">AI 요약 아님</Badge></div>
          <div className="item-list">{result.data.facts.map((fact, i) => <div className="mini-row" key={i}>{fact}</div>)}</div>
          <p className="small muted">summary_contract: {result.data.summary_contract.status}</p>
          <h2>최근 허용 문의</h2>
          <div className="item-list">{result.data.recent_tickets.map((t) => <div className="mini-row" key={t.ticket_id}>
            <strong>{t.ticket_id}</strong><span>{stageLabel[t.stage] ?? t.stage}</span>
          </div>)}</div>
        </section>
      </div>}
  </>;
}
export function FollowupsPage({ client, resourceKey }: Props) {
  const [query, setQuery] = useSearchParams();
  const status = query.get("status") ?? "";
  const cursor = query.get("cursor") ?? "";
  const valid = !status || ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"].includes(status);
  const load = useCallback((signal: AbortSignal) => client.getFollowups(status, cursor, signal), [client, status, cursor]);
  const result = useResource(`followups:${resourceKey}:${status}:${cursor}`, load);
  return <>
    <PageHeading title="후속 관리" subtitle="문의와 제품 개선 업무를 별도 단위로 추적합니다." />
    <div className="filter-bar"><label>상태
      <select value={status} onChange={(e) => setQuery(e.target.value ? { status: e.target.value } : {})}>
        <option value="">전체</option><option value="OPEN">예정</option><option value="IN_PROGRESS">진행</option>
        <option value="DONE">완료</option><option value="CANCELLED">취소</option>
      </select></label></div>
    {!valid ? <PageError error={new ApiError(422, "INVALID_FILTER")} /> :
      result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      result.data.items.length === 0 ? <p className="notice" role="status">현재 조건에서 조회된 후속 업무가 없습니다.</p> :
      <section className="card"><div className="card-heading"><h2>후속 업무</h2><span>현재 페이지 {result.data.items.length}건</span></div>
        <div className="item-list">{result.data.items.map((item) => <article className="item-card" key={item.action_id}>
          <div><strong>{item.kind}</strong> <Badge tone={item.needs_handover ? "amber" : "purple"}>{item.needs_handover ? "인수 필요" : item.status}</Badge></div>
          <p>{item.ticket_id ? `문의 ${item.ticket_id}` : `제품 ${item.product_id}`} · 담당 {item.owner_user_id ?? "미지정"}</p>
          <p>기한 {item.due_at ? `${kst(item.due_at)} KST` : "미설정"} · 후속 revision {item.revision}</p>
          {item.public_note && <p>공개 약속: {item.public_note}</p>}
          {item.internal_note && <p className="muted">내부 메모: {item.internal_note}</p>}
        </article>)}</div>
      </section>}
    {result.status === "ready" && result.data.next_cursor && <button className="button secondary" onClick={() => setQuery({ ...(status ? { status } : {}), cursor: result.data.next_cursor! })}>다음 페이지</button>}
    <p className="small muted">완료된 후속 업무만으로 문의가 해결 완료된 것은 아닙니다. 변경 기능은 revision 충돌 처리를 포함해 연결합니다.</p>
  </>;
}
function VocImprovementsPanel({ client, resourceKey }: Props) {
  const [cursor, setCursor] = useState("");
  const load = useCallback((signal: AbortSignal) => client.getVocImprovements(cursor, signal), [client, cursor]);
  const result = useResource(`improvements:${resourceKey}:${cursor}`, load);
  return <section className="card">
    <div className="card-heading"><h2>VOC 개선 조치</h2><Badge tone="purple">후속 업무와 연결</Badge></div>
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      result.data.items.length === 0 ? <p className="notice">현재 권한에서 조회된 개선 조치가 없습니다.</p> :
      <div className="item-list">{result.data.items.map((item) => <div className="item-card" key={item.action_id}>
        <div><strong>제품 {item.product_id}</strong><Badge tone="amber">{item.status}</Badge></div>
        <p>조치 {item.action_id} · 계획 revision {item.current_plan_revision}</p>
        <p>{item.plan_access === "COMPARISON_SCOPE_DENIED" ? "과거 비교 범위 접근 제한" : "계획 조회 가능"}
          {item.plan_refresh_required && " · 계획 재조회 필요"}</p>
        <p>효과: 현재 제공되지 않음 · 전후 비교 연동 전</p>
      </div>)}</div>}
    {result.status === "ready" && result.data.next_cursor && <button className="button secondary" onClick={() => setCursor(result.data.next_cursor!)}>다음 조치</button>}
  </section>;
}
export function ProductsPage({ client, resourceKey, session }: Props) {
  const load = useCallback(async (signal: AbortSignal) => {
    const top = await client.getVocTop(signal);
    const unavailable = top.meta ? await client.getVocUnavailable(top.meta.batch_id, signal) : null;
    if (unavailable?.meta && (unavailable.meta.batch_id !== top.meta?.batch_id ||
        unavailable.meta.scope_key !== top.meta?.scope_key))
      throw new ApiError(0, "INVALID_RESPONSE");
    return { top, unavailable };
  }, [client]);
  const result = useResource(`voc:${resourceKey}`, load);
  return <>
    <PageHeading title="제품·VOC" subtitle="점수는 관리 우선순위입니다. 상품 불량률이나 결함 확정으로 표시하지 않습니다." />
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      <>
        <SourceNotice data={result.data.top} />
        {result.data.top.availability === "AVAILABLE" && <section className="card">
          <div className="card-heading"><h2>VOC TOP 10</h2><span>같은 범위·배치의 제공 순위</span></div>
          {result.data.top.items.length === 0 ? <p className="notice">게시된 범위에 순위 대상이 없습니다.</p> :
            <div className="item-list">{result.data.top.items.map((p) => <Link className="item-card" key={p.product_id}
              to={`/products/${p.product_id}?batch_id=${result.data.top.meta!.batch_id}`}>
              <div><strong>{p.rank}위 · 제품 {p.product_id}</strong><Badge tone="red">{p.score}점</Badge></div>
              <p>주요 이슈 {p.metrics.top_issue ?? "미분류"} · 문의 사례 C {p.metrics.C} · 판매 분모 S {p.metrics.S}</p>
            </Link>)}</div>}
        </section>}
        {result.data.unavailable && <section className="card">
          <div className="card-heading"><h2>점수 산정 불가</h2><Badge tone="amber">0점 아님</Badge></div>
          {result.data.unavailable.items.length === 0 ? <p>산정 불가 항목이 없습니다.</p> :
            <div className="item-list">{result.data.unavailable.items.map((p) => <Link className="item-card" key={p.product_id}
              to={`/products/${p.product_id}?batch_id=${result.data.top.meta!.batch_id}`}>
              <strong>{p.product_id}</strong><p>{dataLabel[p.data_status]} · 사례 {p.metrics.C}건 · 점수 없음</p>
            </Link>)}</div>}
        </section>}
        {can(session, "VOC_IMPROVEMENT_MANAGE") && <VocImprovementsPanel client={client} session={session} resourceKey={resourceKey} />}
        <p className="small muted">기본 상품 카탈로그 API는 아직 없습니다. 이 목록은 게시된 VOC 분석 대상 제품만 보여줍니다.</p>
      </>}
  </>;
}
export function ProductDetailPage({ client, resourceKey }: Props) {
  const { id = "" } = useParams();
  const [query] = useSearchParams();
  const batch = query.get("batch_id") ?? "";
  const load = useCallback((signal: AbortSignal) => client.getProductDetail(id, batch, signal), [client, id, batch]);
  const result = useResource(`product:${resourceKey}:${id}:${batch}`, load);
  return <>
    <PageHeading title="제품 VOC 상세" subtitle="목록에서 선택한 배치를 유지해 근거와 추세를 확인합니다." />
    <Link className="text-link" to="/products">← 제품·VOC 목록</Link>
    {!batch ? <PageError error={new ApiError(422, "INVALID_FILTER")} /> :
      result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      result.data.availability === "UNAVAILABLE" || !result.data.product ?
        <p className="notice">해당 배치의 제품 분석을 제공할 수 없습니다: {result.data.reason}</p> :
        <>
          <SourceNotice data={{ ...result.data, items: [] }} />
          <div className="panel-grid">
            <section className="card">
              <div className="card-heading"><h2>{result.data.product.product_id}</h2>
                <Badge tone={result.data.product.score === null ? "amber" : "red"}>{result.data.product.score === null ? "점수 산정 불가" : `${result.data.product.score}점`}</Badge></div>
              <dl className="fact-list">
                <div><dt>자료 상태</dt><dd>{dataLabel[result.data.product.data_status]}</dd></div>
                <div><dt>주요 이슈</dt><dd>{result.data.product.metrics.top_issue ?? "미분류"}</dd></div>
                <div><dt>사례 C / 판매 분모 S</dt><dd>{result.data.product.metrics.C} / {result.data.product.metrics.S}</dd></div>
                <div><dt>표본 조건 K</dt><dd>{result.data.product.metrics.K}</dd></div>
              </dl>
            </section>
            <section className="card">
              <div className="card-heading"><h2>제공된 일별 추세</h2><span>누락 날짜를 0으로 채우지 않음</span></div>
              {result.data.trend.length === 0 ? <p className="notice">제공된 추세가 없습니다.</p> :
                <div className="item-list">{result.data.trend.map((t) => <div className="mini-row" key={t.day}>
                  <strong>{t.day}</strong><span>사례 {t.episode_count} · 미해결 {t.unresolved_count}</span>
                </div>)}</div>}
            </section>
          </div>
          <p className="notice">VOC 개선 조치의 전후 효과 수치는 Backend A에서 아직 UNAVAILABLE입니다. 완료와 효과 입증을 같은 의미로 표시하지 않습니다.</p>
        </>}
  </>;
}
export function QualityPage({ client, resourceKey }: Props) {
  const [query, setQuery] = useSearchParams();
  const cursor = query.get("cursor") ?? "";
  const load = useCallback((signal: AbortSignal) => client.getQualitySamples(cursor, signal), [client, cursor]);
  const result = useResource(`quality:${resourceKey}:${cursor}`, load);
  return <>
    <PageHeading title="AI 상담 품질" subtitle="수동 표본의 검토 상태를 확인합니다. 전체 AI 정답률로 일반화하지 않습니다." />
    <p className="notice">평가 기준 DEV_QUALITY_V1은 개발 제안입니다. 실제 운영 평가 기준은 팀 합의가 필요합니다.</p>
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      result.data.items.length === 0 ? <p className="notice">현재 권한 범위에서 조회된 표본이 없습니다.</p> :
      <section className="card"><div className="card-heading"><h2>평가 표본</h2><span>현재 페이지 {result.data.items.length}건</span></div>
        <div className="item-list">{result.data.items.map((item) => <Link className="item-card" key={item.sample_id} to={`/quality/${item.sample_id}`}>
          <div><strong>표본 {item.sample_id}</strong><Badge tone={item.status === "VOID" ? "amber" : "purple"}>{item.status}</Badge></div>
          <p>기준 {item.rubric_version} · revision {item.current_revision} · 선택 {kst(item.selected_at)} KST</p>
        </Link>)}</div>
      </section>}
    {result.status === "ready" && result.data.next_cursor && <button className="button secondary" onClick={() => setQuery({ cursor: result.data.next_cursor! })}>다음 페이지</button>}
  </>;
}
export function QualityMaterialPage({ client, resourceKey }: Props) {
  const { id = "" } = useParams();
  const load = useCallback((signal: AbortSignal) => client.getQualityMaterial(id, signal), [client, id]);
  const result = useResource(`quality-material:${resourceKey}:${id}`, load);
  return <>
    <PageHeading title="품질 평가 자료" subtitle="지정된 평가자와 목적 권한을 서버가 다시 검사합니다." />
    <Link className="text-link" to="/quality">← 평가 표본</Link>
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      <div className="panel-grid">
        <section className="card">
          <div className="card-heading"><h2>검토 자료</h2><Badge tone="amber">{dataLabel[result.data.material_state] ?? result.data.material_state}</Badge></div>
          <p><strong>고객 질문</strong></p><p className="notice">{result.data.question ?? "제공되지 않음"}</p>
          <p><strong>AI 응답</strong></p><p className="notice">{result.data.reply ?? "제공되지 않음"}</p>
        </section>
        <section className="card">
          <h2>출처·한계</h2>
          <dl className="fact-list">
            <div><dt>원천</dt><dd>{result.data.origin}</dd></div>
            <div><dt>모델</dt><dd>{result.data.model_version ?? "미기록"}</dd></div>
            <div><dt>프롬프트</dt><dd>{result.data.prompt_version ?? "미기록"}</dd></div>
            <div><dt>기준 시각</dt><dd>{kst(result.data.as_of)} KST</dd></div>
          </dl>
          <p className="notice">패턴 마스킹은 개인정보 제거를 보장하지 않습니다. 평가 자료를 외부로 복사하지 마세요.</p>
        </section>
      </div>}
  </>;
}
export function AutomationPage({ client, resourceKey }: Props) {
  const load = useCallback((signal: AbortSignal) => client.getControl(signal), [client]);
  const result = useResource(`automation:${resourceKey}`, load);
  return <>
    <PageHeading title="자동화 운영" subtitle="서버 제어 상태와 L3 확장 조건을 확인합니다." />
    {result.status === "loading" ? <AsyncState kind="loading" /> :
      result.status === "error" ? <PageError error={result.error} /> :
      <div className="panel-grid">
        <section className="card">
          <div className="card-heading"><h2>현재 제어 상태</h2><Badge tone={result.data.paused ? "amber" : "green"}>{result.data.paused ? "일시 중지" : "운영 중"}</Badge></div>
          <dl className="fact-list">
            <div><dt>사유</dt><dd>{result.data.reason_code}</dd></div>
            <div><dt>제어 revision</dt><dd>{result.data.revision}</dd></div>
            <div><dt>작업 generation</dt><dd>{result.data.generation}</dd></div>
            <div><dt>변경 시각</dt><dd>{kst(result.data.changed_at)} KST</dd></div>
          </dl>
          <p className="notice">중지는 새 자동 작업의 진행을 제한합니다. 이미 완료된 외부 발송을 되돌렸다는 뜻은 아닙니다.</p>
        </section>
        <section className="card">
          <h2>L3 조건부 자동 결정</h2>
          <div className="item-list">
            <div className="mini-row">허용 작업·금액·위험 한도 정책</div>
            <div className="mini-row">근거·버전·외부 실행 결과 기록</div>
            <div className="mini-row">이의 신청·사람 검토·되돌리기 경로</div>
          </div>
          <p className="notice">L3 자동 결정 UI는 설계 범위입니다. 실제 실행·중지·재개 버튼은 권한, revision, 사고 검증을 포함한 쓰기 계약 연결 후 제공합니다.</p>
        </section>
      </div>}
  </>;
}
