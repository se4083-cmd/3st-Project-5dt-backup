import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api";
import { useAuth, useAuthManager } from "../../auth/AuthProvider";
import { hasCapability } from "../../auth/session";
import { AsyncState, Badge, DataTimestamp, PageHeading } from "../../components";
import { useResource } from "../../useResource";
import { useWrites, useWriteRefresh, WriteResult } from "../workspace/widgets";
import { uuid } from "../workspace/validate";
import { createVOCClient } from "./api";
import { Evidence } from "./Evidence";
import type { GenerateBody, ReviewBody, VOC } from "./contracts";
export const statusNames = { PENDING_REVIEW: "검토 대기", APPROVED: "승인", REJECTED: "반려", INSUFFICIENT_DATA: "데이터 부족", FAILED: "생성 실패" };
function Status({ value }: { value: VOC["status"] }) { return <Badge tone={value === "APPROVED" ? "green" : value === "FAILED" || value === "REJECTED" ? "red" : "amber"}>{statusNames[value]} · {value}</Badge>; }
export function VOCList() {
  const auth = useAuthManager(), { session, epoch } = useAuth(), { store, entries } = useWrites(), client = useMemo(() => createVOCClient(auth), [auth]);
  const slot = "voc:generate", entry = entries[slot];
  const [teams, setTeams] = useState(session!.allowedTeamIds.length <= 8 ? session!.allowedTeamIds : []), [product, setProduct] = useState("");
  const [revision, setRevision] = useState(0), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const body = entry ? entry.body as GenerateBody : { team_ids: teams, product_id: product }, cursor = cursors.at(-1)!;
  const refresh = useCallback(() => { setRevision(n => n + 1); setCursors([null]); }, []);
  useWriteRefresh(entry, refresh);
  const historyLoad = useCallback((signal: AbortSignal) => client.history(cursor, signal), [client, cursor, revision]);
  const history = useResource(JSON.stringify([epoch, cursor, revision]), historyLoad);
  const canGenerate = hasCapability(session, "P1_VOC_GENERATE");
  const productsLoad = useCallback(async (signal: AbortSignal) => canGenerate && body.team_ids.length ? client.products(body.team_ids, signal) : null, [client, canGenerate, body.team_ids, revision]);
  const products = useResource(JSON.stringify([epoch, body.team_ids, revision]), productsLoad);
  const available = products.status === "ready" && products.data?.data.items.some(i => i.product_id === body.product_id);
  const disabled = history.status === "error" && ["P1_DISABLED", "VOC_DISABLED", "VOC_CONFIGURATION_INVALID"].includes(history.error.code);
  const reset = () => { setTeams([...body.team_ids]); setProduct(""); store.reset(slot); refresh(); };
  return <div className="p1-workspace"><PageHeading title="VOC 개선 제안" subtitle="게시된 근거로 검토용 제안을 생성하고 이력을 확인합니다." action={<button className="button secondary" onClick={refresh}>이력 새로고침</button>} />
    {disabled ? <p className="notice">서버가 VOC 기능을 제공하지 않아 생성을 차단했습니다.</p> : canGenerate ? <section className="card" aria-label="VOC 생성"><h2>개선 제안 생성</h2><p className="notice">분석 기간·provider는 서버가 결정합니다. 생성된 문구는 가설이며 승인 자체로 운영 정책·자동응답을 변경하지 않습니다.</p>
      <form className="p1-form" aria-label="VOC 생성" onSubmit={e => { e.preventDefault(); if (!entry && available) void store.start(slot, { ...body, team_ids: [...body.team_ids].sort() }, body.team_ids, "P1_VOC_GENERATE", "P1_VOC_READ", async (original, key) => { const r = await client.generate(original, key); return { href: `/p1/voc/${r.data.request_id}`, requestId: r.requestId, replayed: r.idempotencyReplayed, status: r.data.status, reason: r.data.reason_code }; }); }}>
        <fieldset disabled={!!entry}><legend>허용 팀 1–8개</legend><div className="p1-teams">{session!.allowedTeamIds.map(id => <label key={id}><input type="checkbox" checked={body.team_ids.includes(id)} disabled={!body.team_ids.includes(id) && body.team_ids.length >= 8} onChange={() => { setTeams(t => t.includes(id) ? t.filter(i => i !== id) : [...t, id].sort()); setProduct(""); }} />팀 {id}</label>)}</div></fieldset>
        {products.status === "loading" ? <AsyncState kind="loading" /> : products.status === "error" ? <AsyncState kind="error" error={products.error} onRetry={refresh} /> : <>
          {products.data?.data.availability === "UNAVAILABLE" && <p className="notice">상품 근거 목록 미제공: {products.data.data.reason}</p>}
          <label>확인된 상품 UUID<select required disabled={!!entry || !products.data?.data.items.length} value={body.product_id} onChange={e => setProduct(e.target.value)}><option value="">상품 선택</option>{products.data?.data.items.map(p => <option key={p.product_id} value={p.product_id}>{p.product_id} · {p.data_status}</option>)}{entry && body.product_id && !available && <option value={body.product_id}>{body.product_id} · 원래 요청</option>}</select></label>
        </>}
        <p className="small">실제 VOC TOP 10·산정 불가 API에서 확인한 상품만 선택합니다. 전체 상품 검색 API는 없으며 UUID를 임의 입력하지 않습니다.</p><button className="button" disabled={!!entry || !available} type="submit">개선 제안 생성</button>
      </form><WriteResult entry={entry} store={store} slot={slot} reset={reset} />
    </section> : <p className="notice">생성 권한이 없습니다. P1_VOC_GENERATE가 필요합니다.</p>}
    <section className="card" aria-label="VOC 생성 이력"><h2>생성 이력</h2><p className="small">요청의 전체 팀에 대한 현재 권한이 있어야 표시됩니다. API가 제공하지 않는 전체 건수·팀/상태 필터는 만들지 않습니다.</p>
      {history.status === "loading" ? <AsyncState kind="loading" /> : history.status === "error" ? <AsyncState kind="error" error={history.error} onRetry={refresh} /> : <>
        {history.data.data.items.length ? <div className="table-scroll" role="region" aria-label="VOC 이력 표" tabIndex={0}><table><caption className="sr-only">현재 허용 팀의 생성 이력</caption><thead><tr><th scope="col">요청 / 상품</th><th scope="col">상태</th><th scope="col">provider / 근거 출처</th><th scope="col">생성 / revision</th></tr></thead><tbody>{history.data.data.items.map(i => <tr key={i.request_id}><td className="p1-id"><Link to={`/p1/voc/${i.request_id}`}>{i.request_id}</Link><small>{i.product_id}</small></td><td><Status value={i.status} /><small>{i.reason_code}</small></td><td>{i.provider}<small>{i.evidence.meta?.source ?? "근거 미제공"}</small></td><td><DataTimestamp value={i.created_at} label="" /><small>revision {i.revision}</small></td></tr>)}</tbody></table></div> : <p className="notice" role="status">이 페이지의 VOC 이력은 정상 조회된 0건입니다.</p>}
        {history.data.requestId && <p className="small">이력 조회 ID: {history.data.requestId}</p>}
      </>}
      <nav className="p1-actions" aria-label="VOC 이력 페이지"><button className="button secondary" disabled={cursors.length === 1} onClick={() => setCursors(c => c.slice(0, -1))}>이전 이력 페이지</button><span>{cursors.length}페이지</span><button className="button secondary" disabled={history.status !== "ready" || !history.data.data.next_cursor || cursors.includes(history.data.data.next_cursor)} onClick={() => { if (history.status === "ready" && history.data.data.next_cursor) setCursors(c => [...c, history.data.data.next_cursor]); }}>다음 이력 페이지</button></nav>
    </section>
  </div>;
}
export function VOCDetailRoute() {
  const { requestId } = useParams(); let id: string;
  try { id = uuid(requestId); } catch { return <AsyncState kind="error" error={new ApiError(404, "NOT_FOUND")} />; }
  return <VOCDetail key={id} id={id} />;
}
function VOCDetail({ id }: { id: string }) {
  const auth = useAuthManager(), { session, epoch } = useAuth(), { store, entries } = useWrites(), client = useMemo(() => createVOCClient(auth), [auth]);
  const slot = `voc:review:${id}`, entry = entries[slot];
  const [revision, setRevision] = useState(0), [decision, setDecision] = useState<ReviewBody["decision"]>("APPROVED"), [reason, setReason] = useState("");
  const refresh = useCallback(() => setRevision(n => n + 1), []); useWriteRefresh(entry, refresh);
  const load = useCallback((signal: AbortSignal) => client.detail(id, signal), [client, id, revision]);
  const detail = useResource(JSON.stringify([epoch, id, revision]), load);
  const pending = detail.status === "ready" && detail.data.data.status === "PENDING_REVIEW";
  const stored = entry?.body as ReviewBody | undefined;
  return <div className="p1-workspace"><PageHeading title="VOC 제안 상세" subtitle="저장된 제안·생성 근거와 관리자 검토 이력입니다." action={<button className="button secondary" onClick={refresh}>상세 새로고침</button>} /><Link to="/p1/voc">생성·이력으로</Link>
    <WriteResult entry={entry} store={store} slot={slot} reset={pending && hasCapability(session, "P1_VOC_REVIEW") ? () => { store.reset(slot); setReason(""); } : undefined} />
    {detail.status === "loading" ? <AsyncState kind="loading" /> : detail.status === "error" ? <AsyncState kind="error" error={detail.error} onRetry={refresh} /> : <>
      <section className="card" aria-label="VOC 제안 상세"><p><Status value={detail.data.data.status} /> <Badge>{detail.data.data.provider}</Badge></p><p className="small">MOCK는 합성 제안, AZURE_OPENAI는 서버 선언 공급자입니다. 실제 외부 연결 검증을 뜻하지 않습니다.</p>
        <dl className="p1-facts">{[["요청 UUID", id], ["상품 UUID", detail.data.data.product_id], ["팀 UUID", detail.data.data.team_ids.join(", ")], ["revision", detail.data.data.revision], ["생성자 UUID", detail.data.data.created_by], ["모델 배포명", detail.data.data.model_deployment ?? "미제공"]].map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl><DataTimestamp value={detail.data.data.created_at} label="생성" /><p className="small">조회 요청 ID: {detail.data.requestId ?? "미제공"}</p>
        {detail.data.data.reason_code && <p className="notice">{statusNames[detail.data.data.status]} · 사유 코드: {detail.data.data.reason_code}</p>}<h2>개선 제안</h2><p className="notice">검토용 가설입니다. 승인만으로 정책·RAG·규칙을 변경하거나 고객에게 발송하지 않습니다.</p>
        {detail.data.data.proposal ? <ol>{detail.data.data.proposal.recommendations.map((r, i) => <li key={i}><h3>{r.title}</h3><p className="p1-prose">{r.action}</p><p className="small">인용 근거: {r.evidence_ids.join(", ")}</p></li>)}</ol> : <p>생성된 제안이 없습니다. 부족·실패 사유를 확인하세요.</p>}
      </section><Evidence data={detail.data.data} />
      <section className="card" aria-label="VOC 검토"><h2>관리자 검토</h2>{!hasCapability(session, "P1_VOC_REVIEW") ? <p>검토 권한이 없습니다. P1_VOC_REVIEW가 필요합니다.</p> : !pending ? <p>검토 대기 상태에서만 검토할 수 있습니다.</p> : <form className="p1-form" aria-label="VOC 검토" onSubmit={e => { e.preventDefault(); if (!entry && reason.trim() && [...reason].length <= 500) void store.start(slot, { expected_revision: detail.data.data.revision, decision, reason: reason.trim() }, detail.data.data.team_ids, "P1_VOC_REVIEW", "P1_VOC_READ", async (body, key) => { const r = await client.review(id, body, key); return { href: `/p1/voc/${id}`, requestId: r.requestId, replayed: r.idempotencyReplayed, status: r.data.status }; }); }}>
        <p>검토 대상 revision: {detail.data.data.revision}</p><label>검토 결정<select disabled={!!entry} value={stored?.decision ?? decision} onChange={e => setDecision(e.target.value as ReviewBody["decision"])}><option value="APPROVED">승인</option><option value="REJECTED">반려</option></select></label><label>검토 사유<textarea required disabled={!!entry} value={stored?.reason ?? reason} onChange={e => setReason(e.target.value)} /></label><p className="small">공백 아닌 사유 최대500자</p><button className="button" type="submit" disabled={!!entry || !reason.trim() || [...reason].length > 500}>검토 제출</button>
      </form>}<h3>검토 이력</h3>{detail.data.data.reviews.length ? <ol>{detail.data.data.reviews.map(r => <li key={r.review_id}><strong>{r.decision === "APPROVED" ? "승인" : "반려"}</strong><p className="p1-prose">{r.reason}</p><p className="small p1-id">검토자 UUID: {r.reviewed_by}</p><DataTimestamp value={r.created_at} label="검토" /></li>)}</ol> : <p>저장된 검토 이력이 없습니다.</p>}</section>
    </>}
  </div>;
}
