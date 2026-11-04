import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, CircleAlert, ClipboardList, Clock3, Inbox, Info, RotateCcw } from "lucide-react";
import { ApiError, operationsApi } from "@/lib/api/client";
import "./product-operations.css";

type Data = Record<string, any>;
export type ProductOperationsLookup = {
  data: Data | null;
  loading: boolean;
  error: string;
  reload: () => void;
};
const operationStatus: Data = {
  OPEN: "접수", REOPENED: "재문의 접수", CLASSIFIED: "유형 확인", VALIDATING: "근거 확인",
  AUTO_READY: "자동 안내 준비", ESCALATED: "상담 대기", ASSIGNED: "상담 중",
  PENDING_APPROVAL: "답변 검토", FOLLOWUP_PENDING: "후속 진행", RESOLVED: "안내 완료",
  IN_PROGRESS: "진행", DONE: "완료", CANCELLED: "취소",
};
const scopeNote = "이 목록은 전체 시연 팀의 현재 업무이며, 선택한 팀 범위의 7일 VOC 집계와 별개입니다.";

function validResult(result: Data, productId: string) {
  const counts = result.counts;
  return result.productId === productId
    && result.source === "SYNTHETIC_OPERATION_LINKS_NOT_ANALYTICS_EPISODES"
    && result.scope === "LOCAL_CURRENT_ALL_DEMO_TEAMS"
    && Number.isInteger(result.revision)
    && Array.isArray(result.tickets) && Array.isArray(result.followups)
    && result.tickets.every((ticket: Data) => typeof ticket.id === "string" && typeof ticket.subject === "string" && typeof ticket.status === "string")
    && result.followups.every((followup: Data) => typeof followup.id === "string" && typeof followup.ticketId === "string" && result.tickets.some((ticket: Data) => ticket.id === followup.ticketId))
    && counts && ["tickets", "openTickets", "followups", "openFollowups"].every(key => Number.isInteger(counts[key]) && counts[key] >= 0)
    && counts.tickets === result.tickets.length && counts.followups === result.followups.length
    && counts.openTickets <= counts.tickets && counts.openFollowups <= counts.followups;
}

/** No count is shown until this exact product's current-work response is verified. */
export function useProductOperations(productId: string, enabled: boolean, revision: number): ProductOperationsLookup {
  const [snapshot, setSnapshot] = useState<{ key: string; loading: boolean; data: Data | null; error: string }>({ key: "", loading: false, data: null, error: "" });
  const [refreshKey, setRefreshKey] = useState(0);
  const reload = useCallback(() => setRefreshKey(key => key + 1), []);
  useEffect(() => {
    if (!enabled) return;
    window.addEventListener("focus", reload);
    return () => window.removeEventListener("focus", reload);
  }, [enabled, reload]);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setSnapshot({ key: productId, loading: true, data: null, error: "" });
    operationsApi.productOperations(productId, controller.signal).then(result => {
      if (!validResult(result, productId)) throw new ApiError("이 제품의 현재 업무 응답을 확인하지 못했습니다.", "INVALID_PRODUCT_OPERATIONS");
      if (!controller.signal.aborted) setSnapshot({ key: productId, loading: false, data: result, error: "" });
    }).catch(error => {
      if (!controller.signal.aborted) setSnapshot({ key: productId, loading: false, data: null, error: error instanceof Error ? error.message : "현재 업무 조회를 완료하지 못했습니다." });
    });
    return () => controller.abort();
  }, [productId, enabled, revision, refreshKey]);
  const current = enabled && snapshot.key === productId ? snapshot : null;
  return { data: current?.data ?? null, loading: enabled && (!current || current.loading), error: current?.error ?? "", reload };
}

function LookupStatus({ lookup }: { lookup: ProductOperationsLookup }) {
  if (lookup.loading) return <div className="product-operation-loading" role="status"><Clock3 size={19}/><p>이 제품의 현재 문의와 후속을 확인하고 있습니다.</p></div>;
  if (lookup.error) return <div className="product-operation-error" role="alert"><CircleAlert size={20}/><p>{lookup.error}</p><button className="btn secondary" onClick={lookup.reload}><RotateCcw size={16}/>업무 다시 조회</button></div>;
  return null;
}

