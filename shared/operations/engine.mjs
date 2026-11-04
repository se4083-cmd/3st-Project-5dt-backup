/**
 * Immutable synthetic operations state machine, executed by the local API.
 * Persistence, role checks and finalization transactions belong to backend/src.
 * RAG contexts are supplied only by the server after retrieval and revalidation;
 * neither a browser payload nor a retrieval score authorizes automatic sending.
 */
import { DEMO_POLICY_SOURCE, demoPolicies, getScenario, scenarioCatalog } from './fixtures.mjs';
import { sha256 } from '../crypto/sha256.mjs';

export { scenarioCatalog };

const MANAGER = 'DEMO-MANAGER';
const MAX_TEXT = 10000;
const ALLOW_KINDS = new Set(['ORDER_STATUS', 'GENERAL_FAQ', 'RETURN_PROCEDURE', 'POLICY_GUIDANCE']);
const ACTIVE_FOLLOWUP = new Set(['OPEN', 'IN_PROGRESS']);
const FOLLOWUP_LABELS = { OPEN: '등록', IN_PROGRESS: '진행 중', DONE: '완료', CANCELLED: '취소' };
const STATUS_LABELS = {
  OPEN: '접수', REOPENED: '재문의 접수', CLASSIFIED: '분류 완료', VALIDATING: '확인 중',
  AUTO_READY: '안내 준비', ESCALATED: '사람 확인 대기', ASSIGNED: '담당자 확인 중',
  PENDING_APPROVAL: '답변 확인 중', FOLLOWUP_PENDING: '추가 확인 중', RESOLVED: '안내 완료',
};

function clone(value) { return structuredClone(value); }
function clock(value) {
  const n = value instanceof Date ? value.getTime() : Number(value);
  return Number.isFinite(n) && Math.abs(n) <= 8.64e15 ? n : Date.now();
}
function iso(now) { return new Date(now).toISOString(); }
function readableText(value) { return typeof value === 'string' ? value.trim() : ''; }
function isText(value, max = MAX_TEXT) { return typeof value === 'string' && value.trim().length > 0 && [...value].length <= max; }
function currentFinal(ticket) { return ticket.messages.find((m) => m.cycle === ticket.cycle && m.final && m.author !== 'CUSTOMER'); }
function hasBlockingFollowup(ticket) { return ticket.followups.some((f) => f.blocking && ACTIVE_FOLLOWUP.has(f.status)); }
function hasActiveFollowup(ticket) { return ticket.followups.some((f) => ACTIVE_FOLLOWUP.has(f.status)); }
function teamFor(category) {
  if (category === 'SHIPPING' || category === 'DELIVERY') return '배송팀';
  if (category === 'RETURN' || category === 'REFUND') return '반품환불팀';
  if (category === 'PRODUCT' || category === 'PAYMENT') return '상품결제팀';
  return '계정예외팀';
}
function ticketStateAfterHumanChange(ticket) {
  if (hasBlockingFollowup(ticket)) return 'FOLLOWUP_PENDING';
  if (currentFinal(ticket)) return 'RESOLVED';
  return ticket.draft.trim() ? 'PENDING_APPROVAL' : 'ASSIGNED';
}


function notice(state, kind, message) { state.notice = { kind, message }; return state; }
function bump(ticket, now) { ticket.version += 1; ticket.updatedAt = iso(now); }
function invalidateApproval(ticket) { ticket.approval = null; }
function addEvent(state, ticket, type, label, detail, now, metadata = {}) {
  const event = {
    id: `DEMO-EVENT-${String(++state.sequence.event).padStart(6, '0')}`,
    type, label, detail, createdAt: iso(now), ticketId: ticket?.id ?? null,
    cycle: ticket?.cycle ?? null, metadata,
  };
  state.events.push(event);
  if (ticket) ticket.events.push(event);
  return event;
}
function addMessage(state, ticket, author, text, final, now) {
  if (final && currentFinal(ticket)) return false;
  ticket.messages.push({
    id: `DEMO-MESSAGE-${String(++state.sequence.message).padStart(6, '0')}`,
    cycle: ticket.cycle, author, text, final, createdAt: iso(now),
  });
  return true;
}
function bareState(now) {
  return {
    schemaVersion: 'l2-l3-v2.1', mode: 'ISOLATED_SYNTHETIC_DEMO', storage: 'MEMORY_ONLY',
    createdAt: iso(now), updatedAt: iso(now), tickets: [], events: [], notice: null,
    lastCreatedTicketId: null, sequence: { ticket: 0, event: 0, message: 0, followup: 0, approval: 0 },
    automation: { enabled: true, version: 1, stopReason: null, regressionPassed: false, regression: null, updatedAt: iso(now) },
  };
}
function evidenceFor(scenario, state, now) {
  const policy = demoPolicies[scenario.policyKey];
  const hasOrder = scenario.orderRelevant && scenario.owned;
  return {
    source: DEMO_POLICY_SOURCE, checkedAt: iso(now), ruleVersion: state.automation.version,
    order: hasOrder ? {
      reference: 'DEMO-OWN-ORDER', status: 'IN_TRANSIT', statusLabel: '배송 중',
      fetchedAt: iso(now - scenario.queryAgeSeconds * 1000), version: 1, eta: null,
    } : null,
    policies: scenario.policyValid && policy ? [clone(policy)] : [],
    note: '새 v2 전용 합성 조회·정책입니다. 실제 주문 API 또는 정책 검색 결과가 아닙니다.',
  };
}
function checksFor(state, ticket, now, context = {}) {
  if (ticket.rag) return ragChecksFor(state, ticket, now, context);
  const scenario = getScenario(ticket.scenarioId);
  const rulesMatch = Boolean(scenario) && ticket.ruleSnapshotVersion === state.automation.version;
  const fetched = ticket.evidence?.order?.fetchedAt ? Date.parse(ticket.evidence.order.fetchedAt) : NaN;
  const age = now - fetched;
  const owned = Boolean(scenario?.owned && ticket.evidence?.order);
  const currentOrderVersion = ticket.evidence?.order?.version === 1;
  const orderNA = Boolean(scenario && !scenario.orderRelevant && ['GENERAL_FAQ','POLICY_GUIDANCE'].includes(scenario.allowKind));
  const policy = scenario ? demoPolicies[scenario.policyKey] : null;
  const policies = ticket.evidence?.policies ?? [];
  const policyOK = Boolean(scenario?.policyValid && policy && policies.length === 1 &&
    policies[0].id === policy.id && policies[0].version === policy.version && policies[0].active === true &&
    policies[0].clause === policy.clause && policies[0].text === policy.text);
  const templateOK = Boolean(scenario?.templateKey && ALLOW_KINDS.has(scenario.allowKind) &&
    (scenario.answer || scenario.allowKind === 'ORDER_STATUS'));
  const gate = (key, label, ok, yes, no, na = false) => ({ key, label, status: na ? 'NA' : ok ? 'PASS' : 'FAIL', detail: na ? yes : ok ? yes : no });
  return [
    gate('automation', '자동화 가동', state.automation.enabled, '합성 시연 자동화가 가동 중입니다.', '자동화가 중지되어 사람 확인으로 전환합니다.'),
    gate('rule_version', '현재 규칙 일치', rulesMatch, `시연 규칙 v${state.automation.version}가 일치합니다.`, '준비 당시와 현재의 규칙 버전이 다릅니다.'),
    gate('customer', '합성 고객 활성', Boolean(scenario?.customerActive), '고정 합성 고객이 활성 상태입니다.', '고객 활성 상태를 확인할 수 없습니다.'),
    gate('input_scope', '정의된 시연 입력', !ticket.customInput, '선택한 시나리오의 고정 질문입니다.', '변경한 자유 입력은 실제 분류 연결 전까지 사람 검토가 필요합니다.'),
    gate('allowlist', '허용 안내군', Boolean(scenario && ALLOW_KINDS.has(scenario.allowKind)) && !ticket.customInput, '허용된 네 가지 안내군에 해당합니다.', '허용된 정보 안내로 확인되지 않았습니다.'),
    gate('ownership', '본인 주문 확인', owned, orderNA ? '사전 정의된 주문 무관 안내로 검사가 적용되지 않습니다.' : '합성 본인 주문 연결이 확인되었습니다.', '주문 연결 권한을 확인할 수 없습니다.', orderNA),
    gate('fresh_lookup', '조회 60초 이내', owned && currentOrderVersion && Number.isFinite(age) && age >= 0 && age <= 60000, orderNA ? '주문 무관 안내에는 주문 조회를 사용하지 않습니다.' : '합성 조회 시각과 버전이 유효합니다.', '현재 유효한 주문 조회를 확보하지 못했습니다.', orderNA),
    gate('policy', '정책·조항 유효', policyOK, '등록된 합성 정책의 버전과 조항이 일치합니다.', '유효하고 일치하는 정책 근거가 없습니다.'),
    gate('template', '등록 안내 템플릿', templateOK && !ticket.customInput, '허용된 고정 안내 문장만 사용합니다.', '허용 템플릿과 입력의 일치를 확인할 수 없습니다.'),
    gate('prohibited_action', '금전·권리 결정 제외', Boolean(scenario && !scenario.highRisk), '환불·보상·계정 권리 실행을 포함하지 않습니다.', 'L3 환불·보상·계정 권리 결정은 자동 처리 범위에서 제외됩니다.'),
    gate('human_request', '사람 요청 우선', !ticket.humanRequested && ticket.route !== 'HUMAN', '고객의 사람 연결 요청이 없습니다.', '사람 요청 또는 이미 확정된 사람 처리 경로를 유지합니다.'),
    gate('followup', '미완료 후속 없음', !scenario?.requiresFollowup && !hasActiveFollowup(ticket), '사람이 수행해야 할 미완료 후속이 없습니다.', '남은 확인 업무가 있어 자동 안내만으로 종료할 수 없습니다.'),
    gate('minimum_data', '최소 정보 사용', !ticket.customInput, '고정 합성 질문과 허용 조회값만 사용합니다.', '자유 입력을 모델이나 외부 API로 보내지 않고 사람 검토로 남깁니다.'),
  ];
}

