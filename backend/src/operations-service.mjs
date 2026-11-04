import { createHash } from 'node:crypto';
import { dispatchOperation, getCustomerView } from '../../shared/operations/engine.mjs';
import { getScenario } from '../../shared/operations/fixtures.mjs';
import { ApiError, requireValue } from './errors.mjs';
import { assertSyntheticInput } from './privacy.mjs';
import { requireOwnedTicket, requireRole, DEMO_CUSTOMERS } from './identity.mjs';
import { validateQuery as validateRagQuery } from '../../ai/rag/privacy.mjs';

const ADMIN = new Set(['STOP_AUTOMATION', 'RUN_REGRESSION', 'RESUME_AUTOMATION', 'RESET']);
const CUSTOMER = new Set(['CREATE_CASE', 'REOPEN', 'REQUEST_HUMAN']);
const ACTIONS = new Set([...ADMIN, ...CUSTOMER, 'RUN_AUTO', 'CLAIM', 'SAVE_DRAFT', 'APPROVE', 'SEND_HUMAN', 'ADD_FOLLOWUP', 'UPDATE_FOLLOWUP']);
const sha = (value) => createHash('sha256').update(value).digest('hex');
const ALLOW_KINDS = new Set(['ORDER_STATUS', 'GENERAL_FAQ', 'RETURN_PROCEDURE', 'POLICY_GUIDANCE']);

export function customerTickets(state, principal) {
  return state.tickets.filter((item) => item.customerRef === principal.customerRef).map((item) => getCustomerView(state, item.id));
}

export function commandResponse(outcome, principal) {
  const { state, revision, replayed, receipt } = outcome;
  if (principal.role !== 'customer') return { state, revision, replayed, receipt, ...(receipt.result ? { result: receipt.result } : {}) };
  const ticket = state.tickets.find((item) => item.id === receipt.ticketId && item.customerRef === principal.customerRef);
  return { ticket: ticket ? getCustomerView(state, ticket.id) : null, tickets: customerTickets(state, principal), revision, replayed,
    receipt: { appliedRevision: receipt.appliedRevision, ticketId: ticket?.id ?? null },
    notice: { kind: 'success', message: ticket ? '문의가 반영되었습니다. 공개된 진행 상황을 확인해 주세요.' : '요청을 반영했습니다.' } };
}

function validQuery(query) {
  try {
    const text = validateRagQuery(query);
    assertSyntheticInput(text);
    return text;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(422, error.code ?? 'INVALID_QUERY', error.message ?? '문의 입력 형식을 확인해 주세요.');
  }
}

function checkVersion(ticket, action) {
  if (!Number.isSafeInteger(action.expectedVersion) || !Number.isSafeInteger(action.expectedCycle)) {
    throw new ApiError(422, 'TICKET_VERSION_REQUIRED', '문의의 expectedVersion과 expectedCycle을 함께 전달해 주세요.');
  }
  if (action.expectedVersion !== ticket.version || action.expectedCycle !== ticket.cycle) {
    throw new ApiError(409, 'STALE_TICKET_REVISION', '문의의 회차 또는 버전이 변경되었습니다. 최신 내용을 확인해 주세요.');
  }
  if (action.type === 'UPDATE_FOLLOWUP') {
    const followup = ticket.followups.find((item) => item.id === action.followupId);
    if (!followup) throw new ApiError(404, 'FOLLOWUP_NOT_FOUND', '접근할 수 있는 후속을 찾을 수 없습니다.');
    if (!Number.isSafeInteger(action.expectedFollowupVersion)) throw new ApiError(422, 'FOLLOWUP_VERSION_REQUIRED', '후속의 현재 버전이 필요합니다.');
    if (action.expectedFollowupVersion !== followup.version) throw new ApiError(409, 'STALE_FOLLOWUP_REVISION', '후속이 변경되었습니다. 최신 내용을 확인해 주세요.');
  }
}

