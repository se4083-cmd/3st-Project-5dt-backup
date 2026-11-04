import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildEvidenceBundle, generateRuleSuggestions, buildModelRequest,
  validateGeneratedSuggestions, selectSuggestions, allowedActions,
  MODEL_OUTPUT_VERSION, InsightInputError, evidenceSignatureInput,
} from '../frontend/src/lib/analytics/insights.mjs';

function source(overrides = {}) {
  return {
    product: { product_id: 'product-1', name: '합성 보관 용기', category: '생활', data_origin: 'SYNTHETIC' },
    risk: {
      product_id: 'product-1', batch_id: 'batch-1', scope_key: 'ALL4', rule_version: 'voc_rule_v1',
      source_as_of: '2026-10-31T03:00:00Z', window_end: '2026-10-30T15:00:00Z',
      data_status: 'ELIGIBLE', score: 63.598682, rank: 1, risk_band: 'HIGH', data_origin: 'SYNTHETIC',
      metrics: { C: 10, P: 5, S: 100, N: 8, M: 6, U: 4, K: 6, raw_rate: 0.08, smoothed_rate: 9 / 150, growth: 1, top_issue: 'DAMAGED', outside_cohort: 1, excluded_count: 0 },
    },
    batch: { batch_id: 'batch-1', source_as_of: '2026-10-31T03:00:00Z', status: 'VALIDATED', is_current: false, data_origin: 'SYNTHETIC' },
    daily: [
      { product_id: 'product-1', batch_id: 'batch-1', scope_key: 'ALL4', day: '2026-10-25', primary_issue: 'DAMAGED', episode_count: 6, unresolved_count: 2 },
      { product_id: 'product-1', batch_id: 'batch-1', scope_key: 'ALL4', day: '2026-10-26', primary_issue: 'REFUND_DELAY', episode_count: 4, unresolved_count: 2 },
    ],
    ...overrides,
  };
}
function modelPayload(bundle) {
  return { schema_version: MODEL_OUTPUT_VERSION, evidence_bundle_id: bundle.evidence_bundle_id, actions: structuredClone(allowedActions(bundle).slice(0, 3)) };
}
function expectInputError(fn, code) {
  assert.throws(fn, error => error instanceof InsightInputError && error.code === code);
}

test('원본 수치·순위는 그대로 유지하며 한국 시간의 배타적 관찰기간을 표시한다', () => {
  const input = source();
  const before = JSON.stringify(input);
  const bundle = buildEvidenceBundle(input);
  const output = generateRuleSuggestions(bundle);
  assert.equal(JSON.stringify(input), before, '원본을 바꾸지 않는다');
  assert.equal(bundle.source_score, 63.598682);
  assert.equal(output.source_score, 63.598682);
  assert.equal(output.source_rank, 1);
  assert.equal(bundle.context.window.start, '2026-10-24');
  assert.equal(bundle.context.window.end, '2026-10-31');
  assert.equal(bundle.context.window.end_exclusive, true);
  assert.equal(bundle.context.is_demo, true);
  assert.equal(output.mode, 'RULE_BASED');
  assert.equal(output.actions.length, 3);
  assert.ok(output.actions.every(item => item.evidence.length && item.requires_human_review));
  assert.ok(Object.isFrozen(bundle.metrics));
});

test('사례, 주문, 서로 다른 고객을 다른 근거 ID로 구분한다', () => {
  const bundle = buildEvidenceBundle(source());
  const map = new Map(bundle.observations.map(item => [item.id, item]));
  assert.equal(map.get('CURRENT_EPISODES').unit, '사례');
  assert.equal(map.get('COMPLAINT_SALES_ORDERS').value, 8);
  assert.equal(map.get('COMPLAINT_SALES_ORDERS').unit, '주문');
  assert.equal(map.get('DISTINCT_CUSTOMERS').value, 6);
  assert.equal(map.get('DISTINCT_CUSTOMERS').unit, '명');
  assert.match(map.get('COMPLAINT_ORDER_RATE').text, /불량률을 뜻하지/);
});

