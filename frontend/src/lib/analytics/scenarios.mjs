/** Controlled detector examples. These are new synthetic data, not Drive history. */

const START = '2026-09-21';
const dayAt = i => new Date(Date.parse(`${START}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10);
const baselinePattern = [4, 5, 4, 6, 4, 3, 2];
const standard = () => Array.from({length: 42}, (_, i) => baselinePattern[i % 7]);

function make(id, title, description, counts, expected, overrides = {}) {
  const identity = {batch_id: `DEMO-ANOMALY-${id}-V1`, scope_key: 'DEMO_ONLY', product_id: `DEMO-PRODUCT-${id}`};
  return {
    id, title, description, data_origin: 'SYNTHETIC_DETECTOR_SCENARIO',
    expected_status: expected.status, expected_signal_types: expected.signals ?? [],
    input: {
      ...identity,
      data_status: 'ELIGIBLE',
      source_as_of: `${dayAt(counts.length)}T00:00:00+09:00`,
      coverage: {start_day: dayAt(0), end_day_exclusive: dayAt(counts.length), complete: true, zero_fill_missing: false},
      rows: counts.map((count, i) => ({...identity, day: dayAt(i), primary_issue: 'DAMAGED', episode_count: count, unresolved_count: 0})),
      ...overrides,
    },
  };
}

export function getScenarios() {
  const spike = standard();
  spike[40] = 24;
  const sustained = standard();
  for (let i = 35; i < 42; i++) sustained[i] += 4;
  const isolated = standard();
  isolated[35] = 30;
  const newActivity = Array(42).fill(0);
  [2, 3, 1, 2, 3, 2, 2].forEach((count, i) => newActivity[35 + i] = count);
  const low = Array(42).fill(0);
  low[20] = 1; low[31] = 1; low[40] = 1;
  const missing = make('missing', '수집 누락', '관찰 기간 중 하루 수집이 누락되어 0건으로 채우지 않고 분석을 보류합니다.', standard(), {status: 'INCOMPLETE_DATA'});
  missing.input.rows = missing.input.rows.filter(row => row.day !== dayAt(38));
  const short = standard().slice(-7);
  return [
    make('normal', '평소 흐름', '요일별 차이는 반복되지만 갑작스러운 변화는 없는 통제 사례입니다.', standard(), {status: 'NORMAL'}),
    make('spike', '하루 급증', '관찰 기간의 하루만 24건으로 늘어난 통제 사례입니다.', spike, {status: 'ALERT', signals: ['POINT_SPIKE']}),
    make('sustained', '지속 증가', '마지막 7일에 매일 4건을 더해 작은 증가가 누적되는 통제 사례입니다.', sustained, {status: 'ALERT', signals: ['SUSTAINED_INCREASE']}),
    make('isolated', '급증 뒤 정상 흐름', '하루 큰 급증 이후 원래 흐름으로 돌아오면 지속 증가로 중복 판정하지 않습니다.', isolated, {status: 'ALERT', signals: ['POINT_SPIKE']}),
    make('new', '신규 발생 관찰', '기준 기간 0건 뒤 여러 날 발생합니다. 증가율이나 결함 확률을 계산하지 않습니다.', newActivity, {status: 'WATCH', signals: ['NEW_ACTIVITY']}),
    make('low', '아직 적은 표본', '발생 사례가 드물어 통계적 비교를 보류하는 통제 사례입니다.', low, {status: 'LOW_BASELINE'}),
    make('short', '7일 이력만 확보', '원본 패키지와 같은 이력 길이 조건을 확인하는 별도 통제 사례입니다.', short, {status: 'INSUFFICIENT_HISTORY'}),
    missing,
  ];
}

/** Metadata for an accessible scenario selector. No original product identity. */
export function listScenarios() {
  return getScenarios().map(scenario => ({
    id: scenario.id,
    name: scenario.title,
    description: scenario.description,
    expected_status: scenario.expected_status,
    expected_alert_level: scenario.expected_status === 'ALERT' ? 'warning'
      : scenario.expected_status === 'WATCH' ? 'watch'
        : scenario.expected_status === 'NORMAL' ? 'none' : 'unavailable',
  }));
}

/** Return an independent copy for a scenario; an unknown ID returns null. */
export function getScenario(id) {
  const scenario = getScenarios().find(item => item.id === id);
  return scenario ? JSON.parse(JSON.stringify(scenario.input)) : null;
}