/** Isolate the AI contract from the local engine and future team adapter. */
function checkedRagResult(result, query) {
  requireValue(result && typeof result === 'object' && result.mode === 'RETRIEVAL_TEMPLATE' &&
    Array.isArray(result.evidence) && Array.isArray(result.reasons) && typeof result.corpusVersion === 'string' &&
    typeof result.eligible === 'boolean' && typeof result.retrieval?.queryHash === 'string',
    502, 'RAG_CONTRACT_INVALID', '검색기의 응답 계약을 확인할 수 없습니다. 결과를 확정하지 않았습니다.');
  if (result.retrieval.queryHash !== sha(query)) throw new ApiError(502, 'RAG_QUERY_MISMATCH', '현재 문의와 검색 결과가 일치하지 않습니다.');
  if (result.eligible && (!ALLOW_KINDS.has(result.allowKind) || typeof result.reply !== 'string' || !result.reply.trim() || [...result.reply].length > 10000 || !result.evidence.length)) {
    throw new ApiError(502, 'RAG_CONTRACT_INVALID', '허용 안내의 본문과 근거가 충분하지 않습니다.');
  }
  assertSyntheticInput(result.reply);
  return structuredClone(result);
}

export class OperationsService {
  constructor(repository, ragProvider) { this.repository = repository; this.ragProvider = ragProvider; }

  context(ticket, now, extra = {}) {
    if (!ticket?.rag && !extra.ragResult) return {};
    const result = extra.ragResult ?? ticket.rag;
    const customerRef = extra.customerRef ?? ticket.customerRef;
    const order = extra.order ?? ticket?.evidence?.order ?? null;
    const validation = this.ragProvider.validateEvidence(result.evidence, { now, expectedCorpusVersion: result.corpusVersion });
    return { ragTrusted: true, ragValidation: validation, customerActive: DEMO_CUSTOMERS.includes(customerRef), customerRef,
      syntheticInputChecked: true, order, orderOwned: Boolean(order && this.repository.ownedOrder(order.id, customerRef, now)),
      orderSnapshotValid: this.repository.orderSnapshotValid(order, customerRef, now), ...extra };
  }

