import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import {
  getDashboardData, getProductAnalysis, resolvePreparedSuggestion,
  runScenario, scenarioOptions, fixtureMetadata,
} from '../frontend/src/lib/analytics/app-service.mjs';
import {
  buildEvidenceBundle, evidenceSignatureInput, validateGeneratedSuggestions,
} from '../frontend/src/lib/analytics/insights.mjs';

const fixture = JSON.parse(await readFile(new URL('../data/analytics/fixture.json', import.meta.url), 'utf8'));
const prepared = JSON.parse(await readFile(new URL('../data/analytics/prepared-suggestions.json', import.meta.url), 'utf8'));
const provenance = JSON.parse(await readFile(new URL('../data/analytics/provenance.json', import.meta.url), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));

test('packaged data retains verified delivery provenance without operational-publication claims', () => {
  assert.deepEqual(fixture.provenance, provenance);
  assert.equal(provenance.input_files.length, 4);
  assert.equal(provenance.input_files.every(file => file.verified && file.sha256 === file.manifest_sha256), true);
  assert.equal(provenance.snapshot_source_as_of, '2026-10-31T03:00:00Z');
  assert.equal(provenance.source_kind, 'LOCAL_SYNTHETIC_VALIDATION_NOT_FABRIC');
  assert.equal(provenance.is_current, false);
  assert.equal(provenance.published_at, null);
  assert.equal(provenance.validation.fabric_executed, false);
  assert.equal(provenance.validation.backend_api_called, false);
  assert.equal(fixtureMetadata.batch_id, fixture.default_batch_id);
});

test('all 300 product/scope analyses join P1 and P2 without inventing earlier daily history', () => {
  const dashboard = getDashboardData('ALL4');
  assert.deepEqual(dashboard.stats, {
    products: 20, episodes: 295, unresolved: 59, eligible: 15, low_sample: 5,
  });
  let contexts = 0;
  for (const scope of dashboard.scopes) {
    const scoped = getDashboardData(scope.scope_key);
    for (const { product, risk } of scoped.products) {
      contexts += 1;
      const result = getProductAnalysis(scope.scope_key, product.product_id);
      const { context, bundle, anomaly, suggestions, daily, issues } = result;
      assert.equal(context.risk.batch_id, fixture.default_batch_id);
      assert.equal(context.risk.scope_key, scope.scope_key);
      assert.equal(bundle.context.scope_key, scope.scope_key);
      assert.equal(bundle.product.product_id, product.product_id);
      assert.equal(bundle.source_score, risk.score);
      assert.equal(bundle.source_rank, risk.rank);
      assert.equal(suggestions.source_score, risk.score);
      assert.equal(suggestions.source_rank, risk.rank);
      assert.equal(suggestions.mode, 'RULE_BASED');
      assert.equal(anomaly.status, 'INSUFFICIENT_HISTORY');
      assert.equal(anomaly.alert_level, 'unavailable');
      assert.equal(anomaly.evidence.coverage_days, 7);
      assert.equal(anomaly.evidence.required_history_days, 28);
      assert.equal(anomaly.signals.length, 0);
      assert.equal('score' in anomaly, false);
      assert.equal('rank' in anomaly, false);
      assert.equal(daily.length, 7);
      assert.equal(daily[0].day, '2026-10-24');
      assert.equal(daily.at(-1).day, '2026-10-30');
      assert.ok(daily.every(point => point.expected_count === null && point.cusum === null));
      assert.equal(daily.reduce((sum, row) => sum + row.episode_count, 0), risk.metrics.C);
      assert.equal(issues.reduce((sum, row) => sum + row.count, 0), risk.metrics.C);
      const observedDays = new Set(context.daily.map(row => row.day));
      for (const point of daily) {
        if (!observedDays.has(point.day)) {
          assert.equal(context.coverage.complete, true);
          assert.equal(context.coverage.zero_fill_missing, true);
          assert.equal(point.source_state, 'confirmed_zero');
          assert.equal(point.episode_count, 0);
        }
      }
      const combined = buildEvidenceBundle({ ...context, anomaly });
      assert.equal(combined.source_score, risk.score);
      assert.ok(combined.cautions.some(text => text.includes('정상 상태로 판정한 결과가 아닙니다')));
    }
  }
  assert.equal(contexts, 300);
});

