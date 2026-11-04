import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAppServer } from '../src/server.mjs';
import { createRagProvider } from '../../ai/rag/index.mjs';

const NOW = Date.UTC(2026, 10, 4, 6, 0, 0);
let sequence = 0;
const key = () => `test-request-${String(++sequence).padStart(6, '0')}`;
const finals = (ticket) => ticket.messages.filter((message) => message.final && message.author !== 'CUSTOMER');
async function app(t, options = {}) {
  const server = createAppServer({ databasePath: ':memory:', clock: () => NOW, ...options });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const url = `http://127.0.0.1:${server.address().port}`;
  t.after(() => server.shutdown());
  const call = async (path, { payload, method = payload ? 'POST' : 'GET', role = 'admin', customer, headers = {} } = {}) => {
    const response = await fetch(url + path, { method, headers: { ...(role ? { 'x-demo-role': role } : {}),
      ...(customer ? { 'x-demo-customer': customer } : {}), ...(payload ? { 'content-type': 'application/json' } : {}), ...headers },
      ...(payload ? { body: JSON.stringify(payload) } : {}) });
    return { status: response.status, data: await response.json() };
  };
  const state = async () => (await call('/api/v2/state')).data;
  const action = async (operation, extra = {}) => {
    const current = await state();
    const ticket = current.state.tickets.find((item) => item.id === operation.ticketId);
    const revision = ticket ? { expectedVersion: ticket.version, expectedCycle: ticket.cycle } : {};
    return call('/api/v2/actions', { payload: { expectedStateRevision: current.revision, requestId: key(), action: { ...revision, ...operation } }, ...extra });
  };
  const ask = async (query, extra = {}, requestOptions = {}) => {
    const current = await state();
    return call('/api/v2/rag/ask', { payload: { query, createTicket: true, orderId: 'DEMO-ORDER-001', expectedStateRevision: current.revision, requestId: key(), ...extra }, ...requestOptions });
  };
  return { server, call, state, action, ask };
}

test('status is public, data requires an explicit demo role, customer cannot read staff state', async (t) => {
  const api = await app(t);
  const status = await api.call('/api/status', { role: null });
  assert.equal(status.status, 200);
  assert.equal(status.data.storage, 'SQLITE_LOCAL');
  assert.equal(status.data.live_generation_configured, false);
  assert.equal(status.data.productionBackendConnected, false);
  assert.equal((await api.call('/api/v2/state', { role: null })).status, 401);
  assert.equal((await api.call('/api/v2/state', { role: 'unknown' })).status, 401);
  assert.equal((await api.call('/api/v2/state', { role: 'customer' })).status, 403);
  assert.equal((await api.call('/api/v2/state', { role: 'agent' })).status, 200);
  assert.equal((await api.call('/api/v2/state', { customer: 'REAL-CUSTOMER' })).status, 403);
});

test('customer list and detail are ownership scoped and omit every staff-only field', async (t) => {
  const api = await app(t);
  const own = await api.call('/api/v2/customer', { role: 'customer' });
  assert.equal(own.data.tickets.length, 4);
  for (const ticket of own.data.tickets) {
    for (const field of ['evidence', 'rag', 'draft', 'approval', 'events', 'assignee', 'handoffReasons', 'gates']) assert.equal(field in ticket, false);
    for (const followup of ticket.followups) for (const field of ['title', 'internalNote', 'cancellationReason', 'owner']) assert.equal(field in followup, false);
  }
  assert.deepEqual((await api.call('/api/v2/customer', { role: 'customer', customer: 'DEMO-CUSTOMER-002' })).data.tickets, []);
  const other = await api.call('/api/v2/customer/DEMO-0001', { role: 'customer', customer: 'DEMO-CUSTOMER-002' });
  const missing = await api.call('/api/v2/customer/DEMO-9999', { role: 'customer', customer: 'DEMO-CUSTOMER-002' });
  assert.equal(other.status, 404);
  assert.deepEqual(other.data, missing.data);
});

