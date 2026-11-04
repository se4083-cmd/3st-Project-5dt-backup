import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createInitialState, dispatchOperation, deriveMetrics, getCustomerView, scenarioCatalog } from '../../shared/operations/engine.mjs';

const NOW = Date.UTC(2026, 10, 4, 4, 0, 0);
const find = (s, id) => s.tickets.find((ticket) => ticket.id === id);
const finals = (ticket, cycle = ticket.cycle) => ticket.messages.filter((m) => m.cycle === cycle && m.final);
function make(scenarioId = 'shipping_status', body) {
  const state = dispatchOperation(createInitialState(NOW), { type: 'CREATE_CASE', scenarioId, ...(body === undefined ? {} : { body }) }, NOW);
  return { state, id: state.lastCreatedTicketId };
}
function act(state, id, type, values = {}, time = NOW + 1) {
  return dispatchOperation(state, { type, ticketId: id, ...values }, time);
}
function human(scenarioId = 'refund_request') {
  let { state, id } = make(scenarioId);
  state = act(state, id, 'RUN_AUTO');
  state = act(state, id, 'CLAIM');
  return { state, id };
}
function freezeDeep(value) {
  if (value && typeof value === 'object') { Object.freeze(value); Object.values(value).forEach(freezeDeep); }
  return value;
}

test('initial examples have a derived, internally consistent four-case workload', () => {
  const state = createInitialState(NOW);
  assert.equal(state.tickets.length, 4);
  assert.equal(scenarioCatalog.length, 12);
  assert.deepEqual(deriveMetrics(state), {
    total: 4, reviewPending: 2, assigned: 1, inProgress: 0, followupPending: 1,
    openFollowups: 1, resolved: 1, autoCompleted: 1, humanCompleted: 0, awaitingAutomation: 0,
    blockedL3: 1, overdue: 1, completedCycles: 2, autoCompletedCycles: 1,
    humanCompletedCycles: 1, autoCompletionRate: 0.5, automationEnabled: true,
  });
  assert.equal(state.mode, 'ISOLATED_SYNTHETIC_DEMO');
  assert.equal(state.storage, 'MEMORY_ONLY');
});

for (const scenario of ['shipping_status', 'general_faq', 'return_procedure', 'policy_guidance']) {
  test(`allowed ${scenario} completes without HUMAN approval or an invented ETA`, () => {
    const { state, id } = make(scenario);
    const next = act(state, id, 'RUN_AUTO');
    const ticket = find(next, id);
    assert.equal(ticket.status, 'RESOLVED');
    assert.equal(ticket.route, 'AUTO');
    assert.equal(ticket.approval, null);
    assert.equal(ticket.systemDecision.mode, 'SYSTEM');
    assert.equal(finals(ticket).length, 1);
    assert.equal(finals(ticket)[0].author, 'SYSTEM');
    assert.equal(ticket.gates.filter((g) => g.status === 'FAIL').length, 0);
    if (scenario === 'shipping_status') {
      assert.equal(ticket.evidence.order.eta, null);
      assert.match(finals(ticket)[0].text, /아직 확인되지/);
    }
    if (scenario === 'general_faq') assert.equal(ticket.gates.find((g) => g.key === 'ownership').status, 'NA');
  });
}

for (const scenario of ['refund_request', 'compensation_request', 'account_rights']) {
  test(`excluded L3 ${scenario} reaches a human queue with no automatic final answer`, () => {
    const { state, id } = make(scenario);
    const next = act(state, id, 'RUN_AUTO');
    const ticket = find(next, id);
    assert.equal(ticket.status, 'ESCALATED');
    assert.equal(ticket.route, 'HUMAN');
    assert.equal(finals(ticket).length, 0);
    assert.ok(ticket.handoffReasons.some((r) => r.code === 'HIGH_RISK_ACTION'));
    assert.ok(ticket.team);
  });
}