function ragChecksFor(state, ticket, now, context) {
  const rag = ticket.rag;
  const validation = context.ragValidation;
  const noOrderNeeded = ['GENERAL_FAQ', 'POLICY_GUIDANCE'].includes(rag.allowKind);
  const policyOK = Boolean(validation?.valid && validation.corpusVersion === rag.corpusVersion && rag.evidence?.length);
  const allowed = rag.eligible === true && ALLOW_KINDS.has(rag.allowKind);
  const gate = (key, label, ok, success, failure, na = false) => ({ key, label, status: na ? 'NA' : ok ? 'PASS' : 'FAIL', detail: na || ok ? success : failure });
  return [
    gate('automation', '자동화 가동', state.automation.enabled, '로컬 자동 안내가 가동 중입니다.', '자동화 중지 중에는 사람 확인으로 전환합니다.'),
    gate('rule_version', '현재 규칙 일치', ticket.ruleSnapshotVersion === state.automation.version, '현재 자동화 규칙 버전을 다시 확인했습니다.', '검색 준비 뒤 자동화 규칙이 변경되었습니다.'),
    gate('customer', '합성 고객 활성', context.customerActive === true, '등록된 합성 고객을 확인했습니다.', '합성 고객 활성 상태를 확인할 수 없습니다.'),
    gate('input_scope', '전체 문의 검증', context.ragTrusted === true && rag.queryHash === sha256(ticket.messages.filter((m) => m.author === 'CUSTOMER').at(-1)?.text ?? ''), '전체 입력과 검색 요청의 해시가 일치합니다.', '현재 문의와 검색 결과가 일치하지 않습니다.'),
    gate('allowlist', '허용 안내군', allowed, '문서 검색과 허용 안내군 검사를 통과했습니다.', '검색 결과가 허용된 안내 범위로 확인되지 않았습니다.'),
    gate('ownership', '본인 주문 확인', context.orderOwned === true, noOrderNeeded ? '주문 무관 안내로 주문을 조회하지 않습니다.' : '현재 합성 고객의 주문을 확인했습니다.', '현재 고객의 주문 소유권을 확인할 수 없습니다.', noOrderNeeded),
    gate('fresh_lookup', '조회 60초 이내', context.orderSnapshotValid === true, noOrderNeeded ? '주문 무관 안내에는 주문 조회를 사용하지 않습니다.' : '저장 직전 주문 버전·조회 시각을 다시 확인했습니다.', '주문 조회가 만료되었거나 주문 버전이 변경되었습니다.', noOrderNeeded),
    gate('policy', '정책·조항 유효', policyOK, '현재 문서 UUID·버전·해시·유효기간을 다시 확인했습니다.', '검색 후 문서가 변경되었거나 유효한 근거가 없습니다.'),
    gate('template', '검색 근거 안내문', allowed && isText(rag.reply) && typeof rag.templateKey === 'string' && rag.replyHash === sha256(rag.reply), '검색한 조항에 연결된 템플릿 안내문입니다.', '검증 가능한 템플릿 안내문이 없습니다.'),
    gate('prohibited_action', '금전·권리 결정 제외', rag.highRisk !== true && !rag.reasons?.some((reason) => reason.code === 'HIGH_RISK_ACTION'), '자동 환불·보상·계정 권리 변경을 실행하지 않습니다.', '금전·권리 결정 요청은 사람이 검토해야 합니다.'),
    gate('human_request', '사람 요청 우선', !ticket.humanRequested && ticket.route !== 'HUMAN', '사람 연결 요청이 없습니다.', '이미 요청한 사람 처리 경로를 유지합니다.'),
    gate('followup', '미완료 후속 없음', !hasActiveFollowup(ticket), '남은 후속 업무가 없습니다.', '후속 확인이 남아 자동 안내로 종료할 수 없습니다.'),
    gate('minimum_data', '합성 입력만 사용', context.syntheticInputChecked === true, '민감 식별정보 검사를 거친 합성 입력입니다.', '합성 입력 검사를 통과하지 않았습니다.'),
  ];
}