test('actual retrieval creates a grounded automatic final, response projection and durable restart agree', async (t) => {
  const directory = mkdtempSync(join(tmpdir(), 'csflow-persist-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const databasePath = join(directory, 'runtime.sqlite');
  const api = await app(t, { databasePath });
  const result = await api.ask('택배가 지금 어디쯤 왔나요?', {}, { role: 'customer' });
  assert.equal(result.status, 200);
  assert.equal(result.data.ticket.route, 'AUTO');
  assert.equal(result.data.ticket.status, 'RESOLVED');
  assert.equal(finals(result.data.ticket).length, 1);
  assert.match(finals(result.data.ticket)[0].text, /배송 중/);
  assert.equal('state' in result.data, false);
  assert.equal('result' in result.data, false);
  const saved = await api.state();
  const ticket = saved.state.tickets[0];
  assert.equal(ticket.rag.mode, 'RETRIEVAL_TEMPLATE');
  assert.equal(ticket.rag.retrieval.mode, 'LOCAL_BM25');
  assert.match(ticket.evidence.policies[0].documentId, /^[a-f0-9-]{36}$/);
  assert.match(ticket.evidence.policies[0].contentHash, /^[a-f0-9]{64}$/);
  assert.equal(ticket.gates.some((gate) => gate.status === 'FAIL'), false);
  assert.equal(api.server.repository.counts().finals, 3);
  await api.server.shutdown();
  const restarted = await app(t, { databasePath });
  const after = await restarted.state();
  assert.equal(after.revision, saved.revision);
  assert.deepEqual(after.state.tickets[0], ticket);
});

test('L3, unknown questions, missing ownership and no order each become a human case with no automatic final', async (t) => {
  const api = await app(t);
  for (const [query, extra, expectedReason] of [
    ['지금 환불 승인해 주세요.', {}, 'HIGH_RISK_ACTION'],
    ['보상금을 확정해 주세요.', {}, 'HIGH_RISK_ACTION'],
    ['계정 이용 제한을 해제해 주세요.', {}, 'HIGH_RISK_ACTION'],
    ['오늘 달의 색은 무엇인가요?', {}, 'UNKNOWN_INTENT'],
    ['배송 상태를 알려 주세요.', { orderId: 'DEMO-ORDER-003' }, 'OWNERSHIP_UNVERIFIED'],
    ['반품 신청은 어떤 순서로 하나요?', { orderId: null }, 'OWNERSHIP_UNVERIFIED'],
  ]) {
    const result = await api.ask(query, extra);
    assert.equal(result.status, 200, query);
    const ticket = result.data.state.tickets[0];
    assert.equal(ticket.route, 'HUMAN', query);
    assert.equal(finals(ticket).length, 0, query);
    assert.ok(ticket.handoffReasons.some((reason) => reason.code === expectedReason), query);
    if (extra.orderId !== undefined) assert.equal(ticket.evidence.order, null);
  }
});

test('recognized sensitive inputs and oversized queries are rejected before any durable write', async (t) => {
  const api = await app(t);
  const before = await api.state();
  const counts = api.server.repository.counts();
  for (const query of ['배송 문의입니다. sample@example.test로 연락 주세요.', '전화 010-1234-5678로 주세요.', '990101-1234567 확인 바랍니다.', 'password=fictional-demo-secret', 'x'.repeat(10001)]) {
    const response = await api.ask(query);
    assert.equal(response.status, 422);
  }
  const after = await api.state();
  assert.equal(after.revision, before.revision);
  assert.deepEqual(api.server.repository.counts(), counts);
  assert.equal(JSON.stringify(after).includes('sample@example.test'), false);
});

test('one command wins concurrent revision CAS, losing command does not leave a case or receipt', async (t) => {
  const api = await app(t);
  const current = await api.state();
  const command = { action: { type: 'CREATE_CASE', scenarioId: 'general_faq' }, expectedStateRevision: current.revision };
  const responses = await Promise.all([api.call('/api/v2/actions', { payload: { ...command, requestId: key() } }), api.call('/api/v2/actions', { payload: { ...command, requestId: key() } })]);
  assert.deepEqual(responses.map((response) => response.status).sort(), [200, 409]);
  const after = await api.state();
  assert.equal(after.state.tickets.length, 5);
  assert.equal(after.revision, current.revision + 1);
  assert.equal(api.server.repository.counts().receipts, 1);
});

test('10,000 Unicode code points are processed in full, and one more is rejected without truncation', async (t) => {
  const api = await app(t);
  const query = '🧪'.repeat(10000);
  const accepted = await api.ask(query);
  assert.equal(accepted.status, 200);
  const ticket = accepted.data.state.tickets[0];
  assert.equal(ticket.messages[0].text, query);
  assert.equal(ticket.rag.retrieval.queryLength, 10000);
  assert.equal(ticket.route, 'HUMAN');
  const rejected = await api.ask(query + '🧪');
  assert.equal(rejected.status, 422);
  assert.equal((await api.state()).revision, accepted.data.revision);
});

test('idempotent retry returns existing receipt without searching again; changed content conflicts', async (t) => {
  const real = createRagProvider();
  let calls = 0;
  const provider = { ...real, ask: (input) => { calls += 1; return real.ask(input); } };
  const api = await app(t, { ragProvider: provider });
  const payload = { query: '내 문의 답변은 어디서 확인해요?', createTicket: true, expectedStateRevision: 1, requestId: key() };
  const first = await api.call('/api/v2/rag/ask', { payload });
  assert.equal(first.status, 200);
  const again = await api.call('/api/v2/rag/ask', { payload });
  assert.equal(again.status, 200);
  assert.equal(again.data.replayed, true);
  assert.equal(again.data.revision, first.data.revision);
  assert.equal(again.data.receipt.ticketId, first.data.receipt.ticketId);
  assert.equal(calls, 1);
  const changed = await api.call('/api/v2/rag/ask', { payload: { ...payload, query: '주문 없이 문의해도 되나요?' } });
  assert.equal(changed.status, 409);
  assert.equal(changed.data.error.code, 'IDEMPOTENCY_CONFLICT');
  assert.equal(api.server.repository.counts().receipts, 1);
});

test('ticket cycle/version is checked even when the global revision is current', async (t) => {
  const api = await app(t);
  const created = await api.action({ type: 'CREATE_CASE', scenarioId: 'shipping_status' });
  const old = created.data.state.tickets[0];
  const requested = await api.action({ type: 'REQUEST_HUMAN', ticketId: old.id }, { role: 'customer' });
  assert.equal(requested.status, 200);
  const response = await api.call('/api/v2/actions', { payload: { requestId: key(), expectedStateRevision: requested.data.revision,
    action: { type: 'RUN_AUTO', ticketId: old.id, expectedVersion: old.version, expectedCycle: old.cycle } } });
  assert.equal(response.status, 409);
  assert.equal(response.data.error.code, 'STALE_TICKET_REVISION');
  const ticket = (await api.state()).state.tickets[0];
  assert.equal(ticket.route, 'HUMAN');
  assert.equal(finals(ticket).length, 0);
});

test('customer cannot approve, claim, run auto or stop; agent cannot administer; forged evidence is rejected', async (t) => {
  const api = await app(t);
  for (const type of ['APPROVE', 'CLAIM', 'RUN_AUTO', 'STOP_AUTOMATION']) {
    assert.equal((await api.action({ type, ticketId: 'DEMO-0002', reason: '시연 중지' }, { role: 'customer' })).status, 403);
  }
  assert.equal((await api.action({ type: 'STOP_AUTOMATION', reason: '시연 중지' }, { role: 'agent' })).status, 403);
  assert.equal((await api.action({ type: 'CREATE_CASE', scenarioId: 'general_faq', evidence: { active: true } })).status, 422);
  assert.equal((await api.action({ type: 'CREATE_RAG_CASE', body: '검색 우회' })).status, 422);
  const foreign = await api.action({ type: 'REQUEST_HUMAN', ticketId: 'DEMO-0001' }, { role: 'customer', customer: 'DEMO-CUSTOMER-002' });
  assert.equal(foreign.status, 404);
  assert.equal((await api.state()).revision, 1);
});

test('stop during an in-flight search fences the old result; new submissions remain in the human queue', async (t) => {
  const real = createRagProvider();
  let release;
  let enteredResolve;
  const entered = new Promise((resolve) => { enteredResolve = resolve; });
  let delayed = true;
  const provider = { ...real, ask: async (input) => {
    const result = real.ask(input);
    if (delayed) { enteredResolve(); await new Promise((resolve) => { release = resolve; }); }
    return result;
  } };
  const api = await app(t, { ragProvider: provider });
  const pending = api.ask('배송 상태를 알려 주세요.');
  await entered;
  const stopped = await api.action({ type: 'STOP_AUTOMATION', reason: '검색 도중 중지 검증' });
  assert.equal(stopped.status, 200);
  delayed = false;
  release();
  const late = await pending;
  assert.equal(late.status, 409);
  assert.equal(late.data.error.code, 'STALE_STATE_REVISION');
  assert.equal((await api.state()).state.tickets.length, 4);
  const next = await api.ask('배송 상태를 알려 주세요.');
  assert.equal(next.status, 200);
  assert.equal(next.data.state.tickets[0].route, 'HUMAN');
  assert.equal(finals(next.data.state.tickets[0]).length, 0);
});

test('a changed order version and a changed corpus between retrieval and finalization fail closed', async (t) => {
  const real = createRagProvider();
  let server;
  let changeOrder = true;
  const provider = { ...real, ask: (input) => {
    const result = real.ask(input);
    if (changeOrder) server.repository.db.prepare('UPDATE demo_orders SET version=version+1 WHERE id=?').run('DEMO-ORDER-001');
    return result;
  }, validateEvidence: (evidence, options) => changeOrder ? real.validateEvidence(evidence, options)
    : { valid: false, corpusVersion: 'changed', reasons: [{ code: 'POLICY_CHANGED', detail: '검증용 변경' }] } };
  const api = await app(t, { ragProvider: provider });
  server = api.server;
  const order = await api.ask('배송 상태를 알려 주세요.');
  assert.equal(order.status, 200);
  assert.equal(order.data.state.tickets[0].route, 'HUMAN');
  assert.ok(order.data.state.tickets[0].gates.some((gate) => gate.key === 'fresh_lookup' && gate.status === 'FAIL'));
  changeOrder = false;
  const policy = await api.ask('내 문의 답변은 어디서 확인해요?');
  assert.equal(policy.status, 200);
  assert.equal(policy.data.state.tickets[0].route, 'HUMAN');
  assert.ok(policy.data.state.tickets[0].gates.some((gate) => gate.key === 'policy' && gate.status === 'FAIL'));
});

test('human approval is required, invalidated by edits and used for only one durable final', async (t) => {
  const api = await app(t);
  const result = await api.ask('지금 환불 승인해 주세요.');
  const id = result.data.state.tickets[0].id;
  assert.equal((await api.action({ type: 'SEND_HUMAN', ticketId: id })).status, 409);
  assert.equal((await api.action({ type: 'CLAIM', ticketId: id })).status, 200);
  assert.equal((await api.action({ type: 'APPROVE', ticketId: id })).status, 200);
  assert.equal((await api.action({ type: 'SAVE_DRAFT', ticketId: id, text: '담당자가 요청을 확인하고 안내하겠습니다.' })).status, 200);
  assert.equal((await api.action({ type: 'SEND_HUMAN', ticketId: id })).status, 409);
  const approved = await api.action({ type: 'APPROVE', ticketId: id });
  assert.match(approved.data.state.tickets[0].approval.evidenceHash, /^[a-f0-9]{64}$/);
  const sent = await api.action({ type: 'SEND_HUMAN', ticketId: id });
  assert.equal(sent.status, 200);
  assert.equal(finals(sent.data.state.tickets[0]).length, 1);
  const again = await api.action({ type: 'SEND_HUMAN', ticketId: id });
  assert.equal(again.status, 200);
  assert.equal(finals(again.data.state.tickets[0]).length, 1);
  assert.equal(api.server.repository.counts().finals, 3);
  const view = await api.call(`/api/v2/customer/${id}`, { role: 'customer' });
  assert.equal('approval' in view.data.ticket, false);
  assert.equal('draft' in view.data.ticket, false);
});

test('free-form reopen searches again and human continuation never returns to automatic mode', async (t) => {
  const api = await app(t);
  const first = await api.ask('내 문의 답변은 어디서 확인해요?');
  const id = first.data.state.tickets[0].id;
  const reopened = await api.action({ type: 'REOPEN', ticketId: id, body: '주문 없이 문의해도 되나요?' }, { role: 'customer' });
  assert.equal(reopened.status, 200);
  assert.equal(reopened.data.ticket.cycle, 2);
  assert.equal(reopened.data.ticket.route, 'AUTO');
  assert.equal(finals(reopened.data.ticket).length, 2);
  const request = await api.action({ type: 'REOPEN', ticketId: id, body: '상담사에게 연결해 주세요.' }, { role: 'customer' });
  assert.equal(request.status, 200);
  assert.equal(request.data.ticket.route, 'HUMAN');
  const continuation = await api.action({ type: 'REOPEN', ticketId: id, body: '내 문의 답변은 어디서 확인해요?' }, { role: 'customer' });
  assert.equal(continuation.status, 200);
  assert.equal(continuation.data.ticket.route, 'HUMAN');
  assert.equal(finals(continuation.data.ticket).length, 2);
});

test('reset starts a new epoch and refuses receipts from the previous session', async (t) => {
  const api = await app(t);
  const payload = { action: { type: 'CREATE_CASE', scenarioId: 'general_faq' }, expectedStateRevision: 1, requestId: key() };
  const first = await api.call('/api/v2/actions', { payload });
  assert.equal(first.status, 200);
  const reset = await api.action({ type: 'RESET' });
  assert.equal(reset.status, 200);
  assert.equal(reset.data.state.tickets.length, 4);
  assert.equal(reset.data.revision, 3);
  const old = await api.call('/api/v2/actions', { payload });
  assert.equal(old.status, 409);
  assert.equal(old.data.error.code, 'REQUEST_FROM_RESET_SESSION');
});

test('same-origin, JSON and body guards fail without persisting an operation', async (t) => {
  const api = await app(t);
  const payload = { action: { type: 'RESET' }, expectedStateRevision: 1, requestId: key() };
  assert.equal((await api.call('/api/v2/actions', { payload, headers: { origin: 'https://different.example' } })).status, 403);
  assert.equal((await api.call('/api/v2/actions', { payload, headers: { 'content-type': 'text/plain' } })).status, 415);
  assert.equal((await api.call('/api/v2/actions', { payload: { padding: 'x'.repeat(140000) } })).status, 413);
  assert.equal((await api.state()).revision, 1);
});

test('missing corpus records a human case without fabricated evidence or an automatic answer', async (t) => {
  const directory = mkdtempSync(join(tmpdir(), 'csflow-empty-rag-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const api = await app(t, { ragProvider: createRagProvider({ corpusDir: directory }) });
  const response = await api.ask('내 문의 답변은 어디서 확인해요?');
  assert.equal(response.status, 200);
  assert.equal(response.data.state.tickets[0].route, 'HUMAN');
  assert.deepEqual(response.data.state.tickets[0].evidence.policies, []);
  assert.equal(finals(response.data.state.tickets[0]).length, 0);
});

for (const [name, query] of [
  ['shipping plus address change', '배송 상태 알려줘. 배송지를 변경해줘.'],
  ['return procedure plus coupon issuance', '반품 신청 절차를 알려주고 쿠폰도 발급해줘.'],
  ['allowed FAQ plus an uncovered information request', '내 문의 답변 확인 방법과 날씨를 알려줘.'],
]) {
  test(`the full request must be covered: ${name} cannot auto-complete`, async (t) => {
    const api = await app(t);
    const response = await api.ask(query);
    assert.equal(response.status, 200);
    const ticket = response.data.state.tickets[0];
    assert.equal(ticket.route, 'HUMAN');
    assert.equal(finals(ticket).length, 0);
    assert.ok(ticket.rag.reasons.length > 0);
  });
}