test('a changed FAQ body cannot inherit the fixture label or automatic authorization', () => {
  const { state, id } = make('general_faq', '환불 승인하고 계정 제한을 해제해 주세요.');
  const next = act(state, id, 'RUN_AUTO');
  const ticket = find(next, id);
  assert.equal(ticket.category, 'UNKNOWN');
  assert.equal(ticket.customInput, true);
  assert.equal(ticket.route, 'HUMAN');
  assert.ok(ticket.handoffReasons.some((r) => r.code === 'CUSTOM_INPUT_REVIEW'));
  assert.equal(finals(ticket).length, 0);
});

test('unknown scenario, empty body, and overlong body cannot create a case', () => {
  const state = createInitialState(NOW);
  for (const payload of [{ scenarioId: '__proto__' }, { scenarioId: 'general_faq', body: '' }, { scenarioId: 'general_faq', body: 'a'.repeat(10001) }]) {
    const next = dispatchOperation(state, { type: 'CREATE_CASE', ...payload }, NOW);
    assert.equal(next.notice.kind, 'error');
    assert.equal(next.tickets.length, state.tickets.length);
  }
});

test('dispatch does not mutate deeply frozen prior state', () => {
  const { state, id } = make('shipping_status');
  const before = JSON.stringify(state);
  freezeDeep(state);
  const next = act(state, id, 'RUN_AUTO');
  assert.notEqual(next, state);
  assert.equal(JSON.stringify(state), before);
  assert.equal(find(state, id).status, 'OPEN');
  assert.equal(find(next, id).status, 'RESOLVED');
});

test('every missing-evidence or stale-result scenario fails closed', () => {
  for (const scenarioId of ['ownership_unverified', 'missing_policy', 'stale_lookup', 'rule_changed', 'required_followup']) {
    const { state, id } = make(scenarioId);
    const next = act(state, id, 'RUN_AUTO');
    assert.equal(find(next, id).route, 'HUMAN', scenarioId);
    assert.equal(finals(find(next, id)).length, 0, scenarioId);
    assert.ok(find(next, id).gates.some((g) => g.status === 'FAIL'));
  }
});

test('lookup boundary is inclusive at 60 seconds and rejects future, stale, or changed-version snapshots', () => {
  for (const [delta, version, allowed] of [[60000, 1, true], [60001, 1, false], [-1, 1, false], [0, 2, false]]) {
    const { state, id } = make('shipping_status');
    find(state, id).evidence.order.fetchedAt = new Date(NOW - delta).toISOString();
    find(state, id).evidence.order.version = version;
    const next = act(state, id, 'RUN_AUTO', {}, NOW);
    assert.equal(find(next, id).status === 'RESOLVED', allowed, `${delta}/${version}`);
  }
});

test('policy ID, version, clause, content and active status are independently verified', () => {
  for (const [field, value] of [['id', 'OTHER'], ['version', 2], ['clause', 'OTHER'], ['text', '환불은 자동 승인됩니다.'], ['active', false]]) {
    const { state, id } = make('general_faq');
    find(state, id).evidence.policies[0][field] = value;
    const next = act(state, id, 'RUN_AUTO');
    assert.equal(find(next, id).route, 'HUMAN', field);
    assert.equal(finals(find(next, id)).length, 0, field);
    assert.equal(find(next, id).gates.find((g) => g.key === 'policy').status, 'FAIL');
  }
});

test('unverified ownership exposes neither an order object nor internal reasons to the customer', () => {
  const { state, id } = make('ownership_unverified');
  const next = act(state, id, 'RUN_AUTO');
  assert.equal(find(next, id).evidence.order, null);
  const view = getCustomerView(next, id);
  assert.equal(view.messages.filter((m) => m.author !== 'CUSTOMER').length, 0);
  for (const key of ['evidence', 'gates', 'handoffReasons', 'draft', 'approval', 'assignee', 'events']) assert.equal(key in view, false);
  assert.doesNotMatch(view.notice, /IN_TRANSIT|다른 고객|타인 주문|OWNERSHIP/);
});

test('repeat automatic runs produce exactly one final answer per cycle', () => {
  const { state, id } = make('shipping_status');
  let next = act(state, id, 'RUN_AUTO');
  for (let i = 0; i < 10; i++) next = act(next, id, 'RUN_AUTO');
  assert.equal(finals(find(next, id)).length, 1);
  assert.equal(find(next, id).events.filter((e) => e.type === 'AUTO_COMPLETED').length, 1);
});