test('직전 0건은 신규 발생으로 설명하며 증가율을 만들지 않는다', () => {
  const input = source();
  input.risk.metrics.P = 0;
  input.risk.metrics.growth = null;
  const bundle = buildEvidenceBundle(input);
  assert.equal(bundle.metrics.growth, null);
  assert.ok(!bundle.observations.some(item => item.id === 'PERIOD_GROWTH'));
  assert.ok(bundle.cautions.some(item => item.includes('증가율을 계산하지')));
  input.risk.metrics.growth = 99;
  expectInputError(() => buildEvidenceBundle(input), 'METRIC_INVARIANT');
});

test('LOW_SAMPLE은 표본 보강만 제안하고 생성형 요청을 차단한다', () => {
  const input = source({ daily: [] });
  Object.assign(input.risk, { data_status: 'LOW_SAMPLE', score: null, rank: null, risk_band: null });
  Object.assign(input.risk.metrics, { C: 3, P: 0, N: 3, M: 1, U: 0, K: 3, raw_rate: 0.03, growth: null });
  const bundle = buildEvidenceBundle(input);
  const result = generateRuleSuggestions(bundle);
  assert.equal(result.source_score, null);
  assert.deepEqual(result.actions.map(item => item.action_key), ['OBSERVE_MORE']);
  expectInputError(() => buildModelRequest(bundle), 'MODEL_NOT_ALLOWED_FOR_STATUS');
  assert.equal(validateGeneratedSuggestions(modelPayload(bundle), bundle).valid, false);
});

test('DATA_MISSING과 QUALITY_BLOCKED는 데이터 확인으로 제한한다', () => {
  for (const [status, key] of [['DATA_MISSING', 'CHECK_SALES_COVERAGE'], ['QUALITY_BLOCKED', 'CHECK_INPUT_QUALITY']]) {
    const input = source({ daily: [] });
    Object.assign(input.risk, { data_status: status, score: null, rank: null, risk_band: null });
    Object.assign(input.risk.metrics, { S: null, N: null, raw_rate: null });
    const bundle = buildEvidenceBundle(input);
    assert.equal(generateRuleSuggestions(bundle).actions[0].action_key, key);
    assert.equal(bundle.metrics.S, null, '미수집을 0으로 만들지 않는다');
  }
});

test('불변식·다른 상품·잘못된 배치·시각을 거부한다', () => {
  const variants = [
    [input => { input.risk.metrics.U = 11; }, 'METRIC_INVARIANT'],
    [input => { input.risk.metrics.N = 101; }, 'METRIC_INVARIANT'],
    [input => { input.risk.metrics.raw_rate = 0.5; }, 'METRIC_INVARIANT'],
    [input => { input.risk.product_id = 'product-2'; }, 'PRODUCT_MISMATCH'],
    [input => { input.batch.batch_id = 'batch-2'; }, 'BATCH_MISMATCH'],
    [input => { input.risk.window_end = '2026-10-31T00:00:00Z'; }, 'INVALID_WINDOW'],
    [input => { input.risk.metrics.C = 4; input.risk.metrics.M = 1; input.risk.metrics.N = 2; input.risk.metrics.U = 0; input.risk.metrics.K = 2; input.risk.metrics.raw_rate = 0.02; input.risk.metrics.growth = -0.2; }, 'STATUS_INVARIANT'],
  ];
  for (const [mutate, code] of variants) {
    const input = source();
    mutate(input);
    expectInputError(() => buildEvidenceBundle(input), code);
  }
});

