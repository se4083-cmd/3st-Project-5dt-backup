import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
  listScopes, getProductsForScope, getProductContext, getScopeSummary, validateFixture,
} from '../frontend/src/lib/analytics/adapter.mjs';

const data = JSON.parse(await readFile(new URL('../data/analytics/fixture.json', import.meta.url), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));

test('verified source has 20 distinct products, 15 scopes, and aggregate-only rows', () => {
  assert.deepEqual(validateFixture(data), {
    valid: true, errors: [], counts: { products: 20, risks: 300, daily: 840, batches: 1, scopes: 15 },
  });
  assert.equal(data.provenance.input_files.every(file => file.verified && file.sha256 === file.manifest_sha256), true);
  const serialized = JSON.stringify(data);
  for (const forbidden of ['customer_id', 'customer_key', 'ticket_id', 'contact_id', 'message_id', 'order_id', 'email', 'phone', 'password']) {
    assert.equal(new RegExp(`"${forbidden}"\\s*:`).test(serialized), false, forbidden);
  }
});

test('scope list preserves codes, with ALL4 first and one row per scope', () => {
  const scopes = listScopes(data);
  assert.equal(scopes.length, 15);
  assert.equal(scopes[0].scope_key, 'ALL4');
  assert.deepEqual(scopes[0].team_codes, ['T1', 'T2', 'T3', 'T4']);
  assert.equal(scopes[0].product_count, 20);
  assert.equal(scopes[0].eligible_count, 15);
  assert.equal(scopes.find(row => row.scope_key === 'T1').eligible_count, 4);
});

test('scope totals do not add overlapping aggregates together', () => {
  assert.equal(getScopeSummary(data, 'ALL4').complaint_episodes, 295);
  assert.equal(getScopeSummary(data, 'T1').complaint_episodes, 49);
  assert.equal(getScopeSummary(data, 'T1+T2').complaint_episodes, 147);
  const summary = getScopeSummary(data, 'ALL4');
  assert.equal(summary.product_count, 20);
  assert.equal(summary.eligible_count, 15);
  assert.equal(summary.low_sample_count, 5);
  assert.equal(summary.is_current, false);
  assert.equal(summary.batch_status, 'VALIDATED');
  assert.equal(summary.is_demo, true);
});

test('source score/rank are preserved and returned objects cannot mutate the fixture', () => {
  const top = getProductsForScope(data, 'ALL4')[0];
  assert.equal(top.product.product_id, '14e4b943-d1a8-51f6-9951-21ffee9945bf');
  assert.equal(top.product.name, '합성 상품 16');
  assert.equal(top.risk.score, 85.266185);
  assert.equal(top.risk.rank, 1);
  top.risk.score = 0;
  top.risk.metrics.C = 0;
  const unchanged = getProductsForScope(data, 'ALL4')[0];
  assert.equal(unchanged.risk.score, 85.266185);
  assert.equal(unchanged.risk.metrics.C, 31);
  const lowSample = getProductsForScope(data, 'ALL4').filter(row => row.risk.data_status === 'LOW_SAMPLE');
  assert.equal(lowSample.length, 5);
  assert.ok(lowSample.every(row => row.risk.score === null && row.risk.rank === null && row.risk.risk_band === null));
});

test('all 300 contexts preserve batch/scope identity and match C/U daily totals', () => {
  for (const risk of data.risks) {
    const ctx = getProductContext(data, risk);
    assert.equal(ctx.risk.score, risk.score);
    assert.equal(ctx.risk.rank, risk.rank);
    assert.ok(ctx.daily.every(row => row.batch_id === risk.batch_id && row.scope_key === risk.scope_key && row.product_id === risk.product_id));
    assert.equal(ctx.daily.reduce((sum, row) => sum + row.episode_count, 0), risk.metrics.C);
    assert.equal(ctx.daily.reduce((sum, row) => sum + row.unresolved_count, 0), risk.metrics.U);
    assert.equal(ctx.coverage.start_day, '2026-10-24');
    assert.equal(ctx.coverage.end_day_exclusive, '2026-10-31');
    assert.equal(ctx.coverage.days, 7);
    assert.ok(ctx.daily.every(row => row.day >= '2026-10-24' && row.day < '2026-10-31'));
    assert.equal(ctx.daily.some(row => row.day < ctx.coverage.start_day), false);
  }
});

test('unknown scope, product, and batch fail closed instead of broadening scope', () => {
  assert.throws(() => getProductsForScope(data, 'ALL'), { code: 'UNKNOWN_SCOPE' });
  assert.throws(() => getProductsForScope(data, 'T1+T9'), { code: 'UNKNOWN_SCOPE' });
  assert.throws(() => getProductsForScope(data, 'T1', 'unknown'), { code: 'UNKNOWN_BATCH' });
  assert.throws(() => getProductContext(data, { scope_key: 'T1', product_id: 'unknown' }), { code: 'UNKNOWN_PRODUCT' });
  assert.throws(() => getProductContext(data, { product_id: data.products[0].product_id }), { code: 'SCOPE_REQUIRED' });
});

test('mixed snapshot, duplicate risk, and incomplete daily aggregate are rejected', () => {
  const mixed = clone(data);
  mixed.risks[0].source_as_of = '2026-11-01T00:00:00Z';
  assert.throws(() => getProductContext(mixed, mixed.risks[0]), { code: 'MIXED_SNAPSHOT' });
  assert.ok(validateFixture(mixed).errors.includes('MIXED_SNAPSHOT'));
  const duplicate = clone(data);
  duplicate.risks.push(clone(duplicate.risks[0]));
  assert.throws(() => getProductsForScope(duplicate, 'T1'), { code: 'DUPLICATE_RISK' });
  const missing = clone(data);
  const deleted = missing.daily.shift();
  assert.throws(() => getProductContext(missing, deleted), { code: 'DAILY_TOTAL_MISMATCH' });
  assert.ok(validateFixture(missing).errors.includes('DAILY_TOTAL_MISMATCH'));
});

test('duplicate issue/day rows, outside-window dates, and false low-sample scores fail validation', () => {
  const duplicate = clone(data);
  duplicate.daily.push(clone(duplicate.daily[0]));
  assert.ok(validateFixture(duplicate).errors.includes('DUPLICATE_DAILY'));
  const historical = clone(data);
  historical.daily[0].day = '2026-10-01';
  assert.ok(validateFixture(historical).errors.includes('DAILY_WINDOW'));
  const corrupted = clone(data);
  corrupted.risks.find(row => row.data_status === 'LOW_SAMPLE').score = 0;
  assert.ok(validateFixture(corrupted).errors.includes('INELIGIBLE_NULLS'));
});