test('all 15 prepared suggestions match the current SHA-256 evidence and the actual cache resolver', async () => {
  assert.equal(prepared.entry_count, 15);
  assert.equal(Object.keys(prepared.entries).length, 15);
  assert.equal(prepared.live_api_called, false);
  assert.equal(prepared.generation_mode, 'CHATGPT_PREPARED');
  for (const [key, entry] of Object.entries(prepared.entries)) {
    assert.equal(key, `${entry.batch_id}|${entry.scope_key}|${entry.product_id}`);
    assert.equal(entry.scope_key, 'ALL4');
    const { bundle, context } = getProductAnalysis(entry.scope_key, entry.product_id, entry.batch_id);
    assert.equal(context.risk.data_status, 'ELIGIBLE');
    const independentHash = createHash('sha256').update(evidenceSignatureInput(bundle), 'utf8').digest('hex');
    assert.equal(entry.input_sha256, independentHash);
    assert.equal(entry.evidence_bundle_id, bundle.evidence_bundle_id);
    assert.equal(validateGeneratedSuggestions(entry.payload, bundle).valid, true);
    const cached = await resolvePreparedSuggestion(bundle);
    assert.ok(cached, key);
    assert.equal(cached.mode, 'CHATGPT_PREPARED');
    assert.equal(cached.generation_status, 'PREPARED_VALIDATED');
    assert.equal(cached.input_sha256, independentHash);
    assert.equal(cached.source_score, context.risk.score);
    assert.equal(cached.source_rank, context.risk.rank);
    assert.equal(cached.provenance.live_api_called, false);
    assert.ok(cached.actions.length > 0 && cached.actions.length <= 3);
    const evidence = new Map(bundle.observations.map(item => [item.id, item]));
    for (const action of cached.actions) {
      assert.equal(action.requires_human_review, true);
      assert.deepEqual(action.evidence, action.evidence_ids.map(id => evidence.get(id)));
    }
  }
});

test('low-sample and other-scope products retain their own rule suggestions without cache leakage', async () => {
  const lowSample = getDashboardData('ALL4').products.filter(row => row.risk.data_status === 'LOW_SAMPLE');
  assert.equal(lowSample.length, 5);
  for (const { product } of lowSample) {
    const result = getProductAnalysis('ALL4', product.product_id);
    assert.equal(await resolvePreparedSuggestion(result.bundle), null);
    assert.equal(result.suggestions.source_score, null);
    assert.equal(result.suggestions.source_rank, null);
    assert.deepEqual(result.suggestions.actions.map(action => action.action_key), ['OBSERVE_MORE']);
  }
  const allScopes = getDashboardData().scopes;
  for (const scope of allScopes.filter(item => item.scope_key !== 'ALL4')) {
    const top = getDashboardData(scope.scope_key).products[0];
    const result = getProductAnalysis(scope.scope_key, top.product.product_id);
    assert.equal(await resolvePreparedSuggestion(result.bundle), null);
    assert.equal(result.suggestions.mode, 'RULE_BASED');
    assert.equal(result.suggestions.source_score, top.risk.score);
    assert.equal(result.suggestions.source_rank, top.risk.rank);
  }
});

test('changed source evidence invalidates a prepared response even when the old bundle id is retained', async () => {
  const entry = Object.values(prepared.entries)[0];
  const { bundle } = getProductAnalysis(entry.scope_key, entry.product_id);
  assert.ok(await resolvePreparedSuggestion(bundle));
  const changed = clone(bundle);
  changed.metrics.C += 1;
  assert.equal(changed.evidence_bundle_id, bundle.evidence_bundle_id);
  assert.equal(await resolvePreparedSuggestion(changed), null);
  const wrongScope = clone(bundle);
  wrongScope.context.scope_key = 'T1';
  assert.equal(await resolvePreparedSuggestion(wrongScope), null);
});

test('controlled scenarios remain separate from the source product, batch, and score', () => {
  const product = getDashboardData().products[0].product;
  const before = getProductAnalysis('ALL4', product.product_id);
  const options = scenarioOptions();
  assert.equal(options.length, 8);
  for (const option of options) {
    const result = runScenario(option.id);
    assert.equal(result.status, option.expected_status);
    assert.equal(result.alert_level, option.expected_alert_level);
    assert.equal(result.scope_key, 'DEMO_ONLY');
    assert.notEqual(result.batch_id, before.context.risk.batch_id);
    assert.notEqual(result.product_id, product.product_id);
    assert.equal('score' in result, false);
    assert.equal('rank' in result, false);
  }
  assert.deepEqual(getProductAnalysis('ALL4', product.product_id), before);
  assert.equal(runScenario('unknown').status, 'INVALID_INPUT');
  assert.throws(() => getProductAnalysis('UNRECOGNIZED', product.product_id), { code: 'UNKNOWN_SCOPE' });
  assert.throws(() => getProductAnalysis('ALL4', product.product_id, 'old-batch'), { code: 'UNKNOWN_BATCH' });
});