test('다른 팀·배치·중복 일별 행과 합계 초과를 거부한다', () => {
  for (const key of ['scope_key', 'batch_id', 'product_id']) {
    const input = source();
    input.daily[1][key] = 'other';
    expectInputError(() => buildEvidenceBundle(input), 'DAILY_SCOPE_MISMATCH');
  }
  const duplicate = source();
  duplicate.daily.push(structuredClone(duplicate.daily[0]));
  expectInputError(() => buildEvidenceBundle(duplicate), 'DUPLICATE_DAILY');
  const tooMany = source();
  tooMany.daily[0].episode_count = 11;
  expectInputError(() => buildEvidenceBundle(tooMany), 'DAILY_METRIC_MISMATCH');
});

test('소수의 일별 행이 기간 합계와 맞더라도 빈 날짜를 0건으로 채우지 않는다', () => {
  const bundle = buildEvidenceBundle(source());
  assert.equal(bundle.daily_summary.current_rows_reconciled, true);
  assert.equal(bundle.daily_summary.observed_days, 2);
  assert.equal(bundle.daily_summary.missing_days_are_zero, false);
  assert.equal(bundle.daily_summary.rows.length, 2);
});

test('모델 입력에 상품명이나 상담 원문이 포함되지 않으며 점수 계산을 맡기지 않는다', () => {
  const input = source();
  input.product.name = 'INJECT_ME_PRIVATE_NAME';
  input.product.customer_email = 'secret@example.com';
  input.risk.ticket_body = 'PRIVATE_TICKET_BODY';
  const request = buildModelRequest(buildEvidenceBundle(input));
  const body = request.messages[1].content;
  assert.ok(!body.includes('INJECT_ME_PRIVATE_NAME'));
  assert.ok(!body.includes('secret@example.com'));
  assert.ok(!body.includes('PRIVATE_TICKET_BODY'));
  assert.ok(!body.includes('63.598682'));
  assert.equal(request.response_format.json_schema.strict, true);
  assert.equal(request.response_format.json_schema.schema.additionalProperties, false);
});

test('유효 생성 응답은 원본 수치를 유지하고 AI 작성으로 구분한다', () => {
  const bundle = buildEvidenceBundle(source());
  const result = validateGeneratedSuggestions(JSON.stringify(modelPayload(bundle)), bundle);
  assert.deepEqual(result.errors, []);
  assert.equal(result.valid, true);
  assert.equal(result.value.mode, 'GENERATIVE');
  assert.equal(result.value.source_score, bundle.source_score);
  assert.equal(result.value.execution, 'REVIEW_ONLY');
  assert.equal(selectSuggestions(bundle, modelPayload(bundle)).generation_status, 'VALIDATED');
});

test('모델이 추가한 점수·순위, 오래된 배치 또는 다른 근거를 거부한다', () => {
  const bundle = buildEvidenceBundle(source());
  for (const field of ['score', 'rank', 'metrics', '__proto__']) {
    const payload = JSON.parse(JSON.stringify(modelPayload(bundle)));
    Object.defineProperty(payload, field, { value: 99, enumerable: true });
    assert.equal(validateGeneratedSuggestions(payload, bundle).valid, false);
  }
  const stale = modelPayload(bundle);
  stale.evidence_bundle_id += '-stale';
  assert.equal(validateGeneratedSuggestions(stale, bundle).valid, false);
  const wrongEvidence = modelPayload(bundle);
  wrongEvidence.actions[0].evidence_ids = ['UNRESOLVED_EPISODES'];
  assert.equal(validateGeneratedSuggestions(wrongEvidence, bundle).valid, false);
  const ungrounded = modelPayload(bundle);
  ungrounded.actions[0].action_key = 'MISSING_FAQ';
  assert.equal(validateGeneratedSuggestions(ungrounded, bundle).valid, false);
});

