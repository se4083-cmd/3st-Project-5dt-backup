import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeSeries} from '../frontend/src/lib/analytics/detector.mjs';
import {getScenarios, getScenario, listScenarios} from '../frontend/src/lib/analytics/scenarios.mjs';

const clone = value => JSON.parse(JSON.stringify(value));
const fixture = id => clone(getScenarios().find(item => item.id === id).input);

for (const scenario of getScenarios()) {
  test(`controlled scenario: ${scenario.id}`, () => {
    const result = analyzeSeries(scenario.input);
    assert.equal(result.status, scenario.expected_status);
    assert.deepEqual([...new Set(result.signals.map(signal => signal.type))].sort(), [...scenario.expected_signal_types].sort());
    assert.equal(result.batch_id, scenario.input.batch_id);
    assert.equal(result.scope_key, scenario.input.scope_key);
    assert.equal(result.product_id, scenario.input.product_id);
  });
}

test('a one-day spike cannot be labelled a sustained change by CUSUM carryover', () => {
  const result = analyzeSeries(fixture('isolated'));
  assert.equal(result.signals.length, 1);
  assert.equal(result.signals[0].type, 'POINT_SPIKE');
  assert.equal(result.evidence.max_cusum, 2.5);
});

test('small daily increases trigger only after enough consecutive observations', () => {
  const result = analyzeSeries(fixture('sustained'));
  const signal = result.signals.find(item => item.type === 'SUSTAINED_INCREASE');
  assert.equal(signal.evidence.first_detected_day, '2026-10-29');
  assert.ok(signal.evidence.elevated_days >= 3);
  assert.equal(result.signals.some(item => item.type === 'POINT_SPIKE'), false);
});

test('repeating weekly seasonality does not itself trigger change alerts', () => {
  const input = fixture('normal');
  input.rows.forEach((row, i) => {row.episode_count = [1, 1, 1, 1, 1, 30, 30][i % 7];});
  const result = analyzeSeries(input);
  assert.equal(result.status, 'NORMAL');
  assert.equal(result.evidence.max_cusum, 0);
});

test('baseline is frozen before monitoring, and peak does not change it', () => {
  const normal = analyzeSeries(fixture('normal'));
  const spike = analyzeSeries(fixture('spike'));
  assert.equal(normal.evidence.baseline_total, spike.evidence.baseline_total);
  assert.deepEqual(normal.evidence.weekday_expected, spike.evidence.weekday_expected);
  assert.equal(normal.evidence.dispersion_scale, spike.evidence.dispersion_scale);
});

for (const key of ['batch_id', 'scope_key', 'product_id']) {
  test(`mixed ${key} is rejected rather than filtered or summed`, () => {
    const input = fixture('normal');
    input.rows[3][key] = 'OTHER';
    const result = analyzeSeries(input);
    assert.equal(result.status, 'INVALID_INPUT');
    assert.deepEqual(result.reason_codes, ['MIXED_CONTEXT']);
    assert.equal(result.signals.length, 0);
  });
}

test('same date and issue duplicate is rejected', () => {
  const input = fixture('normal');
  input.rows.push({...input.rows[0]});
  assert.deepEqual(analyzeSeries(input).reason_codes, ['DUPLICATE_ROW']);
});

test('different issues on the same day sum once into episode count', () => {
  const input = fixture('normal');
  input.rows.forEach(row => {row.episode_count -= 1;});
  input.rows.push(...input.rows.map(row => ({...row, primary_issue: 'DELAYED', episode_count: 1})));
  const result = analyzeSeries(input);
  assert.equal(result.status, 'NORMAL');
  assert.equal(result.daily_series[0].episode_count, 4);
});

test('missing bucket is not implicitly treated as zero', () => {
  const input = fixture('normal');
  const missing = input.rows.splice(2, 1)[0].day;
  const result = analyzeSeries(input);
  assert.equal(result.status, 'INCOMPLETE_DATA');
  assert.equal(result.daily_series.find(point => point.day === missing).episode_count, null);
});

test('explicit complete sparse coverage may fill confirmed zero days', () => {
  const input = fixture('normal');
  input.rows.splice(2, 1);
  input.coverage.zero_fill_missing = true;
  const result = analyzeSeries(input);
  assert.equal(result.status, 'NORMAL');
  assert.equal(result.daily_series[2].episode_count, 0);
  assert.equal(result.daily_series[2].source_state, 'confirmed_zero');
  assert.equal(result.evidence.zero_filled_days, 1);
});

test('declared missing day is not overridden by zero-fill permission', () => {
  const input = fixture('normal');
  input.coverage.zero_fill_missing = true;
  input.coverage.missing_days = [input.rows[39].day];
  const result = analyzeSeries(input);
  assert.equal(result.status, 'INCOMPLETE_DATA');
  assert.equal(result.daily_series[39].episode_count, null);
});

test('an incomplete source is blocked even when every day has rows', () => {
  const input = fixture('normal');
  input.coverage.complete = false;
  assert.equal(analyzeSeries(input).status, 'INCOMPLETE_DATA');
});

