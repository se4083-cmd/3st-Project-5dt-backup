"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight, ArrowUpRight, Ban, Check, CheckCheck, ChevronRight, CircleAlert,
  CircleCheck, ClipboardList, Clock3, FileCheck2, FileText, Inbox, LifeBuoy,
  MessageCircle, Package, Pause, Play, Plus, RotateCcw, Search, Send,
  ShieldAlert, ShieldCheck, Sparkles, UserRound, Users, X,
} from "lucide-react";
import { deriveMetrics } from "@/lib/operations-presentation";
import { scenarioCatalog } from "../../../shared/operations/fixtures.mjs";
import { operationsApi } from "@/lib/api/client";
import { useOperations } from "./operations-context";
import { CustomerInquiryForm, RagWorkspace, RagEvidence } from "./rag-workspace";
export { OperationsProvider } from "./operations-context";
import "./operations-workspace.css";

type Data = Record<string, any>;
type OperationSection = "home" | "inquiries" | "followups" | "settings" | "customer";
type Navigate = (section: OperationSection | "products") => void;
const scenarios = scenarioCatalog as readonly Data[];
const sectionTitles: Record<OperationSection, { title: string; description: string }> = {
  home: { title: "안내는 빠르게, 판단은 정확하게", description: "자동 안내와 사람의 검토를 하나의 업무 흐름으로 연결합니다." },
  inquiries: { title: "문의 작업 공간", description: "이관 사유를 확인하고, 초안 검토부터 답변 확정까지 진행하세요." },
  followups: { title: "끝까지 이어지는 후속 업무", description: "담당자와 기한을 확인하고, 필요한 조치가 끝날 때까지 추적합니다." },
  settings: { title: "자동화 운영 설정", description: "자동 안내의 허용 범위와 중지·재개 상태를 확인합니다." },
  customer: { title: "내 문의와 진행 상황", description: "안내가 끝난 뒤에도 다시 문의하거나 상담사에게 연결할 수 있습니다." },
};
const statusLabels: Data = {
  OPEN: "접수", REOPENED: "재문의 접수", CLASSIFIED: "유형 확인", VALIDATING: "근거 확인",
  AUTO_READY: "자동 안내 준비", ESCALATED: "상담 대기", ASSIGNED: "상담 중",
  PENDING_APPROVAL: "답변 검토", FOLLOWUP_PENDING: "후속 진행", RESOLVED: "안내 완료",
};
const followupLabels: Data = { OPEN: "등록", IN_PROGRESS: "진행", DONE: "완료", CANCELLED: "취소" };
const followupTransitions: Data = { OPEN: ["OPEN", "IN_PROGRESS", "CANCELLED"], IN_PROGRESS: ["IN_PROGRESS", "DONE", "CANCELLED"], DONE: ["DONE"], CANCELLED: ["CANCELLED"] };
const handoffLabels: Data = {
  HIGH_RISK_ACTION: "환불·보상·계정 결정 요청", HUMAN_REQUESTED: "고객의 상담사 연결 요청",
  AUTOMATION_STOPPED: "자동 안내 중지", OWNERSHIP_UNVERIFIED: "주문 소유권 미확인",
  POLICY_UNAVAILABLE: "정책 근거 미확인", REQUIRED_FOLLOWUP: "필수 후속 확인 필요",
  CUSTOM_INPUT_REVIEW: "직접 작성한 문의 검토 필요", RULE_CHANGED: "처리 중 규칙 변경",
  LOOKUP_NOT_FRESH: "주문 조회 갱신 필요", NOT_ALLOWLISTED: "자동 안내 허용 범위 밖",
  CUSTOMER_UNVERIFIED: "고객 활성 상태 미확인", TEMPLATE_UNVERIFIED: "허용 안내문 일치 미확인",
  MINIMUM_DATA_REVIEW: "자유 입력의 최소 정보 확인 필요",
};
const handoffPriority = Object.keys(handoffLabels);
const handoffDescriptions = (ticket: Data): string[] => [...(ticket.handoffReasons ?? [])]
  .sort((a: Data, b: Data) => (handoffPriority.indexOf(a.code) < 0 ? 100 : handoffPriority.indexOf(a.code)) - (handoffPriority.indexOf(b.code) < 0 ? 100 : handoffPriority.indexOf(b.code)))
  .map((reason: Data) => handoffLabels[reason.code] ?? reason.detail ?? reason.label);
const isClosedFollowup = (followup: Data) => ["DONE", "CANCELLED"].includes(followup.status);
const statusTone = (status: string) => status === "RESOLVED" || status === "DONE" ? "success" : status === "ESCALATED" || status === "FOLLOWUP_PENDING" ? "warning" : status === "CANCELLED" ? "muted" : "purple";
const scenarioGroup = (group: string) => group === "L2" ? "자동 안내" : group === "L3" ? "사람 판단" : "검증 예외";
const shortId = (id: string) => id?.length > 19 ? id.slice(0, 16) + "…" : id;
const time = (value?: string) => {
  if (!value || !Number.isFinite(Date.parse(value))) return "—";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
};
const scenarioOf = (ticket: Data) => scenarios.find(s => s.id === ticket.scenarioId);
const ticketAction = (ticket: Data, type: string, extra: Data = {}) => ({ type, ticketId: ticket.id, expectedCycle: ticket.cycle, expectedVersion: ticket.version, ...extra });

function Tag({ children, tone = "muted" }: { children: React.ReactNode; tone?: string }) {
  return <span className={"badge op-tag " + tone}>{children}</span>;
}

function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return <div className="op-empty"><Inbox size={30}/><h3>{title}</h3>{children && <p>{children}</p>}</div>;
}

function Feedback({ customer = false }: { customer?: boolean }) {
  const { notice, clearNotice } = useOperations();
  if (!notice?.message || notice.scope !== (customer ? "customer" : "staff")) return null;
  return <div className={"op-feedback " + notice.kind} role={notice.kind === "error" ? "alert" : "status"}>
    {notice.kind === "error" ? <CircleAlert size={19}/> : <CircleCheck size={19}/>}<span>{notice.message}</span>
    <button className="icon-button" aria-label="운영 알림 닫기" onClick={clearNotice}><X size={18}/></button>
  </div>;
}

