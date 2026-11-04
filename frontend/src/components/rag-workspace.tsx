import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, CheckCircle2, CircleAlert, Database, FileText, Search, Send, ShieldCheck, Sparkles } from "lucide-react";
import { operationsApi } from "@/lib/api/client";
import { useOperations } from "./operations-context";
import "./rag-workspace.css";

type Data = Record<string, any>;
const initialQueries = [
  { query: "내 문의 답변은 어디서 확인해요?", needsOrder: false },
  { query: "반품 신청은 어떤 순서로 하나요?", needsOrder: true },
  { query: "택배가 지금 어디쯤 왔나요?", needsOrder: true },
  { query: "지금 환불 승인해 주세요.", needsOrder: true },
];
const reasonLabels: Data = {
  HIGH_RISK_ACTION: "사람의 판단이 필요한 요청",
  HUMAN_REQUESTED: "고객의 상담사 연결 요청",
  NO_RELEVANT_POLICY: "질문에 맞는 정책 근거 없음",
  NO_MATCH: "질문에 맞는 정책 근거 없음",
  NO_EVIDENCE: "유효한 근거 없음",
  POLICY_UNAVAILABLE: "유효한 정책 근거 없음",
  CATEGORY_UNKNOWN: "문의 분류 확인 필요",
  UNKNOWN_CATEGORY: "문의 분류 확인 필요",
  NOT_ALLOWLISTED: "자동 안내 범위 밖",
  POLICY_CONFLICT: "정책 간 내용 확인 필요",
  OWNERSHIP_UNVERIFIED: "본인 주문 확인 필요",
  ORDER_REQUIRED: "본인 주문 선택 필요",
  PROMPT_INJECTION: "문의 내용 확인 필요",
  AUTOMATION_STOPPED: "자동 안내 중지",
};

function EvidenceDocument({ document, rank }: { document: Data; rank?: number }) {
  const id = document.documentId ?? document.document_id ?? document.id;
  const hash = document.contentHash ?? document.content_hash ?? document.hash;
  return <article className="rag-document">
    <div className="rag-document-title"><span className="rag-document-icon">{rank ? rank : <FileText size={18}/>}</span><div><strong>{document.title ?? "정책 문서"}</strong><small>버전 {document.version ?? "—"}{document.clauseId ? ` · ${document.clauseId}` : document.clause ? ` · ${document.clause}` : ""}{Number.isFinite(document.score) ? ` · 검색 점수 ${Number(document.score).toFixed(3)}` : ""}</small></div></div>
    {(document.text ?? document.content) && <p className="rag-document-text">{document.text ?? document.content}</p>}
    <details className="rag-document-meta"><summary>문서 식별자·검증 정보</summary><dl><dt>문서 ID</dt><dd>{id ?? "—"}</dd><dt>내용 해시</dt><dd>{hash ?? "—"}</dd><dt>자료 구분</dt><dd>{document.source ?? document.scope ?? "개발용 합성 정책"}</dd>{document.active !== undefined && <><dt>개발 검색 상태</dt><dd>{document.active ? "활성" : "비활성 · 자동 안내 제외"}</dd></>}</dl></details>
  </article>;
}

/** Staff-only evidence, read from the API's stored RAG result. */
export function RagEvidence({ ticket }: { ticket: Data }) {
  const result = ticket.ragResult ?? ticket.rag?.result ?? ticket.rag ?? ticket.evidence?.rag;
  const documents: Data[] = result?.evidence ?? ticket.evidence?.retrievedDocuments ?? [];
  if (!result && !documents.length) return null;
  return <section className="rag-ticket-evidence">
    <div className="op-card-title"><div><h3><BookOpen size={18}/>검색된 문서 근거</h3><p className="op-muted">{result?.mode ?? "RETRIEVAL_TEMPLATE"} · {result?.retrieval?.mode ?? "LOCAL_BM25"}</p></div><span className="badge purple">임시 RAG</span></div>
    {documents.length ? documents.map((document, index) => <EvidenceDocument key={`${document.documentId ?? document.id}-${index}`} document={document} rank={index + 1}/>) : <p className="op-muted">자동 안내에 사용할 문서 근거를 확인하지 못했습니다.</p>}
    {result?.corpusVersion && <p className="op-small op-muted">문서 묶음 버전 {result.corpusVersion}</p>}
  </section>;
}