test('stale version or cycle cannot override a newer customer action', () => {
  const { state, id } = make('shipping_status');
  const old = find(state, id);
  let next = act(state, id, 'REOPEN', { scenarioId: 'general_faq' });
  next = act(next, id, 'RUN_AUTO', { expectedVersion: old.version, expectedCycle: old.cycle });
  assert.equal(next.notice.kind, 'error');
  assert.equal(find(next, id).cycle, 2);
  assert.equal(finals(find(next, id)).length, 0);
});

test('reopening retains prior final history but invalidates current approval and creates a new SLA', () => {
  let { state, id } = human();
  state = act(state, id, 'APPROVE');
  state = act(state, id, 'SEND_HUMAN');
  const prior = find(state, id);
  const next = act(state, id, 'REOPEN', { scenarioId: 'shipping_status' }, NOW + 3600000);
  const ticket = find(next, id);
  assert.equal(ticket.cycle, prior.cycle + 1);
  assert.equal(ticket.approval, null);
  assert.equal(ticket.draft, '');
  assert.equal(finals(ticket, 1).length, 1);
  assert.equal(finals(ticket, 2).length, 0);
  assert.equal(Date.parse(ticket.slaDueAt), NOW + 3600000 + 240 * 60000);
  assert.equal(getCustomerView(next, id).messages.filter((m) => m.final).length, 1);
});

test('person request blocks automatic processing and preserves unanswered SLA and waiting time', () => {
  const { state, id } = make('shipping_status');
  const deadline = find(state, id).slaDueAt;
  let next = act(state, id, 'REQUEST_HUMAN', {}, NOW + 60000);
  assert.equal(find(next, id).slaDueAt, deadline);
  const requestedCycle = find(next, id).cycle;
  next = act(next, id, 'REQUEST_HUMAN', {}, NOW + 120000);
  assert.equal(find(next, id).cycle, requestedCycle);
  next = act(next, id, 'RUN_AUTO');
  assert.equal(find(next, id).route, 'HUMAN');
  assert.equal(finals(find(next, id)).length, 0);
  next = act(next, id, 'REOPEN', { scenarioId: 'general_faq' });
  assert.equal(find(next, id).route, 'HUMAN');
});

test('person request after an answered cycle gets a new response deadline', () => {
  const { state, id } = make('shipping_status');
  const replied = act(state, id, 'RUN_AUTO');
  const next = act(replied, id, 'REQUEST_HUMAN', {}, NOW + 3600000);
  assert.equal(find(next, id).cycle, 2);
  assert.equal(Date.parse(find(next, id).slaDueAt), NOW + 3600000 + 240 * 60000);
});

test('claim retains SLA, and human send requires a current explicit approval', () => {
  let { state, id } = make('refund_request');
  const deadline = find(state, id).slaDueAt;
  state = act(state, id, 'RUN_AUTO');
  state = act(state, id, 'CLAIM', {}, NOW + 30000);
  assert.equal(find(state, id).slaDueAt, deadline);
  state = act(state, id, 'SEND_HUMAN');
  assert.equal(state.notice.kind, 'error');
  assert.equal(finals(find(state, id)).length, 0);
  state = act(state, id, 'APPROVE');
  assert.equal(getCustomerView(state, id).messages.filter((m) => m.final).length, 0);
  state = act(state, id, 'SEND_HUMAN');
  state = act(state, id, 'SEND_HUMAN');
  assert.equal(finals(find(state, id)).length, 1);
  assert.equal(finals(find(state, id))[0].author, 'AGENT');
  assert.equal(find(state, id).resolutionMode, 'HUMAN');
});