function ScenarioPicker({ onNavigate, compact = false }: { onNavigate: Navigate; compact?: boolean }) {
  const { createScenario } = useOperations();
  const [selected, setSelected] = useState(scenarios[0]?.id ?? "shipping_status");
  const scenario = scenarios.find(s => s.id === selected) ?? scenarios[0];
  return <section className={"card op-scenario-picker " + (compact ? "op-compact" : "")}>
    <div className="op-card-title"><div><span className="op-kicker">직접 흐름 확인하기</span><h2>새 문의 시연</h2></div><Sparkles size={23}/></div>
    {!compact && <p className="op-muted">자동으로 안내되는 문의와 상담사 판단이 필요한 문의를 골라 보세요.</p>}
    <label className="op-field"><span>문의 시나리오</span><select aria-label="문의 시나리오" value={selected} onChange={e => setSelected(e.target.value)}>
      {["L2", "L3", "EXCEPTION"].map(group => <optgroup key={group} label={scenarioGroup(group)}>{scenarios.filter(s => s.group === group).map(s => <option key={s.id} value={s.id}>{s.title}</option>)}</optgroup>)}
    </select></label>
    <div className="op-scenario-summary"><Tag tone={scenario?.group === "L2" ? "success" : scenario?.group === "L3" ? "danger" : "warning"}>{scenarioGroup(scenario?.group)}</Tag><p>{scenario?.description}</p></div>
    <button className="btn primary" onClick={async () => { const result = await createScenario(selected); if (result.notice?.kind !== "error") onNavigate("customer"); }}><Plus size={17}/>문의 접수하고 결과 보기<ArrowRight size={17}/></button>
    <p className="op-small op-muted">예제는 합성 데이터입니다. 실제 고객에게 전송되지 않습니다.</p>
  </section>;
}

function Metric({ title, value, label, icon: Icon, tone, onClick }: { title: string; value: number; label: string; icon: typeof Inbox; tone: string; onClick?: () => void }) {
  return <button className={"card op-metric " + tone} onClick={onClick} disabled={!onClick}>
    <div><span>{title}</span><Icon size={20}/></div><strong>{value.toLocaleString("ko-KR")}<small>건</small></strong><p>{label}{onClick && <ChevronRight size={15}/>}</p>
  </button>;
}

function HomeWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const { state, setSelectedId } = useOperations();
  const metrics = deriveMetrics(state) as Data;
  const pending = state.tickets.filter((t: Data) => t.route === "HUMAN" && t.status !== "RESOLVED").sort((a: Data, b: Data) => {
    const replied = (ticket: Data) => Number(ticket.messages.some((message: Data) => message.final && message.cycle === ticket.cycle));
    return replied(a) - replied(b) || Date.parse(a.slaDueAt) - Date.parse(b.slaDueAt);
  });
  return <>
    <div className="op-metrics">
      <Metric title="전체 시연 문의" value={metrics.total ?? state.tickets.length} label="현재 시연 원장 기준" icon={Inbox} tone="purple" onClick={() => onNavigate("inquiries")}/>
      <Metric title="자동 안내 완료" value={metrics.autoCompleted ?? 0} label="현재 회차 · 사람 승인 없음" icon={CheckCheck} tone="green" onClick={() => onNavigate("inquiries")}/>
      <Metric title="사람 검토·처리" value={pending.length} label="판단이 필요한 미완료 문의" icon={Users} tone="amber" onClick={() => onNavigate("inquiries")}/>
      <Metric title="진행할 후속" value={metrics.openFollowups ?? 0} label="등록·진행 중인 조치" icon={ClipboardList} tone="rose" onClick={() => onNavigate("followups")}/>
    </div>
    <div className="op-home-layout">
      <div className="op-stack">
        <section className="card op-flow-card">
          <div className="op-card-title"><div><span className="op-kicker">L2 자동 안내 · L3 요청 이관</span><h2>문의에 맞는 다음 단계</h2></div><ShieldCheck size={25}/></div>
          <div className="op-flow-branches">
            <div className="op-flow-branch"><div className="op-flow-icon success"><Sparkles size={22}/></div><div><h3>검증된 저위험 안내</h3><p>주문·배송 상태, FAQ, 반품 절차, 명확한 정책을 확인합니다.</p><div className="op-flow-labels"><span>근거 확인</span><ArrowRight size={15}/><span>자동 응답</span><ArrowRight size={15}/><strong>안내 완료</strong></div></div></div>
            <div className="op-flow-branch"><div className="op-flow-icon warning"><UserRound size={22}/></div><div><h3>판단이 필요하거나 검증 실패</h3><p>환불·보상·계정 결정, 근거 부족, 고객 연결 요청을 이관합니다.</p><div className="op-flow-labels"><span>사람 큐</span><ArrowRight size={15}/><span>초안·승인</span><ArrowRight size={15}/><strong>답변·후속</strong></div></div></div>
          </div>
          <div className="op-inline-note"><CircleAlert size={17}/><span>‘안내 완료’는 문의에 대한 설명의 완료입니다. 실제 배송·환불·반품 승인과 구분합니다.</span></div>
        </section>
        <section className="card op-priority-card">
          <div className="op-card-title"><div><h2>먼저 확인할 문의 <span className="count-chip">{pending.length}</span></h2><p className="op-muted">예외 큐에 도착한 문의를 확인하고 인수하세요.</p></div><button className="text-link" onClick={() => onNavigate("inquiries")}>전체 보기<ArrowUpRight size={16}/></button></div>
          {pending.length ? <div className="op-priority-list">{pending.slice(0, 5).map((ticket: Data) => <button key={ticket.id} onClick={() => { setSelectedId(ticket.id); onNavigate("inquiries"); }}>
            <span className={"op-priority-icon " + (scenarioOf(ticket)?.group === "L3" ? "danger" : "warning")}>{scenarioOf(ticket)?.group === "L3" ? <ShieldAlert size={20}/> : <MessageCircle size={20}/>}</span>
            <span className="op-priority-copy"><strong>{ticket.subject}</strong><small>{handoffDescriptions(ticket)[0] ?? statusLabels[ticket.status]} · {ticket.team}</small></span><Tag tone={statusTone(ticket.status)}>{statusLabels[ticket.status] ?? ticket.status}</Tag><ChevronRight size={17}/>
          </button>)}</div> : <Empty title="검토할 문의가 없습니다">새 문의 시연으로 자동 안내와 이관을 확인할 수 있습니다.</Empty>}
        </section>
      </div>
      <div className="op-stack"><section className="card op-rag-start"><Search size={26}/><h3>내 문장으로 문의해 보세요</h3><p>정해진 사례를 고르지 않아도 입력한 질문으로 정책을 검색합니다. 안내 근거는 문의 상세에서 확인할 수 있습니다.</p><button className="btn primary" onClick={() => onNavigate("customer")}>직접 문의 작성<ArrowRight size={17}/></button></section><ScenarioPicker onNavigate={onNavigate}/><section className="card op-product-link"><Package size={27}/><h3>제품의 목소리도 함께 확인</h3><p>기존 VOC TOP 10, P1 개선 제안, P2 이상 탐지를 그대로 이어서 볼 수 있습니다.</p><button className="text-link" onClick={() => onNavigate("products")}>제품 분석 열기<ArrowRight size={16}/></button></section></div>
    </div>
  </>;
}