export function CustomerInquiryForm() {
  const { createRagInquiry, busy, uncertain, customerLoaded, refreshCustomer } = useOperations();
  const [query, setQuery] = useState(initialQueries[0].query);
  const [orders, setOrders] = useState<Data[]>([]);
  const [orderId, setOrderId] = useState("");
  const [ordersError, setOrdersError] = useState("");
  const [sent, setSent] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    operationsApi.orders(controller.signal).then(result => {
      if (!Array.isArray(result.orders)) throw new Error("주문 목록을 확인하지 못했습니다.");
      setOrders(result.orders);
      setOrdersError("");
    }).catch(error => { if (!controller.signal.aborted) setOrdersError(error.message); });
    return () => controller.abort();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || uncertain || !query.trim()) return;
    setSent("");
    if (!customerLoaded && !await refreshCustomer()) return;
    const response = await createRagInquiry(query, orderId || undefined);
    if (response.ticket) {
      setSent(response.ticket.route === "AUTO" && response.ticket.status === "RESOLVED"
        ? "확인된 근거로 안내가 완료되었습니다. 왼쪽 대화에서 답변을 확인하세요."
        : "문의를 접수했습니다. 담당자가 확인할 수 있도록 연결했습니다.");
    }
  }

  return <section className="card rag-customer-form" id="new-inquiry">
    <div className="op-card-title"><div><span className="op-kicker">직접 질문해 보기</span><h2>새 문의 작성</h2></div><MessageIcon/></div>
    <p className="op-muted">입력한 문장을 바탕으로 정책을 찾아 안내하거나 담당자에게 연결합니다.</p>
    <div className="rag-sample-list" aria-label="문의 예문">{initialQueries.map(example => <button key={example.query} type="button" onClick={() => { setQuery(example.query); setOrderId(example.needsOrder ? orders[0]?.id ?? "" : ""); setSent(""); }}>{example.query}</button>)}</div>
    <form onSubmit={submit}>
      <label className="op-field"><span>문의 내용</span><textarea aria-label="새 문의 내용" value={query} onChange={event => { setQuery(event.target.value); setSent(""); }} rows={5} maxLength={10000} required placeholder="예: 반품 신청은 어떤 순서로 하나요?"/><small className="rag-input-count">{query.length.toLocaleString("ko-KR")} / 10,000자</small></label>
      <label className="op-field"><span>관련 합성 주문</span><select aria-label="새 문의 관련 주문" value={orderId} onChange={event => setOrderId(event.target.value)}><option value="">주문과 관계없는 문의</option>{orders.map(order => <option key={order.id} value={order.id}>{order.id} · {order.statusLabel ?? order.status}</option>)}</select></label>
      {ordersError && <p className="rag-error" role="alert">{ordersError}</p>}
      <button className="btn primary full" type="submit" disabled={busy || uncertain || !query.trim()}><Send size={17}/>{busy ? "문의를 처리하고 있습니다" : "문의 접수하기"}<ArrowRight size={17}/></button>
      <p className="op-small op-muted rag-form-note">합성 문의를 연습하는 공간입니다. 이름·연락처 등 개인정보는 입력하지 마세요.</p>
    </form>
    {sent && <p className="rag-sent" role="status"><CheckCircle2 size={18}/>{sent}</p>}
  </section>;
}

function MessageIcon() { return <Sparkles className="rag-accent" size={24}/>; }