function attachRag(ticket, result, context, now) {
  ticket.rag = clone(result);
  ticket.rag.queryHash = sha256(ticket.messages.filter((m) => m.author === 'CUSTOMER').at(-1)?.text ?? '');
  ticket.rag.replyHash = result.reply ? sha256(result.reply) : null;
  const titles = {
    DELIVERY_STATUS: '배송 상태 문의', RETURN_STEPS: '반품 절차 문의', EXCHANGE_STEPS: '교환 절차 문의',
    TICKET_ANSWER_FAQ: '문의 답변 확인', ORDER_FREE_INQUIRY: '일반 문의 접수',
    REFUND_REVIEW: '환불 요청 검토', COMPENSATION_REVIEW: '보상 요청 검토',
    ACCOUNT_RIGHTS_REVIEW: '계정 권리 확인', HUMAN_HANDOFF: '상담사 연결 요청', PAYMENT_REVIEW: '결제 문의 검토',
  };
  ticket.subject = titles[result.intent] ?? '상담이 필요한 문의';
  ticket.category = result.category === 'SHIPPING' ? 'DELIVERY' : result.category || 'UNKNOWN';
  ticket.team = teamFor(ticket.category);
  ticket.customInput = true;
  ticket.humanRequested = ticket.humanRequested || result.humanRequested === true;
  ticket.priority = result.highRisk ? 'HIGH' : 'NORMAL';
  ticket.slaDueAt = iso(now + (ticket.priority === 'HIGH' ? 60 : 240) * 60000);
  ticket.evidence = {
    source: 'LOCAL_BM25_RETRIEVAL', checkedAt: iso(now), ruleVersion: ticket.ruleSnapshotVersion,
    order: context.orderOwned ? clone(context.order) : null,
    policies: (result.evidence ?? []).map((item) => ({ ...clone(item), id: item.documentId, clause: item.clauseId })),
    note: 'v2 개발용 합성 문서에서 실제 검색한 근거입니다. 팀의 운영 정책 또는 외부 주문 조회가 아닙니다.',
  };
}

function evidenceFingerprint(ticket) {
  return sha256(JSON.stringify({ policies: ticket.evidence?.policies ?? [], order: ticket.evidence?.order ?? null,
    ruleVersion: ticket.ruleSnapshotVersion, corpusVersion: ticket.rag?.corpusVersion ?? null }));
}
const gateReasonCodes = {
  automation: 'AUTOMATION_STOPPED', rule_version: 'RULE_CHANGED', customer: 'CUSTOMER_UNVERIFIED',
  input_scope: 'CUSTOM_INPUT_REVIEW', allowlist: 'NOT_ALLOWLISTED', ownership: 'OWNERSHIP_UNVERIFIED',
  fresh_lookup: 'LOOKUP_NOT_FRESH', policy: 'POLICY_UNAVAILABLE', template: 'TEMPLATE_UNVERIFIED',
  prohibited_action: 'HIGH_RISK_ACTION', human_request: 'HUMAN_REQUESTED', followup: 'REQUIRED_FOLLOWUP',
  minimum_data: 'MINIMUM_DATA_REVIEW',
};
function handoff(state, ticket, reasons, now) {
  ticket.route = 'HUMAN'; ticket.resolutionMode = null;
  ticket.status = ticket.assignee ? ticketStateAfterHumanChange(ticket) : 'ESCALATED';
  ticket.handoffReasons = reasons;
  invalidateApproval(ticket); bump(ticket, now);
  addEvent(state, ticket, 'HANDOFF', '사람 확인으로 이관', '사유 코드를 남기고 합성 팀 대기열에 유지합니다.', now,
    { reasonCodes: reasons.map((r) => r.code), team: ticket.team });
}
function newTicket(state, scenario, body, now) {
  const changedBody = body.trim() !== scenario.body;
  const category = changedBody ? 'UNKNOWN' : scenario.category;
  const number = ++state.sequence.ticket;
  const ticket = {
    id: `DEMO-${String(number).padStart(4, '0')}`, subject: changedBody ? '자유 입력 검토' : scenario.title,
    customerRef: 'DEMO-CUSTOMER-001', category, cycle: 1, version: 1, status: 'OPEN', route: 'AUTO',
    scenarioId: scenario.id, customInput: changedBody, humanRequested: false, resolutionMode: null,
    gates: [], handoffReasons: [], messages: [], assignee: null, team: teamFor(category),
    approval: null, draft: '', draftRevision: 0, followupRevision: 0, followups: [], events: [],
    priority: scenario.priority, createdAt: iso(now), updatedAt: iso(now),
    slaDueAt: iso(now + (scenario.priority === 'HIGH' ? 60 : 240) * 60000),
    ruleSnapshotVersion: scenario.ruleSnapshotMismatch ? state.automation.version - 1 : state.automation.version,
    evidence: evidenceFor(scenario, state, now),
  };
  state.tickets.unshift(ticket); state.lastCreatedTicketId = ticket.id;
  addMessage(state, ticket, 'CUSTOMER', body.trim(), false, now);
  addEvent(state, ticket, 'RECEIVED', '문의 접수', '새 합성 문의와 회차를 만들었습니다.', now, { scenarioId: scenario.id, customInput: changedBody });
  if (!state.automation.enabled) {
    ticket.gates = checksFor(state, ticket, now);
    handoff(state, ticket, [{ code: 'AUTOMATION_STOPPED', label: '자동화 중지', detail: '중지 중 접수한 문의는 사람 대기열에 남깁니다.' }], now);
  }
  return ticket;
}

function approvalError(ticket, now) {
  const approval = ticket.approval;
  if (!approval) return '현재 초안의 검토 승인이 필요합니다.';
  if (approval.used) return '이미 사용한 승인으로 다시 답변할 수 없습니다.';
  if (Date.parse(approval.expiresAt) <= now) return '승인 후 10분이 지나 다시 검토해야 합니다.';
  if (approval.cycle !== ticket.cycle || approval.ticketVersion !== ticket.version ||
      approval.draftRevision !== ticket.draftRevision || approval.followupRevision !== ticket.followupRevision ||
      approval.draftHash !== sha256(ticket.draft) || approval.approvedText !== ticket.draft ||
      approval.evidenceHash !== evidenceFingerprint(ticket)) {
    return '회차·본문·후속 또는 버전이 바뀌어 이전 승인을 사용할 수 없습니다.';
  }
  return null;
}