  async action(envelope, principal) {
    const action = envelope?.action;
    requireValue(action && typeof action === 'object' && !Array.isArray(action) && ACTIONS.has(action.type),
      422, 'UNKNOWN_ACTION', '지원하는 작업 종류를 전달해 주세요.');
    if (ADMIN.has(action.type)) requireRole(principal, ['admin']);
    else if (!CUSTOMER.has(action.type)) requireRole(principal, ['admin', 'agent']);
    // Never allow client-supplied evidence, RAG output, principal or full state.
    for (const key of ['rag', 'ragResult', 'context', 'evidence', 'state', 'customerRef', 'actor', 'approval']) {
      requireValue(!(key in action), 422, 'SERVER_FIELD_REJECTED', '서버가 확인하는 근거와 권한 필드는 직접 지정할 수 없습니다.');
    }
    assertSyntheticInput(action);
    if ('orderId' in action) requireValue(action.orderId === null || typeof action.orderId === 'string', 422, 'INVALID_ORDER_ID', '합성 주문 식별자를 확인해 주세요.');
    const replay = this.repository.replay({ scope: `${principal.role}:${principal.customerRef}:actions`, requestId: envelope.requestId, payload: { action } });
    if (replay) return commandResponse(replay, principal);
    const before = this.repository.read();
    let prepared = null;
    if (action.ticketId) {
      const ticket = requireOwnedTicket(before.state, action.ticketId, principal);
      // Reopened free-form RAG cases search again, before the write transaction.
      if (action.type === 'REOPEN' && typeof action.body === 'string' && action.scenarioId === undefined) {
        const query = validQuery(action.body);
        const order = this.repository.ownedOrder(action.orderId ?? ticket.evidence?.order?.id, ticket.customerRef);
        const result = checkedRagResult(await this.ragProvider.ask({ query, order, now: this.repository.clock() }), query);
        prepared = { query, result, order, customerRef: ticket.customerRef };
      }
    }
    const outcome = this.repository.command({ scope: `${principal.role}:${principal.customerRef}:actions`, requestId: envelope.requestId,
      payload: { action }, expectedRevision: envelope.expectedStateRevision, reset: action.type === 'RESET' }, (state, now) => {
      const ticket = action.ticketId ? requireOwnedTicket(state, action.ticketId, principal) : null;
      if (ticket) checkVersion(ticket, action);
      if (action.type === 'CREATE_CASE') {
        requireValue(Boolean(getScenario(action.scenarioId)), 422, 'UNKNOWN_SCENARIO', '등록된 합성 시나리오를 선택해 주세요.');
        if (action.body !== undefined) validQuery(action.body);
      }
      const context = this.context(ticket, now, prepared ? { ragResult: prepared.result, order: prepared.order, customerRef: prepared.customerRef } : {});
      let next = dispatchOperation(state, action, now, context);
      const id = action.type === 'CREATE_CASE' ? next.lastCreatedTicketId : action.ticketId ?? null;
      if (action.type === 'CREATE_CASE' && next.notice?.kind !== 'error') next.tickets.find((item) => item.id === id).customerRef = principal.customerRef;
      if (prepared && next.notice?.kind !== 'error') {
        const changed = next.tickets.find((item) => item.id === id);
        if (changed.route === 'AUTO') next = dispatchOperation(next, { type: 'RUN_AUTO', ticketId: id, expectedVersion: changed.version, expectedCycle: changed.cycle }, now, context);
      }
      return { state: next, ticketId: id };
    });
    return commandResponse(outcome, principal);
  }

  async ask(envelope, principal) {
    const query = validQuery(envelope?.query);
    requireValue(envelope.createTicket === undefined || typeof envelope.createTicket === 'boolean', 422, 'INVALID_CREATE_FLAG', 'createTicket은 true 또는 false여야 합니다.');
    if (!envelope.createTicket) requireRole(principal, ['admin', 'agent']);
    requireValue(envelope.orderId === undefined || envelope.orderId === null || typeof envelope.orderId === 'string', 422, 'INVALID_ORDER_ID', '합성 주문 식별자를 확인해 주세요.');
    if (envelope.createTicket) {
      const replay = this.repository.replay({ scope: `${principal.role}:${principal.customerRef}:rag`, requestId: envelope.requestId,
        payload: { query, orderId: envelope.orderId ?? null, createTicket: true } });
      if (replay) return commandResponse(replay, principal);
    }
    const order = this.repository.ownedOrder(envelope.orderId, principal.customerRef);
    const result = checkedRagResult(await this.ragProvider.ask({ query, order, now: this.repository.clock() }), query);
    if (!envelope.createTicket) return { result, revision: this.repository.read().revision };
    const outcome = this.repository.command({ scope: `${principal.role}:${principal.customerRef}:rag`, requestId: envelope.requestId,
      payload: { query, orderId: envelope.orderId ?? null, createTicket: true }, expectedRevision: envelope.expectedStateRevision }, (state, now) => {
      const context = this.context(null, now, { ragResult: result, order, customerRef: principal.customerRef });
      let next = dispatchOperation(state, { type: 'CREATE_RAG_CASE', body: query }, now, context);
      const id = next.lastCreatedTicketId;
      if (next.notice?.kind !== 'error') {
        const ticket = next.tickets.find((item) => item.id === id);
        if (ticket.route === 'AUTO') next = dispatchOperation(next, { type: 'RUN_AUTO', ticketId: id, expectedVersion: ticket.version, expectedCycle: ticket.cycle }, now, context);
      }
      return { state: next, ticketId: id, result };
    });
    return commandResponse(outcome, principal);
  }
}