export function RagWorkspace() {
  const [knowledge, setKnowledge] = useState<Data | null>(null);
  const [orders, setOrders] = useState<Data[]>([]);
  const [query, setQuery] = useState(initialQueries[0].query);
  const [orderId, setOrderId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.allSettled([operationsApi.knowledge(controller.signal), operationsApi.orders(controller.signal)]).then(results => {
      if (controller.signal.aborted) return;
      const corpus = results[0], ownedOrders = results[1];
      if (corpus.status === "fulfilled" && corpus.value.knowledge) {
        setKnowledge(corpus.value.knowledge);
        setLoadError("");
      } else setLoadError(corpus.status === "rejected" ? corpus.reason.message : "검색 문서 목록을 확인하지 못했습니다.");
      if (ownedOrders.status === "fulfilled" && Array.isArray(ownedOrders.value.orders)) setOrders(ownedOrders.value.orders);
      else if (ownedOrders.status === "rejected") setLoadError(previous => [previous, "합성 주문 목록을 불러오지 못했습니다."].filter(Boolean).join(" "));
    });
    return () => { controller.abort(); epoch.current += 1; };
  }, [reload]);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !query.trim()) return;
    const current = ++epoch.current;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await operationsApi.rag({ query, createTicket: false, ...(orderId ? { orderId } : {}) });
      if (current !== epoch.current) return;
      if (!response.result || !Array.isArray(response.result.evidence)) throw new Error("검색 결과의 근거 형식을 확인하지 못했습니다.");
      setResult(response.result);
    } catch (cause) {
      if (current === epoch.current) setError(cause instanceof Error ? cause.message : "문서 검색을 완료하지 못했습니다.");
    } finally { if (current === epoch.current) setBusy(false); }
  }
  const samples: Data[] = knowledge?.sampleQueries?.length ? knowledge.sampleQueries : initialQueries;
  const hits: Data[] = result?.retrieval?.hits ?? [];
  return <section className="card rag-workspace">
    <div className="op-card-title"><div><span className="op-kicker">검색부터 문안까지 확인하기</span><h2>임시 RAG 작업 공간</h2></div><span className="badge purple"><BookOpen size={15}/> 개발용 정책</span></div>
    <p className="op-muted">질문에 맞는 문서와 조항을 실제로 검색하고, 찾은 근거를 이용해 안내문을 구성합니다.</p>
    {knowledge && <div className="rag-corpus-summary"><span><Database size={17}/><strong>{knowledge.activeCount}</strong>개 활성 / 전체 {knowledge.documentCount}개</span><span>검색 {knowledge.mode}</span><span>문안 {knowledge.generationMode}</span></div>}
    {loadError && <div className="rag-error" role="alert"><CircleAlert size={18}/><p>{loadError}</p><button className="text-link" onClick={() => setReload(value => value + 1)}>다시 연결</button></div>}
    <div className="rag-workspace-grid">
      <form className="rag-query-form" onSubmit={search}>
        <label className="op-field"><span>검색할 문의</span><textarea aria-label="RAG 검증 질문" rows={5} maxLength={10000} value={query} disabled={busy} onChange={event => { setQuery(event.target.value); setResult(null); }} required/><small className="rag-input-count">{query.length.toLocaleString("ko-KR")} / 10,000자</small></label>
        <label className="op-field"><span>본인 합성 주문</span><select aria-label="RAG 검증 주문" disabled={busy} value={orderId} onChange={event => { setOrderId(event.target.value); setResult(null); }}><option value="">주문 선택 없음</option>{orders.map(order => <option key={order.id} value={order.id}>{order.id} · {order.statusLabel ?? order.status}</option>)}</select></label>
        <button type="submit" className="btn primary full" disabled={busy || !query.trim()}><Search size={17}/>{busy ? "문서를 검색하고 있습니다" : "검색·안내문 확인"}</button>
        <div className="rag-sample-list" aria-label="RAG 검증 예문">{samples.map((example, index) => <button key={example.query ?? index} disabled={busy} type="button" onClick={() => { setQuery(example.query); setOrderId(example.needsOrder ? orders[0]?.id ?? "" : ""); setResult(null); }}>{example.query}</button>)}</div>
        <p className="op-small op-muted">여기서는 검색 결과와 문안만 확인합니다. 실제 문의 접수는 고객 화면에서 진행하세요.</p>
      </form>
      <div className="rag-search-result" aria-live="polite" aria-busy={busy}>
        {error ? <div className="rag-error" role="alert"><CircleAlert size={20}/><p>{error}</p></div> : result ? <>
          <div className="rag-result-heading"><span className={"badge " + (result.eligible ? "success" : "warning")}>{result.eligible ? "문서 근거 충족" : "사람 확인 필요"}</span><small>{result.category} · {result.mode}</small></div>
          <p className="op-small op-muted">이 표시는 검색 결과입니다. 최종 자동 안내는 주문·회차·중지 여부를 서버에서 다시 확인합니다.</p>
          {result.reply ? <div className="rag-grounded-reply"><strong>근거로 구성한 안내문</strong><p>{result.reply}</p></div> : <div className="rag-grounded-reply rag-held"><strong>자동 안내문을 만들지 않았습니다</strong><p>확정할 수 있는 근거와 허용 범위를 확인해 사람에게 연결합니다.</p></div>}
          {!!result.reasons?.length && <ul className="rag-reasons">{result.reasons.map((reason: Data, index: number) => <li key={`${reason.code}-${index}`}><CircleAlert size={16}/><span>{reasonLabels[reason.code] ?? reason.detail ?? reason.code}</span></li>)}</ul>}
          <div className="rag-evidence-label"><h3>채택한 근거</h3><span>{result.evidence.length}개 문서</span></div>
          {result.evidence.length ? result.evidence.map((document: Data, index: number) => <EvidenceDocument key={`${document.documentId}-${index}`} document={document} rank={index + 1}/>) : <p className="op-muted">안내문에 채택된 문서가 없습니다.</p>}
          {!!hits.length && <details className="rag-ranked-results"><summary>검색 후보 순위 {hits.length}개 보기</summary><ol>{hits.map((hit, index) => <li key={`${hit.documentId}-${index}`}><span>{hit.title ?? hit.documentId}</span><strong>{Number.isFinite(hit.score) ? Number(hit.score).toFixed(3) : "—"}</strong></li>)}</ol></details>}
          <p className="rag-result-footer">입력 {result.retrieval?.queryLength ?? "—"}자 · 문서 묶음 {result.corpusVersion ?? "—"}</p>
        </> : <div className="rag-empty-result"><Search size={34}/><h3>어떤 근거로 답할까요?</h3><p>질문을 입력하면 찾은 문서, 선택한 조항과 안내문이 함께 표시됩니다.</p></div>}
      </div>
    </div>
    {knowledge && <details className="rag-knowledge-list"><summary><BookOpen size={18}/>개발용 정책 목록 <span>{knowledge.documentCount}개</span></summary><div className="rag-knowledge-grid">{knowledge.documents?.map((document: Data) => <EvidenceDocument key={document.documentId ?? document.id} document={document}/>)}</div></details>}
    <div className="op-inline-note"><ShieldCheck size={18}/><span>합성 정책을 검색한 뒤 검증된 조항으로 문안을 구성합니다. 현재 기본 모드는 외부 언어 모델을 호출하지 않습니다.</span></div>
  </section>;
}