/** Apply one action without mutating the supplied state. Invalid operations return a notice. */
export function dispatchOperation(previous, action, suppliedNow = Date.now(), context = {}) {
  const now = clock(suppliedNow);
  if (!previous || !Array.isArray(previous.tickets) || !previous.automation) {
    return notice(bareState(now), 'error', '시연 상태가 유효하지 않습니다. 초기화 후 다시 진행해 주세요.');
  }
  const state = clone(previous);
  state.updatedAt = iso(now); state.notice = null;
  if (!action || typeof action.type !== 'string') return notice(state, 'error', '실행할 작업을 확인할 수 없습니다.');
  if (action.type === 'RESET') return createInitialState(now);

  if (action.type === 'CREATE_RAG_CASE') {
    if (!context.ragTrusted || !context.ragResult || !isText(action.body)) return notice(state, 'error', '서버에서 검증한 문서 검색 결과가 필요합니다.');
    if (state.tickets.length >= 100) return notice(state, 'error', '합성 문의 100건에 도달했습니다. 시연을 초기화해 주세요.');
    const map = { ORDER_STATUS: 'shipping_status', GENERAL_FAQ: 'general_faq', RETURN_PROCEDURE: 'return_procedure', POLICY_GUIDANCE: 'policy_guidance' };
    const scenario = getScenario(map[context.ragResult.allowKind] ?? 'general_faq');
    const ticket = newTicket(state, scenario, action.body, now);
    ticket.customerRef = context.customerRef ?? 'DEMO-CUSTOMER-001';
    attachRag(ticket, context.ragResult, context, now);
    addEvent(state, ticket, 'RAG_RETRIEVED', '문서 검색 완료', '전체 문의로 로컬 문서를 검색하고 문서 식별자와 버전을 기록했습니다.', now,
      { mode: context.ragResult.mode, corpusVersion: context.ragResult.corpusVersion, documents: ticket.evidence.policies.length });
    if (ticket.humanRequested && ticket.route === 'AUTO') handoff(state, ticket,
      [{ code: 'HUMAN_REQUESTED', label: '고객의 사람 연결 요청', detail: '직접 작성한 사람 상담 요청을 우선합니다.' }], now);
    return notice(state, 'success', `${ticket.id}를 접수하고 관련 문서를 검색했습니다.`);
  }

  if (action.type === 'CREATE_CASE') {
    const scenario = getScenario(action.scenarioId);
    if (!scenario) return notice(state, 'error', '등록된 합성 시나리오를 선택해 주세요.');
    const body = action.body === undefined ? scenario.body : action.body;
    if (!isText(body)) return notice(state, 'error', '문의는 1~10,000자의 텍스트로 입력해 주세요.');
    if (state.tickets.length >= 100) return notice(state, 'error', '합성 문의 100건에 도달했습니다. 시연을 초기화해 주세요.');
    const ticket = newTicket(state, scenario, body, now);
    return notice(state, 'success', `${ticket.id}를 접수했습니다. 시연 처리 결과를 확인할 수 있습니다.`);
  }
  if (action.type === 'STOP_AUTOMATION') {
    if (!state.automation.enabled) return notice(state, 'info', '자동화는 이미 중지되어 있습니다.');
    if (!isText(action.reason, 500)) return notice(state, 'error', '중지 사유를 1~500자로 입력해 주세요.');
    state.automation.enabled = false; state.automation.version += 1;
    state.automation.stopReason = action.reason.trim(); state.automation.regressionPassed = false;
    state.automation.regression = null; state.automation.updatedAt = iso(now);
    addEvent(state, null, 'AUTOMATION_STOPPED', '자동화 중지', '대기 중인 자동 문의를 사람 경로로 전환했습니다.', now, { ruleVersion: state.automation.version });
    let count = 0;
    for (const ticket of state.tickets) {
      if (ticket.route === 'AUTO' && !currentFinal(ticket)) {
        ticket.gates = checksFor(state, ticket, now);
        handoff(state, ticket, [{ code: 'AUTOMATION_STOPPED', label: '자동화 중지', detail: '가동 중지에 따라 사람 확인이 필요합니다.' }], now);
        count += 1;
      }
    }
    return notice(state, 'success', `시연 자동화를 중지했습니다. 대기 ${count}건을 사람 큐로 옮겼습니다.`);
  }
  if (action.type === 'RUN_REGRESSION') {
    if (state.automation.enabled) return notice(state, 'error', '자동화를 중지한 뒤 재개 전 검사를 실행해 주세요.');
    const checks = regressionChecks(now);
    state.automation.regressionPassed = checks.every((check) => check.passed);
    state.automation.regression = { ranAt: iso(now), passed: state.automation.regressionPassed, ruleVersion: state.automation.version, checks };
    addEvent(state, null, 'REGRESSION_CHECKED', '시연 안전 회귀 검사', '같은 상태 엔진을 별도 메모리 상태에서 실행해 검사했습니다.', now,
      { checks: checks.length, passed: checks.filter((check) => check.passed).length });
    return notice(state, state.automation.regressionPassed ? 'success' : 'error',
      `${checks.filter((check) => check.passed).length}/${checks.length} 시연 검사를 통과했습니다. 실제 DB·권한 검증 결과는 포함하지 않습니다.`);
  }
  if (action.type === 'RESUME_AUTOMATION') {
    if (state.automation.enabled) return notice(state, 'info', '자동화가 이미 가동 중입니다.');
    if (!state.automation.regressionPassed || !state.automation.regression?.passed ||
        state.automation.regression.ruleVersion !== state.automation.version) {
      return notice(state, 'error', '현재 중지 상태의 시연 회귀 검사를 통과한 뒤 명시적으로 재개해 주세요.');
    }
    state.automation.enabled = true; state.automation.version += 1; state.automation.updatedAt = iso(now);
    addEvent(state, null, 'AUTOMATION_RESUMED', '자동화 재개', '검사 결과 확인 후 새 문의의 자동 안내를 재개했습니다. 기존 사람 큐는 유지합니다.', now, { ruleVersion: state.automation.version });
    return notice(state, 'success', '시연 자동화를 재개했습니다. 이미 사람에게 넘어간 문의는 사람 경로에 유지됩니다.');
  }

  const ticket = state.tickets.find((item) => item.id === action.ticketId);
  if (!ticket) return notice(state, 'error', '현재 시연에서 해당 문의를 찾을 수 없습니다.');
  if ((action.expectedVersion !== undefined && action.expectedVersion !== ticket.version) ||
      (action.expectedCycle !== undefined && action.expectedCycle !== ticket.cycle)) {
    return notice(state, 'error', '문의의 회차 또는 버전이 변경되었습니다. 현재 상태를 확인하고 다시 진행해 주세요.');
  }

  if (action.type === 'RUN_AUTO') {
    if (currentFinal(ticket)) return notice(state, 'info', '이번 회차의 확정 답변이 이미 있습니다. 새 답변을 만들지 않았습니다.');
    if (ticket.route === 'HUMAN' || ticket.humanRequested) return notice(state, 'error', '사람 확인으로 전환된 문의는 자동 경로로 되돌리지 않습니다.');
    ticket.gates = checksFor(state, ticket, now, context);
    const failures = ticket.gates.filter((gate) => gate.status === 'FAIL');
    addEvent(state, ticket, 'GATES_CHECKED', '자동 안내 조건 확인', '합성 입력·조회·정책·현재 회차의 허용 조건을 검사했습니다.', now,
      { passed: ticket.gates.filter((g) => g.status === 'PASS').length, failed: failures.length });
    if (failures.length) {
      const reasons = failures.map((gate) => ({ code: gateReasonCodes[gate.key], label: gate.label, detail: gate.detail }));
      for (const reason of ticket.rag?.reasons ?? []) if (!reasons.some((item) => item.code === reason.code)) reasons.push({ ...reason, label: reason.detail });
      handoff(state, ticket, reasons, now);
      return notice(state, 'info', '자동 안내 조건을 충족하지 못해 사유와 함께 사람 큐로 옮겼습니다.');
    }
    const scenario = getScenario(ticket.scenarioId);
    const text = ticket.rag ? ticket.rag.reply : scenario.answer || getScenario('shipping_status').answer;
    if (!addMessage(state, ticket, 'SYSTEM', text, true, now)) return notice(state, 'info', '이미 확정된 답변을 유지합니다.');
    ticket.status = 'RESOLVED'; ticket.route = 'AUTO'; ticket.resolutionMode = 'AUTO'; bump(ticket, now);
    ticket.systemDecision = { mode: 'SYSTEM', ruleVersion: state.automation.version, cycle: ticket.cycle, contentHash: sha256(text), decidedAt: iso(now) };
    addEvent(state, ticket, 'AUTO_COMPLETED', '자동 안내 완료', '합성 문의 회차에 안내 한 건을 확정했습니다. 실제 주문 조치는 실행하지 않았습니다.', now,
      { mode: 'SYSTEM', ruleVersion: state.automation.version, contentHash: ticket.systemDecision.contentHash });
    return notice(state, 'success', '검증된 합성 안내를 한 번 확정했습니다. 고객 공개 결과를 확인해 주세요.');
  }

  if (action.type === 'REOPEN') {
    const scenario = getScenario(action.scenarioId ?? ticket.scenarioId);
    if (!scenario) return notice(state, 'error', '재문의에 사용할 합성 시나리오를 선택해 주세요.');
    const body = action.body === undefined ? scenario.body : action.body;
    if (!isText(body)) return notice(state, 'error', '재문의는 1~10,000자의 텍스트로 입력해 주세요.');
    const preserveHuman = ticket.route === 'HUMAN' || ticket.humanRequested;
    ticket.cycle += 1; ticket.scenarioId = scenario.id; ticket.customInput = body.trim() !== scenario.body;
    ticket.subject = ticket.customInput ? '자유 입력 검토' : scenario.title;
    ticket.category = ticket.customInput ? 'UNKNOWN' : scenario.category; ticket.team = teamFor(ticket.category);
    ticket.draft = ''; ticket.draftRevision += 1; ticket.assignee = null; invalidateApproval(ticket);
    ticket.gates = []; ticket.handoffReasons = []; ticket.systemDecision = null; ticket.resolutionMode = null;
    ticket.route = preserveHuman ? 'HUMAN' : 'AUTO'; ticket.status = 'REOPENED';
    ticket.priority = scenario.priority; ticket.slaDueAt = iso(now + (scenario.priority === 'HIGH' ? 60 : 240) * 60000);
    delete ticket.rag;
    ticket.evidence = evidenceFor(scenario, state, now);
    ticket.ruleSnapshotVersion = scenario.ruleSnapshotMismatch ? state.automation.version - 1 : state.automation.version;
    bump(ticket, now); addMessage(state, ticket, 'CUSTOMER', body.trim(), false, now);
    if (context.ragTrusted && context.ragResult) attachRag(ticket, context.ragResult, context, now);
    addEvent(state, ticket, 'REOPENED', '새 회차 접수', '이전 회차의 승인과 자동 작업 결과를 새 회차에 사용하지 않습니다.', now, { scenarioId: scenario.id });
    if (preserveHuman || ticket.humanRequested || !state.automation.enabled) {
      handoff(state, ticket, [{ code: ticket.humanRequested ? 'HUMAN_REQUESTED' : preserveHuman ? 'HUMAN_CONTINUATION' : 'AUTOMATION_STOPPED', label: '사람 처리 유지', detail: '사람 처리 경로 또는 중지 상태에 따라 사람 큐에 유지합니다.' }], now);
    }
    return notice(state, 'success', `${ticket.cycle}회차로 접수했습니다. 이전 승인과 답변은 이 회차에 재사용되지 않습니다.`);
  }

  if (action.type === 'REQUEST_HUMAN') {
    if (ticket.humanRequested && !currentFinal(ticket)) return notice(state, 'info', '이미 사람 연결을 요청했습니다. 현재 대기 상태를 유지합니다.');
    const wasAnswered = Boolean(currentFinal(ticket));
    ticket.cycle += 1; ticket.humanRequested = true; ticket.draft = ''; ticket.draftRevision += 1;
    ticket.assignee = null; ticket.systemDecision = null; ticket.gates = []; invalidateApproval(ticket);
    if (wasAnswered) ticket.slaDueAt = iso(now + (ticket.priority === 'HIGH' ? 60 : 240) * 60000);
    addMessage(state, ticket, 'CUSTOMER', '상담사 연결을 요청합니다.', false, now);
    handoff(state, ticket, [{ code: 'HUMAN_REQUESTED', label: '고객의 사람 연결 요청', detail: '자동 처리로 되돌리지 않고 사람 확인을 기다립니다.' }], now);
    return notice(state, 'success', '새 회차에서 사람 연결을 요청했습니다. 기존 자동 응답은 다시 보내지 않습니다.');
  }

  if (action.type === 'CLAIM') {
    if (ticket.route !== 'HUMAN' || currentFinal(ticket)) return notice(state, 'error', '답변 전 사람 대기 문의를 인수할 수 있습니다.');
    if (ticket.assignee === MANAGER) return notice(state, 'info', '이 문의는 현재 합성 운영 담당자가 처리 중입니다.');
    ticket.assignee = MANAGER; ticket.draft = ticket.draft || '요청 내용을 확인하고 있습니다. 필요한 확인을 거쳐 안내하겠습니다.';
    ticket.draftRevision += 1; invalidateApproval(ticket); ticket.status = ticketStateAfterHumanChange(ticket); bump(ticket, now);
    addEvent(state, ticket, 'CLAIMED', '운영 담당자 인수', '합성 운영 담당자에게 배정했습니다. 같은 회차의 첫 응답 기한은 유지합니다.', now, { assignee: MANAGER, team: ticket.team });
    return notice(state, 'success', '합성 운영 담당자가 인수했습니다. 초안과 근거를 확인해 주세요.');
  }

  if (!['SAVE_DRAFT','APPROVE','SEND_HUMAN','ADD_FOLLOWUP','UPDATE_FOLLOWUP'].includes(action.type)) {
    return notice(state, 'error', '지원하지 않는 시연 작업입니다.');
  }
  if (ticket.route !== 'HUMAN' || ticket.assignee !== MANAGER) return notice(state, 'error', '사람 경로의 문의를 먼저 인수해 주세요.');

  if (action.type === 'SAVE_DRAFT') {
    if (currentFinal(ticket)) return notice(state, 'error', '확정된 답변은 덮어쓰지 않습니다. 새 회차에서 답변해 주세요.');
    if (!isText(action.text)) return notice(state, 'error', '초안은 1~10,000자의 텍스트로 입력해 주세요.');
    const text = action.text.trim();
    if (text === ticket.draft) return notice(state, 'info', '변경된 초안이 없어 현재 검토 상태를 유지합니다.');
    ticket.draft = text; ticket.draftRevision += 1; invalidateApproval(ticket); ticket.status = ticketStateAfterHumanChange(ticket); bump(ticket, now);
    addEvent(state, ticket, 'DRAFT_SAVED', '초안 수정', '초안 수정으로 이전 승인을 무효화했습니다. 아직 고객에게 공개되지 않았습니다.', now, { revision: ticket.draftRevision });
    return notice(state, 'success', '초안을 저장했습니다. 수정한 내용으로 다시 검토 승인해 주세요.');
  }

  if (action.type === 'APPROVE') {
    if (currentFinal(ticket)) return notice(state, 'error', '이미 확정 답변이 있어 이 회차를 다시 승인하지 않습니다.');
    if (!isText(ticket.draft)) return notice(state, 'error', '내용이 있는 초안을 준비한 뒤 검토 승인해 주세요.');
    if (ticket.rag?.evidence?.length && context.ragValidation?.valid !== true) return notice(state, 'error', '현재 유효한 문서 근거로 다시 검토해 주세요. 변경된 근거로 승인할 수 없습니다.');
    if (getScenario(ticket.scenarioId)?.requiresFollowup && !ticket.followups.some((f) => f.cycle === ticket.cycle && f.blocking)) {
      return notice(state, 'error', '필수 확인이 필요한 시나리오입니다. 이번 회차의 필수 후속을 먼저 등록해 주세요.');
    }
    bump(ticket, now);
    ticket.approval = {
      id: `DEMO-APPROVAL-${String(++state.sequence.approval).padStart(5, '0')}`, mode: 'HUMAN',
      cycle: ticket.cycle, ticketVersion: ticket.version, draftRevision: ticket.draftRevision,
      draftHash: sha256(ticket.draft), contentHash: sha256(ticket.draft), approvedText: ticket.draft,
      evidenceHash: evidenceFingerprint(ticket),
      followupRevision: ticket.followupRevision, ruleVersion: state.automation.version,
      approvedAt: iso(now), expiresAt: iso(now + 600000), used: false,
    };
    addEvent(state, ticket, 'HUMAN_APPROVED', '사람 검토 승인', '현재 회차·본문·후속 상태의 검토 승인을 기록했습니다. 아직 고객 답변을 확정하지 않았습니다.', now,
      { approvalId: ticket.approval.id, mode: 'HUMAN', contentHash: ticket.approval.contentHash });
    return notice(state, 'success', '현재 초안을 승인했습니다. 10분 안에 답변을 확정할 수 있습니다.');
  }

  if (action.type === 'SEND_HUMAN') {
    if (currentFinal(ticket)) return notice(state, 'info', '이번 회차의 확정 답변이 이미 있어 중복 답변을 만들지 않았습니다.');
    const error = approvalError(ticket, now);
    if (error) return notice(state, 'error', error);
    if (ticket.rag?.evidence?.length && context.ragValidation?.valid !== true) {
      return notice(state, 'error', '검토에 사용한 문서가 변경되거나 만료되었습니다. 새 근거로 다시 검토해 주세요.');
    }
    addMessage(state, ticket, 'AGENT', ticket.draft, true, now); ticket.approval.used = true;
    ticket.resolutionMode = 'HUMAN'; ticket.status = hasBlockingFollowup(ticket) ? 'FOLLOWUP_PENDING' : 'RESOLVED'; bump(ticket, now);
    addEvent(state, ticket, 'HUMAN_REPLIED', '사람 답변 확정', '현재 회차의 합성 고객 화면에 답변 한 건을 확정했습니다.', now,
      { approvalId: ticket.approval.id, mode: 'HUMAN', hasBlockingFollowup: hasBlockingFollowup(ticket) });
    return notice(state, 'success', ticket.status === 'FOLLOWUP_PENDING'
      ? '합성 답변을 확정했습니다. 필수 후속이 남아 추가 확인 중으로 유지합니다.'
      : '합성 답변을 한 번 확정하고 안내 완료로 표시했습니다.');
  }

  if (action.type === 'ADD_FOLLOWUP') {
    if (!isText(action.title, 160)) return notice(state, 'error', '후속 제목을 1~160자로 입력해 주세요.');
    if ((action.publicNote !== undefined && (typeof action.publicNote !== 'string' || [...action.publicNote].length > 3000)) ||
        (action.internalNote !== undefined && (typeof action.internalNote !== 'string' || [...action.internalNote].length > 3000))) {
      return notice(state, 'error', '후속 메모는 각각 3,000자 이하의 텍스트로 입력해 주세요.');
    }
    const due = action.dueAt === undefined ? now + 86400000 : Date.parse(action.dueAt);
    if (!Number.isFinite(due)) return notice(state, 'error', '유효한 후속 기한을 입력해 주세요.');
    const followup = {
      id: `DEMO-FOLLOWUP-${String(++state.sequence.followup).padStart(5, '0')}`,
      title: action.title.trim(), cycle: ticket.cycle, status: 'OPEN', blocking: action.blocking === true,
      publicNote: readableText(action.publicNote), internalNote: readableText(action.internalNote),
      owner: ticket.assignee, dueAt: iso(due), version: 1, createdAt: iso(now), updatedAt: iso(now), cancellationReason: null,
    };
    ticket.followups.push(followup); ticket.followupRevision += 1; invalidateApproval(ticket);
    ticket.status = ticketStateAfterHumanChange(ticket); bump(ticket, now);
    addEvent(state, ticket, 'FOLLOWUP_ADDED', '후속 등록', '공개 내용과 내부 메모를 분리해 등록했습니다. 이전 승인은 다시 검토해야 합니다.', now,
      { followupId: followup.id, blocking: followup.blocking, owner: followup.owner });
    return notice(state, 'success', '후속을 등록했습니다. 변경된 조건으로 답변을 다시 검토해 주세요.');
  }

  const followup = ticket.followups.find((item) => item.id === action.followupId);
  if (!followup) return notice(state, 'error', '해당 문의의 후속을 찾을 수 없습니다.');
  if (action.expectedFollowupVersion !== undefined && action.expectedFollowupVersion !== followup.version) {
    return notice(state, 'error', '후속 버전이 변경되었습니다. 현재 후속을 확인해 주세요.');
  }
  if (followup.status === action.status) return notice(state, 'info', '후속이 이미 요청한 상태입니다.');
  const transitions = { OPEN: ['IN_PROGRESS','CANCELLED'], IN_PROGRESS: ['DONE','CANCELLED'], DONE: [], CANCELLED: [] };
  if (!transitions[followup.status]?.includes(action.status)) return notice(state, 'error', '등록 → 진행 → 완료 또는 등록·진행 → 취소 순서로 변경해 주세요. 종료된 후속은 다시 열지 않습니다.');
  if (action.status === 'CANCELLED' && !isText(action.reason, 500)) return notice(state, 'error', '후속 취소 사유를 1~500자로 입력해 주세요.');
  followup.status = action.status; followup.version += 1; followup.updatedAt = iso(now);
  if (action.status === 'CANCELLED') followup.cancellationReason = action.reason.trim();
  ticket.followupRevision += 1; invalidateApproval(ticket); ticket.status = ticketStateAfterHumanChange(ticket); bump(ticket, now);
  addEvent(state, ticket, 'FOLLOWUP_UPDATED', '후속 상태 변경', '필수 후속과 현재 회차의 확정 답변 유무를 다시 확인했습니다.', now,
    { followupId: followup.id, status: followup.status, blocking: followup.blocking });
  return notice(state, 'success', ticket.status === 'RESOLVED' ? '필수 후속과 확정 답변을 확인하고 안내 완료로 전환했습니다.' : '후속 상태를 반영했습니다. 남은 업무와 답변 상태를 확인해 주세요.');
}