for (const status of ['DATA_MISSING', 'QUALITY_BLOCKED']) {
  test(`source ${status} blocks statistical interpretation`, () => {
    const input = fixture('spike');
    input.data_status = status;
    const result = analyzeSeries(input);
    assert.equal(result.status, 'DATA_BLOCKED');
    assert.equal(result.signals.length, 0);
  });
}

test('LOW_SAMPLE keeps P0 status and never fabricates score/rank', () => {
  const input = fixture('normal');
  input.data_status = 'LOW_SAMPLE';
  input.score = null;
  input.rank = null;
  const result = analyzeSeries(input);
  assert.equal(result.data_status, 'LOW_SAMPLE');
  assert.equal(result.status, 'NORMAL');
  assert.ok(result.warnings.some(item => item.code === 'SOURCE_LOW_SAMPLE'));
  assert.equal('score' in result, false);
  assert.equal('rank' in result, false);
});

test('counts reject fractional, negative, string and unsafe numbers', () => {
  for (const value of [1.5, -1, '4', NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    const input = fixture('normal');
    input.rows[0].episode_count = value;
    assert.deepEqual(analyzeSeries(input).reason_codes, ['COUNT_INVALID']);
  }
});

test('unresolved count cannot exceed all episodes', () => {
  const input = fixture('normal');
  input.rows[0].unresolved_count = 100;
  assert.deepEqual(analyzeSeries(input).reason_codes, ['UNRESOLVED_COUNT_INVALID']);
});

test('calendar validation rejects rollover dates and outside-coverage rows', () => {
  for (const day of ['2026-02-30', '2026-13-01', '2026-11-02', '2026-9-21']) {
    const input = fixture('normal');
    input.rows[0].day = day;
    assert.deepEqual(analyzeSeries(input).reason_codes, ['ROW_DAY_INVALID']);
  }
});

test('KST exclusive end is checked against source time without machine-timezone dependence', () => {
  const input = fixture('normal');
  input.source_as_of = '2026-11-01T14:59:59Z';
  assert.deepEqual(analyzeSeries(input).reason_codes, ['UNFINISHED_BUCKET']);
  input.source_as_of = '2026-11-01T15:00:00Z';
  assert.equal(analyzeSeries(input).status, 'NORMAL');
});

test('exactly 28 complete days is enough, 27 is not', () => {
  const input = fixture('normal');
  input.rows = input.rows.slice(-28);
  input.coverage.start_day = input.rows[0].day;
  assert.equal(analyzeSeries(input).status, 'NORMAL');
  input.rows.shift();
  input.coverage.start_day = input.rows[0].day;
  assert.equal(analyzeSeries(input).status, 'INSUFFICIENT_HISTORY');
});

test('zero baseline produces finite watch evidence and no growth percentage', () => {
  const result = analyzeSeries(fixture('new'));
  assert.equal(result.status, 'WATCH');
  assert.equal(result.signals[0].expected_count, null);
  const walk = value => {
    if (typeof value === 'number') assert.equal(Number.isFinite(value), true);
    else if (value && typeof value === 'object') Object.values(value).forEach(walk);
  };
  walk(result);
  assert.equal(JSON.stringify(result).includes('Infinity'), false);
});

test('output and input are independent, deterministic, and Fabric metrics remain unchanged', () => {
  const input = fixture('spike');
  input.score = 63.598682; input.rank = 1;
  input.metrics = {C: 10, P: 5};
  const before = clone(input);
  const first = analyzeSeries(input);
  const second = analyzeSeries(input);
  assert.deepEqual(first, second);
  assert.deepEqual(input, before);
  first.parameters.baseline_days = 1;
  assert.equal(analyzeSeries(input).parameters.baseline_days, 21);
  assert.equal('score' in first, false);
  assert.equal('rank' in first, false);
});

test('rows may arrive unordered without changing results', () => {
  const input = fixture('spike');
  const original = analyzeSeries(input);
  input.rows.reverse();
  assert.deepEqual(analyzeSeries(input), original);
});

test('missing identity or invalid top-level objects give unavailable result, not an exception', () => {
  for (const input of [null, undefined, [], {}, 1, 'test']) {
    const result = analyzeSeries(input);
    assert.equal(result.status, 'INVALID_INPUT');
    assert.equal(result.alert_level, 'unavailable');
  }
});

test('scenario selection returns independent inputs and accurate metadata', () => {
  const metadata = listScenarios();
  assert.equal(metadata.length, 8);
  for (const item of metadata) {
    const input = getScenario(item.id);
    const result = analyzeSeries(input);
    assert.equal(result.status, item.expected_status);
    assert.equal(result.alert_level, item.expected_alert_level);
    assert.equal(input.scope_key, 'DEMO_ONLY');
    input.rows[0].episode_count = 999999;
    assert.notEqual(getScenario(item.id).rows[0].episode_count, 999999);
  }
  assert.equal(getScenario('unknown'), null);
});