function Conversation({ messages, customer = false }: { messages: Data[]; customer?: boolean }) {
  return <div className={"op-conversation " + (customer ? "op-customer-conversation" : "")}>
    {messages.length ? messages.map((message: Data) => <article className={"op-message " + (message.author === "CUSTOMER" ? "customer" : "response")} key={message.id}>
      <div className="op-message-meta"><span>{message.author === "CUSTOMER" ? "고객" : message.author === "SYSTEM" ? "자동 안내" : "상담사"}</span><small>{message.cycle}회차 · {time(message.createdAt)}</small>{message.final && <Tag tone="success">확정 답변</Tag>}</div><div className="op-message-bubble">{message.text}</div>
    </article>) : <Empty title="표시할 대화가 없습니다"/>}
  </div>;
}

function Evidence({ ticket }: { ticket: Data }) {
  const evidence = ticket.evidence ?? {};
  const gates: Data[] = ticket.gates ?? [];
  const failed = gates.filter(g => g.status === "FAIL").length;
  return <div className="op-evidence-stack">
    <div className="op-evidence-heading"><div><h3>자동 안내 조건</h3><p>해당하는 모든 조건을 통과해야 자동 안내가 가능합니다.</p></div><Tag tone={failed ? "warning" : gates.length ? "success" : "muted"}>{gates.length ? failed ? `${failed}개 조건 확인 필요` : "검증 통과" : "검증 전"}</Tag></div>
    {gates.length ? <div className="op-gates">{gates.map((gate: Data) => <div className={"op-gate " + gate.status.toLowerCase()} key={gate.key}>
      {gate.status === "PASS" ? <CircleCheck size={19}/> : gate.status === "FAIL" ? <CircleAlert size={19}/> : <Ban size={19}/>}<div><strong>{gate.label}</strong><p>{gate.detail}</p></div><span>{gate.status === "PASS" ? "통과" : gate.status === "FAIL" ? "보류" : "해당 없음"}</span>
    </div>)}</div> : <Empty title="자동 안내 검증을 시작해 주세요"/>}
    <div className="op-evidence-columns">
      <section><h3><Package size={18}/>주문 조회</h3>{evidence.order ? <dl className="op-definition-list"><dt>주문</dt><dd>{evidence.order.reference}</dd><dt>현재 상태</dt><dd>{evidence.order.statusLabel ?? evidence.order.status}</dd><dt>도착 예정</dt><dd>{evidence.order.eta ? time(evidence.order.eta) : "확인된 예정 시각 없음"}</dd><dt>조회 시각</dt><dd>{time(evidence.order.fetchedAt)}</dd><dt>자료 구분</dt><dd>합성 주문 조회</dd></dl> : <p className="op-muted">이 문의에 표시할 주문 조회 근거가 없습니다.</p>}</section>
      <section><h3><FileText size={18}/>정책 근거</h3>{evidence.policies?.length ? evidence.policies.map((policy: Data) => <div className="op-policy" key={policy.id}><strong>{policy.title}</strong><small>버전 {policy.version} · {policy.clause}</small>{!ticket.rag && <p>{policy.text}</p>}<Tag tone={policy.active ? "success" : "warning"}>{policy.active ? "유효한 시연 정책" : "유효성 확인 필요"}</Tag></div>) : <p className="op-muted">유효한 정책 근거가 확인되지 않았습니다.</p>}</section>
    </div>
    <RagEvidence ticket={ticket}/><div className="op-inline-note"><ShieldCheck size={17}/><span>개발용 합성 근거 · 규칙 버전 {evidence.ruleVersion ?? "—"} · 확인 {time(evidence.checkedAt)}. 검색 근거가 있는 문의는 아래의 문서 식별자로 확인합니다.</span></div>
  </div>;
}

function History({ ticket }: { ticket: Data }) {
  return <div className="op-history">{ticket.events?.length ? [...ticket.events].reverse().map((event: Data) => <article key={event.id}><span className="op-history-dot"/><div><div><strong>{event.label ?? event.type}</strong><small>{event.cycle}회차 · {time(event.createdAt)}</small></div>{event.detail && <p>{event.detail}</p>}</div></article>) : <Empty title="아직 기록된 단계가 없습니다"/>}</div>;
}