export function ProductOperationsSummary({ lookup, onOpenFollowups, onOpenTicket }: {
  lookup: ProductOperationsLookup;
  onOpenFollowups: () => void;
  onOpenTicket: (ticketId: string) => void;
}) {
  const { data } = lookup;
  return <>
    <div className="card-title"><h2>현재 조치와 연결</h2><span className="badge purple">로컬 업무</span></div>
    <p className="product-operation-label">현재 로컬 업무 · 합성 연결</p>
    <LookupStatus lookup={lookup}/>
    {data && <>
      <dl className="product-operation-counts"><div><dt>관련 문의</dt><dd>{data.counts.tickets}건<small>미완료 {data.counts.openTickets}건</small></dd></div><div><dt>연결된 후속</dt><dd>{data.counts.followups}건<small>미완료 {data.counts.openFollowups}건</small></dd></div></dl>
      <div className="product-operation-actions"><button className="btn primary full" onClick={onOpenFollowups}><ClipboardList size={17}/>제품 후속 보기<ArrowUpRight size={16}/></button></div>
      {data.tickets.length ? <details className="product-linked-tickets" open><summary>관련 문의 {data.tickets.length}건</summary><div>{data.tickets.map((ticket: Data) => <button key={ticket.id} onClick={() => onOpenTicket(ticket.id)} aria-label={`${ticket.id} ${ticket.subject} 문의 열기`}><span><strong>{ticket.subject}</strong><small>{ticket.id} · {operationStatus[ticket.status] ?? ticket.status}</small></span><ArrowUpRight size={16}/></button>)}</div></details> : <p className="product-operation-empty-small">현재 이 제품에 연결된 시연 문의가 없습니다.</p>}
      <button className="text-link product-operation-refresh" onClick={lookup.reload}><RotateCcw size={15}/>현재 업무 다시 조회</button>
    </>}
    <div className="soft-note product-operation-scope"><Info size={17}/><p>{scopeNote}</p></div>
  </>;
}

function dueDate(value: unknown) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return "기한 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) + " KST";
}

export function ProductFollowupsPanel({ lookup, productName, onOpenFollowup, onOpenTicket }: {
  lookup: ProductOperationsLookup;
  productName: string;
  onOpenFollowup: (ticketId: string, followupId: string) => void;
  onOpenTicket: (ticketId: string) => void;
}) {
  const { data } = lookup;
  return <section className="card product-current-followups" aria-label="제품의 현재 후속 업무">
    <div className="card-title"><div><span className="product-operation-label">현재 로컬 업무 · 합성 연결</span><h2>{productName}의 후속</h2></div><button className="icon-button" disabled={lookup.loading} onClick={lookup.reload} aria-label="제품 후속 다시 조회"><RotateCcw size={19}/></button></div>
    <p className="product-followup-scope">{scopeNote}</p>
    <LookupStatus lookup={lookup}/>
    {data && (data.followups.length ? <>
      <div className="product-followup-totals"><ClipboardList size={18}/><span>연결 후속 {data.counts.followups}건 · 미완료 {data.counts.openFollowups}건</span></div>
      <div className="product-current-followup-list">{data.followups.map((followup: Data) => <article key={followup.id}>
        <div className="product-current-followup-title"><div><span>{followup.ticketId}</span><h3>{followup.title}</h3></div><span className={"badge " + (["DONE", "CANCELLED"].includes(followup.status) ? "muted" : "warning")}>{followup.status === "OPEN" ? "등록" : operationStatus[followup.status] ?? followup.status}</span></div>
        <p><Clock3 size={16}/>{dueDate(followup.dueAt)}까지 <span>{followup.blocking ? "필수 후속" : "일반 후속"}</span></p>
        <div className="product-current-followup-buttons"><button className="btn secondary" onClick={() => onOpenFollowup(followup.ticketId, followup.id)}>후속 업무 열기<ArrowUpRight size={16}/></button><button className="text-link" onClick={() => onOpenTicket(followup.ticketId)}>연결 문의 열기<ArrowUpRight size={16}/></button></div>
      </article>)}</div>
    </> : <div className="product-followup-empty"><Inbox size={32}/><h3>연결된 후속이 없습니다</h3><p>현재 서버에서 이 제품에 연결된 후속이 없는 것을 확인했습니다. 필요한 조치는 관련 문의에서 등록할 수 있습니다.</p></div>)}
    <div className="soft-note"><Info size={17}/><p>후속 상태를 변경해도 저장된 분석 배치의 점수와 순위는 그대로 유지됩니다.</p></div>
  </section>;
}
