import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createAppServer } from '../src/server.mjs';

const P16 = '14e4b943-d1a8-51f6-9951-21ffee9945bf';
const P11 = '2a98daae-1440-5183-a1f5-2a19c8efd495';
const fixturePath = new URL('../../data/analytics/fixture.json', import.meta.url);
const fixtureHash = () => createHash('sha256').update(readFileSync(fixturePath)).digest('hex');
const knownEmpty = JSON.parse(readFileSync(fixturePath, 'utf8')).products.find((item) => ![P16, P11].includes(item.product_id)).product_id;
let sequence = 0;
const requestId = () => `product-links-test-${++sequence}`;
async function app(t) {
  const server = createAppServer({ databasePath: ':memory:' });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.shutdown());
  const base = `http://127.0.0.1:${server.address().port}`;
  async function call(path, { payload, role = 'admin' } = {}) {
    const response = await fetch(base + path, { method: payload ? 'POST' : 'GET', headers: {
      'x-demo-role': role, ...(payload ? { 'content-type': 'application/json' } : {}),
    }, ...(payload ? { body: JSON.stringify(payload) } : {}) });
    return { status: response.status, data: await response.json() };
  }
  const product = (id, role = 'admin') => call(`/api/v2/products/${id}/operations`, { role });
  return { server, call, product };
}

test('product 16 has three explicitly linked cases and one followup, with a minimal staff projection', async (t) => {
  const api = await app(t);
  const before = fixtureHash();
  const { status, data } = await api.product(P16, 'agent');
  assert.equal(status, 200);
  assert.equal(data.source, 'SYNTHETIC_OPERATION_LINKS_NOT_ANALYTICS_EPISODES');
  assert.equal(data.scope, 'LOCAL_CURRENT_ALL_DEMO_TEAMS');
  assert.equal(data.mappingVersion, 'v2-product-links-1');
  assert.deepEqual(data.counts, { tickets: 3, openTickets: 2, followups: 1, openFollowups: 1 });
  assert.deepEqual(data.tickets.map((ticket) => ticket.id).sort(), ['DEMO-0001', 'DEMO-0002', 'DEMO-0004']);
  assert.deepEqual(Object.keys(data.tickets[0]).sort(), ['cycle', 'id', 'status', 'subject', 'team', 'version']);
  assert.deepEqual(Object.keys(data.followups[0]).sort(), ['blocking', 'dueAt', 'id', 'status', 'ticketId', 'title']);
  assert.equal(fixtureHash(), before);
});

test('a known unlinked product is a valid empty result; unknown products and customer access are rejected', async (t) => {
  const api = await app(t);
  const empty = await api.product(knownEmpty);
  assert.equal(empty.status, 200);
  assert.deepEqual(empty.data.tickets, []);
  assert.deepEqual(empty.data.followups, []);
  assert.deepEqual(empty.data.counts, { tickets: 0, openTickets: 0, followups: 0, openFollowups: 0 });
  assert.equal((await api.product('00000000-0000-0000-0000-000000000000')).status, 404);
  assert.equal((await api.product(P16, 'customer')).status, 403);
});

test('followup changes are reflected in product operations without rewriting analytics or schema', async (t) => {
  const api = await app(t);
  const before = fixtureHash();
  const schemaBefore = api.server.repository.db.prepare("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").all();
  for (const status of ['IN_PROGRESS', 'DONE']) {
    const current = (await api.call('/api/v2/state')).data;
    const ticket = current.state.tickets.find((item) => item.id === 'DEMO-0004');
    const followup = ticket.followups[0];
    const response = await api.call('/api/v2/actions', { payload: {
      expectedStateRevision: current.revision, requestId: requestId(), action: {
        type: 'UPDATE_FOLLOWUP', ticketId: ticket.id, expectedVersion: ticket.version, expectedCycle: ticket.cycle,
        followupId: followup.id, expectedFollowupVersion: followup.version, status,
      },
    } });
    assert.equal(response.status, 200);
    const view = await api.product(P16);
    assert.equal(view.data.revision, response.data.revision);
    assert.equal(view.data.followups[0].status, status);
  }
  const completed = await api.product(P16);
  assert.equal(completed.data.counts.openFollowups, 0);
  assert.equal(completed.data.counts.openTickets, 1);
  assert.equal(fixtureHash(), before);
  assert.deepEqual(api.server.repository.db.prepare("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").all(), schemaBefore);
});

test('RAG cases link only through their owned order; absent or unowned orders cannot inherit a scenario product', async (t) => {
  const api = await app(t);
  for (const [query, orderId] of [
    ['배송 상태를 알려 주세요.', 'DEMO-ORDER-002'],
    ['배송 상태를 알려 주세요.', 'DEMO-ORDER-003'],
    ['내 문의 답변은 어디서 확인해요?', null],
  ]) {
    const current = (await api.call('/api/v2/state')).data;
    const result = await api.call('/api/v2/rag/ask', { payload: { query, orderId, createTicket: true,
      expectedStateRevision: current.revision, requestId: requestId() } });
    assert.equal(result.status, 200);
  }
  const eleven = await api.product(P11);
  assert.equal(eleven.data.counts.tickets, 1);
  assert.equal(eleven.data.tickets[0].id, 'DEMO-0005');
  const sixteen = await api.product(P16);
  assert.equal(sixteen.data.counts.tickets, 3);
  assert.equal(sixteen.data.tickets.some((ticket) => ['DEMO-0006', 'DEMO-0007'].includes(ticket.id)), false);
});