function DraftEditor({ ticket }: { ticket: Data }) {
  const { act } = useOperations();
  const [draft, setDraft] = useState(ticket.draft ?? "");
  useEffect(() => setDraft(ticket.draft ?? ""), [ticket.id, ticket.cycle, ticket.draft]);
  const dirty = draft !== (ticket.draft ?? "");
  const responded = ticket.messages?.some((m: Data) => m.cycle === ticket.cycle && m.final);
  const editable = ticket.route === "HUMAN" && !!ticket.assignee && !responded;
  const approved = !!ticket.approval && !ticket.approval.used && ticket.approval.cycle === ticket.cycle && Date.parse(ticket.approval.expiresAt) > Date.now();
  const openBlocking = (ticket.followups ?? []).filter((f: Data) => f.blocking && !isClosedFollowup(f));
  if (responded) return <section className="op-response-complete"><CircleCheck size={23}/><div><h3>이 회차의 답변이 확정되었습니다</h3><p>{openBlocking.length ? `필수 후속 ${openBlocking.length}건이 남아 있어 후속 진행 상태를 유지합니다.` : "고객이 재문의하면 새 회차에서 이어서 처리합니다."}</p></div></section>;
  if (ticket.route !== "HUMAN") return <section className="op-response-complete neutral"><Sparkles size={23}/><div><h3>자동 안내 경로입니다</h3><p>조건을 모두 통과하면 상담사 승인 없이 안내가 완료됩니다.</p></div><button className="btn secondary" onClick={() => act(ticketAction(ticket, "RUN_AUTO"))}>자동 안내 확인<ArrowRight size={16}/></button></section>;
  return <section className="op-draft-editor">
    <div className="op-card-title"><div><h3>상담사 답변</h3><p className="op-muted">초안 저장 → 승인 → 답변 확정 순서로 진행합니다.</p></div><Tag tone={approved && !dirty ? "success" : "muted"}>{approved && !dirty ? "현재 초안 승인됨" : !ticket.assignee ? "인수 필요" : "검토 필요"}</Tag></div>
    {!ticket.assignee && <div className="op-inline-note"><UserRound size={17}/><span>이 문의를 인수하면 답변과 후속 업무를 작성할 수 있습니다.</span></div>}
    <label className="op-field"><span>답변 초안</span><textarea aria-label="답변 초안" rows={5} maxLength={10000} value={draft} onChange={e => setDraft(e.target.value)} disabled={!editable} placeholder="확인된 사실과 다음 안내를 작성하세요. 환불 승인이나 지급을 확정하는 표현은 사용하지 마세요."/></label>
    <div className="op-draft-hint"><span>{dirty ? "변경 내용을 저장하면 이전 승인은 해제됩니다." : approved ? `승인 유효 시각 ${time(ticket.approval.expiresAt)}까지` : "저장된 현재 초안에 대해 승인합니다."}</span><small>{draft.length.toLocaleString("ko-KR")} / 10,000자</small></div>
    <div className="op-action-row">
      <button className="btn secondary" disabled={!editable || !draft.trim() || !dirty} onClick={() => act(ticketAction(ticket, "SAVE_DRAFT", { text: draft }))}><FileText size={17}/>1. 초안 저장</button>
      <button className="btn secondary" disabled={!editable || dirty || !draft.trim() || approved} onClick={() => act(ticketAction(ticket, "APPROVE"))}><FileCheck2 size={17}/>2. 답변 승인</button>
      <button className="btn primary" disabled={!editable || dirty || !approved} onClick={() => act(ticketAction(ticket, "SEND_HUMAN"))}><Send size={17}/>3. 시연 답변 확정</button>
    </div>
    {openBlocking.length > 0 && <p className="op-small op-muted">답변 이후에도 필수 후속 {openBlocking.length}건이 끝날 때까지 안내 완료로 변경하지 않습니다.</p>}
  </section>;
}

function FollowupStatusControl({ ticket, followup }: { ticket: Data; followup: Data }) {
  const { act } = useOperations();
  const [nextStatus, setNextStatus] = useState(followup.status);
  const [reason, setReason] = useState("");
  useEffect(() => { setNextStatus(followup.status); setReason(""); }, [followup.id, followup.status]);
  const options: string[] = followupTransitions[followup.status] ?? [followup.status];
  if (isClosedFollowup(followup)) return <Tag tone={statusTone(followup.status)}>{followupLabels[followup.status]}</Tag>;
  return <div className="op-followup-status-control">
    <div><select aria-label={followup.title + " 상태"} value={nextStatus} onChange={e => setNextStatus(e.target.value)}>{options.map(status => <option key={status} value={status}>{followupLabels[status]}</option>)}</select><button className="btn secondary" disabled={nextStatus === followup.status || (nextStatus === "CANCELLED" && !reason.trim())} onClick={() => act(ticketAction(ticket, "UPDATE_FOLLOWUP", { followupId: followup.id, expectedFollowupVersion: followup.version, status: nextStatus, ...(nextStatus === "CANCELLED" ? { reason } : {}) }))}>변경 적용</button></div>
    {nextStatus === "CANCELLED" && <label className="op-field"><span>취소 사유</span><input aria-label={followup.title + " 취소 사유"} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} placeholder="취소하는 이유를 입력하세요"/></label>}
  </div>;
}

function FollowupForm({ ticket }: { ticket: Data }) {
  const { act } = useOperations();
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [publicNote, setPublicNote] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [blocking, setBlocking] = useState(true);
  useEffect(() => { setTitle(""); setDueAt(""); setPublicNote(""); setInternalNote(""); setBlocking(true); }, [ticket.id, ticket.cycle]);
  const canAdd = ticket.route === "HUMAN" && !!ticket.assignee && ticket.status !== "RESOLVED";
  return <details className="op-followup-form"><summary><Plus size={17}/>후속 조치 등록</summary><form onSubmit={async event => {
    event.preventDefault();
    const result = await act(ticketAction(ticket, "ADD_FOLLOWUP", { title, publicNote, internalNote, blocking, ...(dueAt ? { dueAt: new Date(dueAt).toISOString() } : {}) }));
    if (result.notice?.kind !== "error") { setTitle(""); setPublicNote(""); setInternalNote(""); setDueAt(""); }
  }}>
    {!canAdd && <p className="op-small op-muted">사람에게 이관된 미완료 문의를 인수한 뒤 등록할 수 있습니다.</p>}
    <fieldset disabled={!canAdd}><div className="op-form-grid"><label className="op-field"><span>조치 이름</span><input required maxLength={160} aria-label="후속 조치 이름" value={title} onChange={e => setTitle(e.target.value)} placeholder="예: 반품 조건 확인"/></label><label className="op-field"><span>기한 <small>기기 시간 · 미입력 시 24시간 뒤</small></span><input type="datetime-local" aria-label="후속 조치 기한" value={dueAt} onChange={e => setDueAt(e.target.value)}/></label></div>
    <label className="op-field"><span>고객에게 공개할 안내</span><textarea rows={2} maxLength={3000} aria-label="고객 공개 후속 안내" value={publicNote} onChange={e => setPublicNote(e.target.value)} placeholder="고객이 확인할 진행 안내만 작성하세요."/></label>
    <label className="op-field"><span>내부 메모 <Tag>고객에게 비공개</Tag></span><textarea rows={2} maxLength={3000} aria-label="후속 내부 메모" value={internalNote} onChange={e => setInternalNote(e.target.value)} placeholder="상담사 간에 공유할 내용"/></label>
    <label className="op-checkbox"><input type="checkbox" checked={blocking} onChange={e => setBlocking(e.target.checked)}/><span>완료 전에는 문의를 해결하지 않는 필수 후속</span></label>
    <div className="op-action-row"><span className="op-small op-muted">담당: {ticket.assignee ?? "미배정"}</span><button className="btn secondary" type="submit" disabled={!title.trim()}><Plus size={17}/>후속 등록</button></div></fieldset>
  </form></details>;
}