test('changed draft invalidates approval and changes independently verified SHA-256', () => {
  let { state, id } = human();
  const text = '한글과 emoji 🧪를 포함한 합성 답변입니다. '.repeat(20);
  state = act(state, id, 'SAVE_DRAFT', { text });
  state = act(state, id, 'APPROVE');
  assert.equal(find(state, id).approval.contentHash, createHash('sha256').update(text.trim()).digest('hex'));
  state = act(state, id, 'SAVE_DRAFT', { text: `${text}수정` });
  assert.equal(find(state, id).approval, null);
  state = act(state, id, 'SEND_HUMAN');
  assert.equal(state.notice.kind, 'error');
  assert.equal(finals(find(state, id)).length, 0);
});

test('approval expires at exactly ten minutes and cannot be replayed with tampered text', () => {
  let { state, id } = human();
  state = act(state, id, 'APPROVE', {}, NOW);
  const expired = act(state, id, 'SEND_HUMAN', {}, NOW + 600000);
  assert.equal(expired.notice.kind, 'error');
  assert.equal(finals(find(expired, id)).length, 0);
  find(state, id).draft = '승인받지 않은 다른 답변';
  const tampered = act(state, id, 'SEND_HUMAN', {}, NOW + 1);
  assert.equal(tampered.notice.kind, 'error');
  assert.equal(finals(find(tampered, id)).length, 0);
});

test('required followup scenario cannot skip registration by approving immediately', () => {
  let { state, id } = human('required_followup');
  state = act(state, id, 'APPROVE');
  assert.equal(state.notice.kind, 'error');
  assert.equal(find(state, id).approval, null);
  state = act(state, id, 'SEND_HUMAN');
  assert.equal(finals(find(state, id)).length, 0);
});

test('all blocking followups must close after a final reply; each change invalidates pending approval', () => {
  let { state, id } = human();
  state = act(state, id, 'APPROVE');
  state = act(state, id, 'ADD_FOLLOWUP', { title: '첫 번째 확인', blocking: true });
  assert.equal(find(state, id).approval, null);
  state = act(state, id, 'ADD_FOLLOWUP', { title: '두 번째 확인', blocking: true });
  state = act(state, id, 'APPROVE');
  state = act(state, id, 'SEND_HUMAN');
  assert.equal(find(state, id).status, 'FOLLOWUP_PENDING');
  const [first, second] = find(state, id).followups;
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: first.id, status: 'IN_PROGRESS' });
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: first.id, status: 'DONE' });
  assert.equal(find(state, id).status, 'FOLLOWUP_PENDING');
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: second.id, status: 'IN_PROGRESS' });
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: second.id, status: 'DONE' });
  assert.equal(find(state, id).status, 'RESOLVED');
  assert.equal(finals(find(state, id)).length, 1);
});

test('finishing a followup without a reply cannot resolve the ticket', () => {
  let { state, id } = human('required_followup');
  state = act(state, id, 'ADD_FOLLOWUP', { title: '필수 확인', blocking: true });
  const f = find(state, id).followups[0];
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'IN_PROGRESS' });
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'DONE' });
  assert.notEqual(find(state, id).status, 'RESOLVED');
  assert.equal(finals(find(state, id)).length, 0);
});

test('followups enforce canonical enum, transitions, version and a cancellation reason', () => {
  let { state, id } = human();
  state = act(state, id, 'ADD_FOLLOWUP', { title: '확인', blocking: true });
  const f = find(state, id).followups[0];
  assert.equal(f.status, 'OPEN');
  assert.ok(f.owner); assert.ok(f.dueAt);
  assert.equal(act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'DONE' }).notice.kind, 'error');
  assert.equal(act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'IN_PROGRESS', expectedFollowupVersion: 7 }).notice.kind, 'error');
  assert.equal(act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'CANCELLED' }).notice.kind, 'error');
  state = act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'CANCELLED', reason: '합성 중복 업무 확인' });
  assert.equal(find(state, id).followups[0].status, 'CANCELLED');
  assert.equal(act(state, id, 'UPDATE_FOLLOWUP', { followupId: f.id, status: 'IN_PROGRESS' }).notice.kind, 'error');
});

test('human continuation with an optional active followup stays human on a new cycle', () => {
  let { state, id } = human();
  state = act(state, id, 'ADD_FOLLOWUP', { title: '선택 후속', blocking: false });
  state = act(state, id, 'REOPEN', { scenarioId: 'shipping_status' });
  state = act(state, id, 'RUN_AUTO');
  assert.equal(find(state, id).route, 'HUMAN');
  assert.equal(finals(find(state, id)).length, 0);
  assert.ok(find(state, id).handoffReasons.some((reason) => reason.code === 'HUMAN_CONTINUATION'));
});