/** Seed four linked fictional cases; all counters derive from these cases. */
export function createInitialState(suppliedNow = Date.now()) {
  const now = clock(suppliedNow);
  let state = bareState(now);
  const apply = (action, time) => { state = dispatchOperation(state, action, time); };
  apply({ type: 'CREATE_CASE', scenarioId: 'shipping_status' }, now - 18 * 60000);
  apply({ type: 'RUN_AUTO', ticketId: state.lastCreatedTicketId }, now - 18 * 60000 + 1000);
  apply({ type: 'CREATE_CASE', scenarioId: 'refund_request' }, now - 75 * 60000);
  apply({ type: 'RUN_AUTO', ticketId: state.lastCreatedTicketId }, now - 75 * 60000 + 1000);
  apply({ type: 'CREATE_CASE', scenarioId: 'ownership_unverified' }, now - 12 * 60000);
  apply({ type: 'RUN_AUTO', ticketId: state.lastCreatedTicketId }, now - 12 * 60000 + 1000);
  apply({ type: 'CREATE_CASE', scenarioId: 'required_followup' }, now - 35 * 60000);
  const followupTicket = state.lastCreatedTicketId;
  apply({ type: 'RUN_AUTO', ticketId: followupTicket }, now - 35 * 60000 + 1000);
  apply({ type: 'CLAIM', ticketId: followupTicket }, now - 34 * 60000);
  apply({ type: 'ADD_FOLLOWUP', ticketId: followupTicket, title: '합성 배송 상태 추가 확인', blocking: true,
    publicNote: '담당자가 배송 관련 내용을 추가로 확인하고 있습니다.', internalNote: '시연 내부 확인 메모', dueAt: iso(now + 2 * 3600000) }, now - 33 * 60000);
  apply({ type: 'APPROVE', ticketId: followupTicket }, now - 32 * 60000);
  apply({ type: 'SEND_HUMAN', ticketId: followupTicket }, now - 31 * 60000);
  state.notice = null; state.updatedAt = iso(now);
  return state;
}