test('지어낸 수치·원인·FAQ 누락·환불 실행·민감정보·HTML 문구를 거부한다', () => {
  const bundle = buildEvidenceBundle(source());
  for (const text of [
    '파손 접수 999건을 확인하세요.',
    '불량이 확정되었으니 포장을 확인하세요.',
    'FAQ가 부족하므로 문서를 점검하세요.',
    '고객의 책임 여부를 확인하세요.',
    '자동 환불을 실행하고 기록하세요.',
    '계정을 차단하고 기록하세요.',
    'https://example.com에서 내용을 확인하세요.',
    '담당자 secret@example.com에게 확인하세요.',
    '<script>alert</script> 내용을 확인하세요.',
    '포장이 문제입니다. 상태를 확인하세요.',
  ]) {
    const payload = modelPayload(bundle);
    payload.actions[0].description = text;
    assert.equal(validateGeneratedSuggestions(payload, bundle).valid, false, text);
  }
});

test('모델 오류·잘못된 JSON·거절 응답에서도 정형 제안과 원본 수치를 유지한다', () => {
  const bundle = buildEvidenceBundle(source());
  for (const payload of ['not JSON', { refusal: 'cannot comply' }, null]) {
    const output = selectSuggestions(bundle, payload);
    assert.equal(output.mode, 'RULE_BASED');
    assert.equal(output.source_score, 63.598682);
    assert.ok(output.actions.length);
    assert.equal(output.generation_status, payload === null ? 'NOT_REQUESTED' : 'REJECTED_FALLBACK');
  }
});

test('다른 시나리오의 이상 탐지를 섞지 않으며 충분하지 않은 이력을 정상이라고 부르지 않는다', () => {
  const base = {
    product_id: 'product-1', batch_id: 'batch-1', scope_key: 'ALL4', source_as_of: '2026-10-31T03:00:00Z',
    detector_version: 'robust_weekday_cusum_v1', status: 'INSUFFICIENT_HISTORY', signals: [],
  };
  const bundle = buildEvidenceBundle(source({ anomaly: base }));
  assert.ok(bundle.cautions.some(item => item.includes('정상 상태로 판정한 결과가 아닙니다')));
  assert.ok(!allowedActions(bundle).some(item => item.action_key === 'VERIFY_ANOMALY_CONTEXT'));
  expectInputError(() => buildEvidenceBundle(source({ anomaly: { ...base, batch_id: 'scenario-1' } })), 'ANOMALY_SCOPE_MISMATCH');
  const alert = buildEvidenceBundle(source({ anomaly: { ...base, status: 'ALERT', signals: [{ type: 'POINT_SPIKE', start_day: '2026-10-25', end_day: '2026-10-25', observed_count: 6 }] } }));
  assert.equal(alert.observations.find(item => item.id === 'ANOMALY_1').value, 6);
  assert.ok(allowedActions(alert).some(item => item.action_key === 'VERIFY_ANOMALY_CONTEXT'));
});

test('원본 값이 바뀌면 이전 모델 응답을 재사용할 수 없다', () => {
  const input = source();
  const original = buildEvidenceBundle(input);
  const payload = modelPayload(original);
  input.risk.score = 64;
  const current = buildEvidenceBundle(input);
  assert.notEqual(current.evidence_bundle_id, original.evidence_bundle_id);
  assert.equal(validateGeneratedSuggestions(payload, current).valid, false);
});

test('근거 서명 입력은 객체 키 순서를 무시하고 배열 순서와 원본 값을 보존한다', () => {
  const bundle = buildEvidenceBundle(source());
  const reordered = Object.fromEntries(Object.entries(bundle).reverse());
  reordered.metrics = Object.fromEntries(Object.entries(bundle.metrics).reverse());
  assert.equal(evidenceSignatureInput(bundle), evidenceSignatureInput(reordered));
  const changed = structuredClone(bundle);
  changed.metrics.C += 1;
  assert.notEqual(evidenceSignatureInput(bundle), evidenceSignatureInput(changed));
  const arrayChanged = structuredClone(bundle);
  arrayChanged.observations.reverse();
  assert.notEqual(evidenceSignatureInput(bundle), evidenceSignatureInput(arrayChanged));
});