function TicketFollowups({ ticket }: { ticket: Data }) {
  return <section className="op-ticket-followups"><div className="op-card-title"><h3>후속 조치 <span className="count-chip">{ticket.followups?.length ?? 0}</span></h3><ClipboardList size={19}/></div>
    {ticket.followups?.length > 0 && <div className="op-mini-followups">{ticket.followups.map((followup: Data) => <article key={followup.id}><div><strong>{followup.title}</strong><p>{followup.blocking ? "필수 후속" : "일반 후속"} · 담당 {followup.owner ?? followup.assignee ?? ticket.assignee ?? "미배정"} · {time(followup.dueAt)}까지</p>{followup.publicNote && <small>고객 공개: {followup.publicNote}</small>}{followup.cancellationReason && <small>취소 사유: {followup.cancellationReason}</small>}</div><FollowupStatusControl ticket={ticket} followup={followup}/></article>)}</div>}
    <FollowupForm ticket={ticket}/>
  </section>;
}

function TicketDetail({ ticket, onNavigate }: { ticket: Data; onNavigate: Navigate }) {
  const { act, setCustomerId } = useOperations();
  const [tab, setTab] = useState("conversation");
  useEffect(() => setTab("conversation"), [ticket.id]);
  const scenario = scenarioOf(ticket);
  const canClaim = ticket.route === "HUMAN" && !ticket.assignee && ticket.status !== "RESOLVED";
  return <section className="card op-ticket-detail" aria-label="선택 문의 상세">
    <header className="op-ticket-header"><div><div className="op-ticket-eyebrow"><span>{shortId(ticket.id)}</span><span>{ticket.cycle}회차</span><span>{ticket.team}</span></div><h2>{ticket.subject}</h2><div className="op-ticket-subline"><Tag tone={statusTone(ticket.status)}>{statusLabels[ticket.status] ?? ticket.status}</Tag><span><UserRound size={15}/>{ticket.assignee ?? "담당자 미배정"}</span><span><Clock3 size={15}/>첫 응답 기한 {time(ticket.slaDueAt)}</span></div></div>
      <div className="op-ticket-header-actions"><button className="btn secondary" onClick={() => { setCustomerId(ticket.id); onNavigate("customer"); }}><ArrowUpRight size={16}/>고객 화면</button>{canClaim && <button className="btn primary" onClick={() => act(ticketAction(ticket, "CLAIM"))}><UserRound size={17}/>문의 인수</button>}</div>
    </header>
    {ticket.handoffReasons?.length > 0 && <div className={"op-handoff-note " + (scenario?.group === "L3" ? "risk" : "")}><ShieldAlert size={23}/><div><strong>{scenario?.group === "L3" ? "사람의 판단이 필요한 요청입니다" : "자동 안내를 멈추고 상담사에게 이관했습니다"}</strong><p>{handoffDescriptions(ticket).join(" · ")}</p>{scenario?.group === "L3" && <small>환불·보상·계정 권리의 자동 결정은 실행하지 않습니다.</small>}</div></div>}
    <div className="op-detail-tabs" role="tablist" aria-label="문의 상세 구역">{[{ id: "conversation", label: "대화·답변", icon: MessageCircle }, { id: "evidence", label: "주문·검증 근거", icon: ShieldCheck }, { id: "history", label: "처리 이력", icon: Clock3 }].map(t => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}><t.icon size={17}/>{t.label}</button>)}</div>
    <div className="op-ticket-body">{tab === "conversation" ? <><Conversation messages={ticket.messages ?? []}/><DraftEditor ticket={ticket}/><TicketFollowups ticket={ticket}/></> : tab === "evidence" ? <Evidence ticket={ticket}/> : <History ticket={ticket}/>}</div>
  </section>;
}

function InquiriesWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const { state, selectedId, setSelectedId, inquiryFocus, clearInquiryFocus } = useOperations();
  const [filter, setFilter] = useState(() => inquiryFocus ? "all" : "pending");
  const [requestedId, setRequestedId] = useState(inquiryFocus?.ticketId ?? "");
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (!inquiryFocus) return;
    setFilter("all"); setQuery(""); setRequestedId(inquiryFocus.ticketId); setSelectedId(inquiryFocus.ticketId);
    clearInquiryFocus();
  }, [inquiryFocus, clearInquiryFocus, setSelectedId]);
  const tickets: Data[] = state.tickets;
  const counts = { pending: tickets.filter(t => t.route === "HUMAN" && t.status !== "RESOLVED").length, all: tickets.length, auto: tickets.filter(t => t.route === "AUTO" && t.status === "RESOLVED").length };
  const rows = tickets.filter(t => (filter === "all" || filter === "pending" ? filter === "all" || (t.route === "HUMAN" && t.status !== "RESOLVED") : t.route === "AUTO" && t.status === "RESOLVED") && [t.id, t.subject, t.customerRef, t.team, ...handoffDescriptions(t)].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const ticket = requestedId ? rows.find(t => t.id === requestedId) : rows.find(t => t.id === selectedId) ?? rows[0];
  return <>
    {requestedId && <div className="op-linked-focus"><Inbox size={17}/><span>선택한 문의 · {requestedId} · 전체 목록에서 확인</span><button className="text-link" onClick={() => { setRequestedId(""); setFilter("pending"); setQuery(""); }}>예외 큐로 돌아가기</button></div>}
    <div className="op-queue-toolbar"><div className="op-filter-tabs" role="tablist" aria-label="문의 목록 필터">{[{ id: "pending", label: "예외·처리 대기", count: counts.pending }, { id: "all", label: "전체", count: counts.all }, { id: "auto", label: "자동 안내 완료", count: counts.auto }].map(f => <button key={f.id} role="tab" aria-selected={filter === f.id} className={filter === f.id ? "active" : ""} onClick={() => { setRequestedId(""); setFilter(f.id); }}>{f.label}<span>{f.count}</span></button>)}</div><button className="btn secondary" onClick={() => onNavigate("customer")}><Plus size={17}/>새 문의 시연</button></div>
    <div className="op-inquiries-layout"><section className="card op-ticket-queue" aria-label="문의 목록"><div className="op-queue-search"><Search size={18}/><input aria-label="문의 검색" placeholder="문의명, 번호, 팀 검색" value={query} onChange={e => { setRequestedId(""); setQuery(e.target.value); }}/>{query && <button className="icon-button" aria-label="문의 검색 지우기" onClick={() => setQuery("")}><X size={16}/></button>}</div><div className="op-queue-count">{rows.length}건 · 합성 문의</div>
      <div className="op-ticket-list">{rows.length ? rows.map((item: Data) => <button key={item.id} className={ticket?.id === item.id ? "selected" : ""} aria-pressed={ticket?.id === item.id} onClick={() => { setRequestedId(""); setSelectedId(item.id); }}><div className="op-ticket-list-top"><span>{shortId(item.id)}</span><Tag tone={statusTone(item.status)}>{statusLabels[item.status] ?? item.status}</Tag></div><strong>{item.subject}</strong><p>{handoffDescriptions(item)[0] ?? (item.route === "AUTO" ? "검증된 저위험 자동 안내" : "상담사 확인")}</p><div className="op-ticket-list-bottom"><span>{item.team}</span><small>{item.cycle}회차</small></div></button>) : <Empty title="일치하는 문의가 없습니다">필터나 검색어를 바꿔 보세요.</Empty>}</div>
    </section>{ticket ? <TicketDetail ticket={ticket} onNavigate={onNavigate}/> : <section className="card"><Empty title={requestedId ? "선택한 문의를 현재 목록에서 찾지 못했습니다" : "확인할 문의를 선택해 주세요"}>{requestedId ? "최신 상태를 확인하거나 예외 큐로 돌아가 주세요." : "새 문의 시연에서 자동 안내와 사람 이관을 확인할 수 있습니다."}</Empty></section>}</div>
  </>;
}

function FollowupsWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const { state, followupFocus, clearFollowupFocus, focusInquiry } = useOperations();
  const [focused, setFocused] = useState(followupFocus);
  const [filter, setFilter] = useState(() => followupFocus ? "all" : "active");
  useEffect(() => {
    if (!followupFocus) return;
    setFocused(followupFocus); setFilter("all"); clearFollowupFocus();
  }, [followupFocus, clearFollowupFocus]);
  const rows: Data[] = state.tickets.flatMap((ticket: Data) => (ticket.followups ?? []).map((followup: Data) => ({ ticket, followup })));
  const filtered = rows.filter(({ ticket, followup }) => (!focused || (ticket.id === focused.ticketId && (!focused.followupId || followup.id === focused.followupId)))
    && (filter === "all" || (filter === "active" ? !isClosedFollowup(followup) : followup.status === filter)));
  return <>
    {focused && <div className="op-linked-focus"><ClipboardList size={17}/><span>선택한 문의의 후속 · {focused.ticketId}{focused.followupId ? ` · ${focused.followupId}` : ""}</span><button className="text-link" onClick={() => { setFocused(null); setFilter("active"); }}>전체 후속 보기</button></div>}
    <div className="op-queue-toolbar"><div className="op-filter-tabs" role="tablist" aria-label="후속 상태 필터">{[{ id: "active", label: "미완료" }, { id: "all", label: "전체" }, { id: "DONE", label: "완료" }, { id: "CANCELLED", label: "취소" }].map(f => <button key={f.id} role="tab" aria-selected={filter === f.id} className={filter === f.id ? "active" : ""} onClick={() => setFilter(f.id)}>{f.label}</button>)}</div><button className="btn secondary" onClick={() => onNavigate("inquiries")}><Plus size={17}/>문의에서 후속 등록</button></div>
    <div className="op-followups-summary"><ClipboardList size={18}/><span>현재 {filtered.length}건 표시 · 필수 후속이 남은 문의는 답변을 보내도 후속 진행 상태로 유지됩니다.</span></div>
    <div className="op-followup-cards">{filtered.length ? filtered.map(({ ticket, followup }: Data) => <article key={followup.id} className={"card op-followup-card" + (focused ? " is-focused" : "")}><div className="op-card-title"><div><span className="op-kicker">{shortId(ticket.id)} · {ticket.subject}</span><h2>{followup.title}</h2></div><Tag tone={followup.blocking ? "warning" : "muted"}>{followup.blocking ? "필수 후속" : "일반 후속"}</Tag></div><dl className="op-followup-meta"><div><dt><UserRound size={16}/>담당</dt><dd>{followup.owner ?? followup.assignee ?? ticket.assignee ?? "미배정"}</dd></div><div><dt><Clock3 size={16}/>기한</dt><dd>{time(followup.dueAt)}</dd></div><div><dt>상태</dt><dd><Tag tone={statusTone(followup.status)}>{followupLabels[followup.status]}</Tag></dd></div></dl><div className="op-followup-notes"><div><span>고객 공개 안내</span><p>{followup.publicNote || "등록된 공개 안내가 없습니다."}</p></div><div><span>내부 메모 · 고객 비공개</span><p>{followup.internalNote || "등록된 내부 메모가 없습니다."}</p></div>{followup.cancellationReason && <div><span>취소 사유 · 고객 비공개</span><p>{followup.cancellationReason}</p></div>}</div><div className="op-followup-bottom"><FollowupStatusControl ticket={ticket} followup={followup}/><button className="text-link" onClick={() => { focusInquiry(ticket.id); onNavigate("inquiries"); }}>문의 열기<ArrowUpRight size={16}/></button></div></article>) : <section className="card"><Empty title={focused ? "선택한 범위에서 이 상태의 후속을 찾지 못했습니다" : "이 상태의 후속 업무가 없습니다"}>{focused ? "상태 필터를 전체로 바꾸거나 최신 상태를 확인해 주세요." : "문의 상세에서 담당자가 필요한 후속을 등록할 수 있습니다."}</Empty></section>}</div>
  </>;
}