/** Counts are computed from this memory-only case ledger, never fabricated KPI constants. */
export function deriveMetrics(state, suppliedNow = Date.parse(state.updatedAt)) {
  const now = clock(suppliedNow);
  const tickets = state.tickets;
  const finals = tickets.flatMap((t) => t.messages.filter((m) => m.final && m.author !== 'CUSTOMER'));
  const autoCompletedCycles = finals.filter((m) => m.author === 'SYSTEM').length;
  const humanCompletedCycles = finals.filter((m) => m.author === 'AGENT').length;
  return {
    total: tickets.length,
    reviewPending: tickets.filter((t) => t.route === 'HUMAN' && !t.assignee && !currentFinal(t)).length,
    assigned: tickets.filter((t) => t.route === 'HUMAN' && t.assignee && t.status !== 'RESOLVED').length,
    inProgress: tickets.filter((t) => t.route === 'HUMAN' && t.assignee && !currentFinal(t)).length,
    followupPending: tickets.filter((t) => t.status === 'FOLLOWUP_PENDING').length,
    openFollowups: tickets.reduce((n,t) => n + t.followups.filter((f) => ACTIVE_FOLLOWUP.has(f.status)).length, 0),
    resolved: tickets.filter((t) => t.status === 'RESOLVED').length,
    autoCompleted: tickets.filter((t) => t.status === 'RESOLVED' && t.resolutionMode === 'AUTO').length,
    humanCompleted: tickets.filter((t) => t.status === 'RESOLVED' && t.resolutionMode === 'HUMAN').length,
    awaitingAutomation: tickets.filter((t) => t.route === 'AUTO' && !currentFinal(t)).length,
    blockedL3: tickets.filter((t) => t.handoffReasons.some((r) => r.code === 'HIGH_RISK_ACTION')).length,
    overdue: tickets.filter((t) => !currentFinal(t) && Date.parse(t.slaDueAt) < now).length,
    completedCycles: finals.length, autoCompletedCycles, humanCompletedCycles,
    autoCompletionRate: finals.length ? autoCompletedCycles / finals.length : null,
    automationEnabled: state.automation.enabled,
  };
}