test('stop preserves final history, drains pending cases, and requires an actual regression run before resuming', () => {
  let { state, id } = make('shipping_status');
  const finalCount = deriveMetrics(state).completedCycles;
  assert.equal(dispatchOperation(state, { type: 'STOP_AUTOMATION', reason: '' }, NOW).automation.enabled, true);
  state = dispatchOperation(state, { type: 'STOP_AUTOMATION', reason: '시연 점검' }, NOW);
  assert.equal(find(state, id).route, 'HUMAN');
  assert.equal(deriveMetrics(state).completedCycles, finalCount);
  assert.equal(act(state, id, 'RUN_AUTO').notice.kind, 'error');
  state = dispatchOperation(state, { type: 'RESUME_AUTOMATION' }, NOW + 1);
  assert.equal(state.automation.enabled, false);
  state = dispatchOperation(state, { type: 'RUN_REGRESSION' }, NOW + 2);
  assert.equal(state.automation.regressionPassed, true);
  assert.equal(state.automation.regression.checks.length, 10);
  assert.ok(state.automation.regression.checks.every((c) => c.passed));
  state = dispatchOperation(state, { type: 'RESUME_AUTOMATION' }, NOW + 3);
  assert.equal(state.automation.enabled, true);
  assert.equal(find(state, id).route, 'HUMAN');
  state = dispatchOperation(state, { type: 'STOP_AUTOMATION', reason: '다른 점검' }, NOW + 4);
  assert.equal(state.automation.regressionPassed, false);
  assert.equal(state.automation.regression, null);
});

test('cases received during stop stay in the human queue and stale regression cannot resume', () => {
  let state = dispatchOperation(createInitialState(NOW), { type: 'STOP_AUTOMATION', reason: '점검' }, NOW);
  state = dispatchOperation(state, { type: 'CREATE_CASE', scenarioId: 'general_faq' }, NOW + 1);
  assert.equal(find(state, state.lastCreatedTicketId).route, 'HUMAN');
  state = dispatchOperation(state, { type: 'RUN_REGRESSION' }, NOW + 2);
  state.automation.version += 1;
  state = dispatchOperation(state, { type: 'RESUME_AUTOMATION' }, NOW + 3);
  assert.equal(state.automation.enabled, false);
  assert.equal(state.notice.kind, 'error');
});

test('customer projection and event metadata exclude draft, internal title, notes and stop reason', () => {
  let { state, id } = human();
  state = act(state, id, 'SAVE_DRAFT', { text: 'PRIVATE_DRAFT_MARKER' });
  state = act(state, id, 'ADD_FOLLOWUP', {
    title: 'PRIVATE_TITLE_MARKER', publicNote: '공개 확인 중', internalNote: 'PRIVATE_NOTE_MARKER', blocking: true,
  });
  state = dispatchOperation(state, { type: 'STOP_AUTOMATION', reason: 'PRIVATE_STOP_MARKER' }, NOW);
  const view = getCustomerView(state, id);
  const publicJSON = JSON.stringify(view);
  assert.doesNotMatch(publicJSON, /PRIVATE_/);
  assert.match(publicJSON, /공개 확인 중/);
  assert.ok(view.followups[0].dueAt);
  assert.doesNotMatch(JSON.stringify(state.events), /PRIVATE_/);
  assert.equal(getCustomerView(state, 'missing'), null);
});

test('reset discards free inputs and restores deterministic fixed examples without persistence', () => {
  let { state } = make('general_faq', 'MEMORY_ONLY_TEST_MARKER');
  state = dispatchOperation(state, { type: 'RESET' }, NOW);
  assert.equal(state.tickets.length, 4);
  assert.doesNotMatch(JSON.stringify(state), /MEMORY_ONLY_TEST_MARKER/);
  assert.deepEqual(state, createInitialState(NOW));
});