function SettingsWorkspace() {
  const { state, act } = useOperations();
  const [reason, setReason] = useState("");
  const automation = state.automation;
  const regression = automation.regression;
  const canResume = !automation.enabled && automation.regressionPassed && regression?.passed && regression?.ruleVersion === automation.version;
  return <><RagWorkspace/><div className="op-settings-grid">
    <section className="card op-settings-card"><div className="op-card-title"><div><span className="op-kicker">자동 안내 운영</span><h2>{automation.enabled ? "L2 자동 안내가 켜져 있습니다" : "L2 자동 안내가 중지되었습니다"}</h2></div><span className={"op-system-status " + (automation.enabled ? "enabled" : "disabled")}>{automation.enabled ? <Play size={23}/> : <Pause size={23}/>}</span></div><p className="op-muted">중지 이후에는 새 자동 답변을 확정하지 않고 사람의 검토로 연결합니다. 이미 확정된 답변은 유지됩니다.</p>
      {automation.stopReason && <div className="op-stop-reason"><strong>기록된 중지 사유</strong><p>{automation.stopReason}</p></div>}
      <label className="op-field"><span>자동화 중지 사유</span><textarea aria-label="자동화 중지 사유" rows={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} disabled={!automation.enabled} placeholder="예: 정책 근거 재확인이 필요하여 중지"/></label><button className="btn op-danger-button" disabled={!automation.enabled || !reason.trim()} onClick={async () => { const result = await act({ type: "STOP_AUTOMATION", reason }); if (result.notice?.kind !== "error") setReason(""); }}><Pause size={17}/>자동 안내 중지</button>
    </section>
    <section className="card op-settings-card"><div className="op-card-title"><div><span className="op-kicker">다시 시작하기 전</span><h2>안전 확인과 재개</h2></div><ShieldCheck size={26}/></div><p className="op-muted">시연 규칙으로 자동 안내·고위험 차단·중복 방지 등을 다시 확인한 뒤 재개합니다.</p><div className="op-resume-steps"><div><span>1</span><p>중지 원인을 확인하고 시연 검사를 실행</p></div><div><span>2</span><p>현재 규칙 버전의 검사 통과 여부 확인</p></div><div><span>3</span><p>관리자가 자동 안내 재개를 명시적으로 선택</p></div></div><div className="op-action-row"><button className="btn secondary" disabled={automation.enabled} onClick={() => act({ type: "RUN_REGRESSION" })}><ShieldCheck size={17}/>안전 검사 실행</button><button className="btn primary" disabled={!canResume} onClick={() => act({ type: "RESUME_AUTOMATION" })}><Play size={17}/>자동 안내 재개</button></div><p className="op-small op-muted">로컬 검사는 현재 개발 규칙을 대상으로 합니다. 팀 서비스의 통합 검증은 API 연결 후 진행합니다.</p></section>
    {regression && <section className="card op-settings-card op-wide"><div className="op-card-title"><div><h2>시연 안전 검사 결과</h2><p className="op-muted">{time(regression.ranAt)} · 규칙 버전 {regression.ruleVersion}</p></div><Tag tone={regression.passed ? "success" : "danger"}>{regression.passed ? "검사 통과" : "확인 필요"}</Tag></div><div className="op-regression-grid">{regression.checks?.map((check: Data) => <div className={check.passed ? "pass" : "fail"} key={check.id}>{check.passed ? <CircleCheck size={20}/> : <CircleAlert size={20}/>}<div><strong>{check.title}</strong><p>{check.detail}</p></div></div>)}</div></section>}
    <section className="card op-settings-card"><div className="op-card-title"><h2>자동 안내 허용 범위</h2><Tag tone="purple">L2</Tag></div><ul className="op-allowlist">{["본인 주문·배송의 현재 상태", "주문과 무관한 일반 FAQ", "교환·반품의 신청 절차", "근거가 명확한 정책 안내"].map(item => <li key={item}><Check size={18}/>{item}</li>)}</ul><div className="op-inline-note"><Ban size={18}/><span>환불 승인·보상 지급·계정 권리 변경은 L3 요청으로 식별해 사람에게 이관합니다.</span></div></section>
    <section className="card op-settings-card"><div className="op-card-title"><h2>시연 데이터 관리</h2><RotateCcw size={23}/></div><p className="op-muted">문의, 답변, 후속은 로컬 데이터베이스에 저장됩니다. 새로고침과 서버 재시작 후에도 이어집니다. 초기화하면 준비된 합성 문의로 돌아갑니다.</p><button className="btn secondary" onClick={async () => { const result = await act({ type: "RESET" }); if (result.notice?.kind !== "error") setReason(""); }}><RotateCcw size={17}/>시연 처음으로</button><details className="op-connection-details"><summary>현재 연결 범위</summary><p>로컬 API, SQLite 저장, 임시 정책 검색과 근거 기반 문안 작성을 연결했습니다. 역할은 로컬 시연용이며, 팀 인증·PostgreSQL 작업 큐·정식 RAG·실제 고객 발송은 연결 전입니다.</p><p>기존 제품 VOC·P1·P2 데이터와 분석 기능은 별도 제품 메뉴에서 유지합니다.</p></details></section>
  </div></>;
}

function CustomerWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const { customerId, setCustomerId, focusInquiry, customerTickets, customerLoaded, refreshCustomer, actCustomer } = useOperations();
  const [body, setBody] = useState("");
  const [detail, setDetail] = useState<Data | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const source = customerTickets.find(ticket => ticket.id === customerId) ?? customerTickets[0];
  useEffect(() => {
    const controller = new AbortController();
    void refreshCustomer(controller.signal);
    const onFocus = () => { void refreshCustomer(); setRefreshKey(key => key + 1); };
    window.addEventListener("focus", onFocus);
    return () => { controller.abort(); window.removeEventListener("focus", onFocus); };
  }, [refreshCustomer]);
  useEffect(() => {
    if (!source) { setDetail(null); return; }
    const controller = new AbortController();
    setDetailLoading(true); setDetailError(""); setDetail(null);
    operationsApi.customerTicket(source.id, controller.signal).then(result => {
      if (!result.ticket || result.ticket.id !== source.id) throw new Error("문의 상세를 확인하지 못했습니다.");
      if (!controller.signal.aborted) setDetail(result.ticket);
    }).catch(error => { if (!controller.signal.aborted) setDetailError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [source?.id, source?.version, refreshKey]);
  useEffect(() => { setBody(""); }, [source?.id, source?.cycle]);
  const ticket = detail?.id === source?.id ? detail : null;
  return <div className="op-customer-layout"><div className="op-stack"><section className="card op-customer-card"><div className="op-customer-card-header"><div><span className="op-kicker">합성 고객 체험</span><h2>내 문의</h2></div><button className="text-link" onClick={() => { if (source) focusInquiry(source.id); onNavigate("inquiries"); }}>운영자 화면<ArrowUpRight size={16}/></button></div>
      <label className="op-field op-customer-selector"><span>내 합성 문의 선택</span><select aria-label="고객 화면의 시연 문의" value={source?.id ?? ""} onChange={event => setCustomerId(event.target.value)} disabled={!customerLoaded || !customerTickets.length}>{customerTickets.map(item => <option key={item.id} value={item.id}>{item.subject} · {shortId(item.id)}</option>)}</select></label>
      <div className="op-api-status"><span>공개 답변과 진행 상황</span><button className="text-link" onClick={async () => { await refreshCustomer(); setRefreshKey(key => key + 1); }}><RotateCcw size={15}/>최신 내용 확인</button></div>
      {detailLoading || !customerLoaded ? <div className="op-customer-view-loading" role="status">공개 문의 정보를 불러오고 있습니다.</div> : detailError ? <div className="rag-error" role="alert"><CircleAlert size={18}/>{detailError}</div> : ticket ? <><div className="op-customer-subject"><div><h3>{ticket.subject}</h3><p>{shortId(ticket.id)} · {ticket.cycle}회차</p></div><Tag tone={statusTone(ticket.status)}>{ticket.statusLabel ?? statusLabels[ticket.status]}</Tag></div>
        <ol className="op-progress" aria-label="문의 진행 단계">{ticket.progress.map((step: Data, index: number) => <li key={step.key} className={step.state} aria-current={step.state === "current" ? "step" : undefined}><span>{step.state === "done" ? <Check size={17}/> : index + 1}</span><strong>{step.label}</strong></li>)}</ol>
        <div className={"op-customer-notice " + (ticket.route === "AUTO" ? "automatic" : "human")}>{ticket.route === "AUTO" ? <CircleCheck size={22}/> : <LifeBuoy size={22}/>}<p>{ticket.notice}</p></div>
        <Conversation messages={ticket.messages ?? []} customer/>
        {ticket.followups?.length > 0 && <section className="op-public-followups"><h3>진행 중인 안내와 후속</h3>{ticket.followups.map((followup: Data) => <article key={followup.id}><Tag tone={statusTone(followup.status)}>{followup.statusLabel ?? followupLabels[followup.status]}</Tag><p>{followup.publicNote || "담당자가 후속 조치를 확인하고 있습니다."}</p><small>확인 기한 {time(followup.dueAt)}</small></article>)}</section>}
        <div className="op-customer-actions"><div><h3>더 도움이 필요하신가요?</h3><p>안내 완료 후에도 문의를 이어갈 수 있습니다.</p></div><button className="btn secondary" disabled={!ticket.canRequestHuman} onClick={() => actCustomer(ticketAction(ticket, "REQUEST_HUMAN"))}><UserRound size={18}/>{ticket.canRequestHuman ? "상담사 연결 요청" : "상담사 연결 요청됨"}</button></div>
        <details className="op-reopen-form"><summary><MessageCircle size={18}/>추가 문의 보내기</summary><form onSubmit={async event => {
          event.preventDefault();
          const response = await actCustomer(ticketAction(ticket, "REOPEN", { body }));
          if (response.ticket) setBody("");
        }}>
          <label className="op-field"><span>추가 문의 내용</span><textarea aria-label="고객 추가 문의 내용" rows={3} maxLength={10000} required value={body} onChange={event => setBody(event.target.value)} placeholder="이 문의에서 더 확인할 내용을 작성하세요."/></label>
          <p className="op-small op-muted">이전 답변과 분리된 새 회차로 접수합니다. 개인정보는 입력하지 마세요.</p><button type="submit" className="btn primary" disabled={!ticket.canReopen || !body.trim()}><Send size={17}/>새 회차로 문의</button>
        </form></details>
      </> : <Empty title="아직 접수된 문의가 없습니다">새 문의 작성에서 질문을 입력해 주세요.</Empty>}
    </section></div><div className="op-stack"><CustomerInquiryForm/><section className="card op-customer-help"><ShieldCheck size={24}/><h3>고객에게 필요한 정보만</h3><p>확정된 답변과 공개 후속을 서버에서 받아 표시합니다. 상담사의 초안, 검증 상세와 내부 메모는 공개 응답에서 제외됩니다.</p></section></div></div>;
}

export function OperationsWorkspace({ section, onNavigate }: { section: OperationSection; onNavigate: Navigate }) {
  const { state, loaded, loading, busy, error, uncertain, retryPending, refresh } = useOperations();
  const heading = sectionTitles[section];
  useEffect(() => {
    if (section === "customer") return;
    void refresh();
    const onFocus = () => { void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [section, refresh]);
  return <div className={"op-workspace op-section-" + section}>
    <div className="page-title"><div><div className="eyebrow">{section === "customer" ? "CUSTOMER EXPERIENCE" : "OPERATIONS WORKSPACE"} · V2</div><h1>{heading.title}</h1><p>{heading.description}</p></div>{section !== "customer" ? <button className="btn secondary" onClick={() => onNavigate("customer")}><UserRound size={17}/>고객 화면 체험</button> : <button className="btn secondary" onClick={() => document.getElementById("new-inquiry")?.scrollIntoView({ behavior: "smooth", block: "start" })}><Plus size={17}/>새 문의 작성</button>}</div>
    <div className="op-environment-banner"><span><ShieldCheck size={18}/><strong>로컬 개발 · 합성 데이터</strong><span>실제 고객 발송 없음</span></span>{loaded && section !== "customer" && <Tag tone={state.automation.enabled ? "success" : "warning"}>{state.automation.enabled ? "자동 안내 켜짐" : "자동 안내 중지"}</Tag>}</div>
    <Feedback key={section} customer={section === "customer"}/>
    {uncertain && <div className="op-uncertain" role="alert"><CircleAlert size={22}/><div><strong>앞선 요청의 결과를 확인해 주세요</strong><p>같은 요청 번호로 서버의 처리 결과를 다시 확인합니다. 확인 전에는 새 작업을 보내지 않습니다.</p></div><button className="btn secondary" disabled={busy} onClick={() => retryPending()}>처리 결과 다시 확인</button></div>}
    {!loaded && section !== "customer" ? <section className="card op-api-loading" aria-busy={loading}><DatabaseIcon/><h2>{loading ? "로컬 API에 연결하고 있습니다" : "로컬 API 연결을 확인해 주세요"}</h2><p>{error || "저장된 문의와 처리 상태를 불러옵니다."}</p>{!loading && <button className="btn primary" onClick={() => refresh()}><RotateCcw size={17}/>다시 연결</button>}</section> : <>
      {section !== "customer" && <div className="op-api-status"><FileCheck2 size={17}/><span>변경 내용 저장됨 · 새로고침 후에도 유지</span><button className="text-link" disabled={busy} onClick={() => refresh()}><RotateCcw size={15}/>최신 상태 확인</button></div>}
      {error && section !== "customer" && <div className="rag-error" role="alert"><CircleAlert size={18}/><p>{error} 마지막으로 확인된 상태를 표시합니다.</p></div>}
      {busy && <div className="op-local-busy" role="status"><Clock3 size={18}/>서버에서 검증하고 저장하고 있습니다.</div>}
      <fieldset className="op-content-fieldset" disabled={busy || uncertain} aria-label="문의 처리 작업">
        {section === "home" ? <HomeWorkspace onNavigate={onNavigate}/> : section === "inquiries" ? <InquiriesWorkspace onNavigate={onNavigate}/> : section === "followups" ? <FollowupsWorkspace onNavigate={onNavigate}/> : section === "settings" ? <SettingsWorkspace/> : <CustomerWorkspace onNavigate={onNavigate}/>}
      </fieldset>
    </>}
  </div>;
}

function DatabaseIcon() { return <Inbox size={32}/>; }