/** A strict allowlist projection for the synthetic customer screen. */
export function getCustomerView(state, ticketId) {
  const ticket = state.tickets.find((item) => item.id === ticketId);
  if (!ticket) return null;
  const hasReply = Boolean(currentFinal(ticket));
  const resolved = ticket.status === 'RESOLVED';
  const human = ticket.route === 'HUMAN';
  const labels = human
    ? [['received','접수'],['checked','담당자 확인'],['answered','답변'],['completed','안내 완료']]
    : [['received','접수'],['checked','조건 확인'],['answered','답변'],['completed','안내 완료']];
  // No draft, approval, internal memo, gate failure, assignment, or event is exposed.
  return {
    id: ticket.id, subject: ticket.subject, cycle: ticket.cycle, version: ticket.version,
    status: ticket.status, route: ticket.route, statusLabel: STATUS_LABELS[ticket.status] || '확인 중',
    notice: resolved ? '문의 안내가 완료되었습니다. 추가 질문이나 사람 연결을 요청할 수 있습니다.'
      : hasBlockingFollowup(ticket) ? '담당자가 필요한 내용을 추가로 확인하고 있습니다.'
      : human ? '담당자의 확인을 기다리고 있습니다. 확정된 답변이 준비되면 이 화면에 표시됩니다.'
      : '문의가 접수되었습니다. 확인이 끝난 확정 답변을 이 화면에서 확인할 수 있습니다.',
    progress: labels.map(([key,label], i) => ({ key, label,
      state: i === 0 || resolved || (i === 1 && hasReply) || (i === 2 && hasReply) ? 'done'
        : i === 1 || (i === 3 && hasReply) ? 'current' : 'pending' })),
    messages: ticket.messages.filter((m) => m.author === 'CUSTOMER' || m.final).map(({ id, cycle, author, text, final, createdAt }) =>
      ({ id, cycle, author, text, final, createdAt })),
    followups: ticket.followups.map(({ id, status, publicNote, updatedAt, dueAt }) =>
      ({ id, status, statusLabel: FOLLOWUP_LABELS[status], publicNote, updatedAt, dueAt })),
    canReopen: true, canRequestHuman: !(ticket.humanRequested && !hasReply), isSimulation: true,
  };
}

/** Real calls into this engine on isolated states; not production backend tests. */
function regressionChecks(now) {
  const results = [];
  const check = (id, title, execute) => {
    try {
      const passed = execute() === true;
      results.push({ id, title, passed, detail: passed ? '격리된 시연 상태 엔진에서 기대 결과를 확인했습니다.' : '시연 기대 결과와 일치하지 않습니다.' });
    } catch {
      results.push({ id, title, passed: false, detail: '시연 검사 실행 중 오류가 발생했습니다.' });
    }
  };
  const make = (scenarioId, body) => {
    let s = dispatchOperation(bareState(now), { type: 'CREATE_CASE', scenarioId, ...(body === undefined ? {} : { body }) }, now);
    return { state: s, id: s.lastCreatedTicketId };
  };
  check('four_allowed_groups', 'L2 네 안내군', () => ['shipping_status','general_faq','return_procedure','policy_guidance'].every((scenarioId) => {
    const { state, id } = make(scenarioId);
    const s = dispatchOperation(state, { type: 'RUN_AUTO', ticketId: id }, now + 1);
    return s.tickets[0].status === 'RESOLVED' && s.tickets[0].messages.filter((m) => m.final).length === 1;
  }));
  check('l3_handoff', 'L3 요청 자동 결정 차단', () => ['refund_request','compensation_request','account_rights'].every((scenarioId) => {
    const { state, id } = make(scenarioId);
    const s = dispatchOperation(state, { type: 'RUN_AUTO', ticketId: id }, now + 1);
    return s.tickets[0].route === 'HUMAN' && !currentFinal(s.tickets[0]);
  }));
  check('edited_question', '자유 입력 허가 우회 차단', () => {
    const { state, id } = make('general_faq', '환불을 승인해 주세요.');
    const s = dispatchOperation(state, { type: 'RUN_AUTO', ticketId: id }, now + 1);
    return s.tickets[0].category === 'UNKNOWN' && s.tickets[0].route === 'HUMAN' && !currentFinal(s.tickets[0]);
  });
  check('evidence_failures', '소유권·근거·신선도·규칙 실패', () => ['ownership_unverified','missing_policy','stale_lookup','rule_changed'].every((scenarioId) => {
    const { state, id } = make(scenarioId);
    const s = dispatchOperation(state, { type: 'RUN_AUTO', ticketId: id }, now + 1);
    return s.tickets[0].route === 'HUMAN' && !currentFinal(s.tickets[0]);
  }));
  check('one_reply', '같은 회차 중복 답변 방지', () => {
    const { state, id } = make('shipping_status');
    const once = dispatchOperation(state, { type: 'RUN_AUTO', ticketId: id }, now + 1);
    const twice = dispatchOperation(once, { type: 'RUN_AUTO', ticketId: id }, now + 2);
    return twice.tickets[0].messages.filter((m) => m.final).length === 1;
  });
  check('human_request', '사람 요청 뒤 자동 처리 차단', () => {
    const { state, id } = make('shipping_status');
    const asked = dispatchOperation(state, { type: 'REQUEST_HUMAN', ticketId: id }, now + 1);
    const s = dispatchOperation(asked, { type: 'RUN_AUTO', ticketId: id }, now + 2);
    return s.tickets[0].route === 'HUMAN' && !currentFinal(s.tickets[0]);
  });
  check('stale_approval', '초안 수정 후 이전 승인 무효', () => {
    let { state, id } = make('refund_request');
    for (const action of [{ type: 'RUN_AUTO' },{ type: 'CLAIM' },{ type: 'APPROVE' },{ type: 'SAVE_DRAFT', text: '추가 확인 후 안내하겠습니다.' },{ type: 'SEND_HUMAN' }]) {
      state = dispatchOperation(state, { ...action, ticketId: id }, now + 1);
    }
    return !state.tickets[0].approval && !currentFinal(state.tickets[0]) && state.notice.kind === 'error';
  });
  check('blocking_followup', '필수 후속 전 완료 방지', () => {
    let { state, id } = make('required_followup');
    for (const action of [{ type: 'RUN_AUTO' },{ type: 'CLAIM' },{ type: 'ADD_FOLLOWUP', title: '필수 확인', blocking: true },{ type: 'APPROVE' },{ type: 'SEND_HUMAN' }]) {
      state = dispatchOperation(state, { ...action, ticketId: id }, now + 1);
    }
    return state.tickets[0].status === 'FOLLOWUP_PENDING' && Boolean(currentFinal(state.tickets[0]));
  });
  check('stop_blocks_auto', '중지 이후 자동 응답 차단', () => {
    const { state, id } = make('shipping_status');
    const stopped = dispatchOperation(state, { type: 'STOP_AUTOMATION', reason: '시연 검사' }, now + 1);
    const s = dispatchOperation(stopped, { type: 'RUN_AUTO', ticketId: id }, now + 2);
    return !s.automation.enabled && s.tickets[0].route === 'HUMAN' && !currentFinal(s.tickets[0]);
  });
  check('public_projection', '내부 메모·초안 고객 응답 제외', () => {
    let { state, id } = make('required_followup');
    for (const action of [{ type: 'RUN_AUTO' },{ type: 'CLAIM' },{ type: 'SAVE_DRAFT', text: 'DRAFT_PRIVATE_MARKER' },{ type: 'ADD_FOLLOWUP', title: 'PRIVATE_TITLE_MARKER', internalNote: 'INTERNAL_PRIVATE_MARKER', publicNote: '추가 확인 중', blocking: true }]) {
      state = dispatchOperation(state, { ...action, ticketId: id }, now + 1);
    }
    const publicText = JSON.stringify(getCustomerView(state, id));
    return !publicText.includes('PRIVATE_MARKER') && !publicText.includes('PRIVATE_TITLE_MARKER') && publicText.includes('추가 확인 중');
  });
  return results;
}
