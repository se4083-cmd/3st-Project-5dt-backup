/**
 * P2 complaint-episode change detector. Browser and Node compatible.
 * Pure function: no network, storage, clock, Fabric score/rank changes, or actions.
 * Calendar `day` values name KST buckets; Date is used only for calendar arithmetic.
 */

export const DETECTOR_VERSION = 'robust_weekday_cusum_v1';

export const DETECTOR_PARAMETERS = Object.freeze({
  baseline_days: 21,
  monitor_days: 7,
  minimum_baseline_episodes: 10,
  minimum_scale: 1,
  scaled_mad_factor: 1.4826,
  spike_z_threshold: 4,
  spike_minimum_excess: 5,
  cusum_reference: 0.5,
  cusum_threshold: 5,
  cusum_positive_z_cap: 3,
  sustained_minimum_streak: 3,
  new_activity_minimum_episodes: 8,
  new_activity_minimum_active_days: 3,
  maximum_coverage_days: 366,
  maximum_input_rows: 20000,
});

const MS_PER_DAY = 86400000;
const KNOWN_DATA_STATUSES = new Set(['ELIGIBLE', 'LOW_SAMPLE', 'DATA_MISSING', 'QUALITY_BLOCKED']);
const BASE_WARNINGS = Object.freeze([
  {code: 'EXPERIMENTAL_THRESHOLDS', message: '임계값은 합성 시나리오용 초기 설정입니다. 실제 운영의 탐지 정확도나 오경보율을 보장하지 않습니다.'},
  {code: 'COUNTS_NOT_DEFECT_RATE', message: '불만 사례 수의 변화를 봅니다. 판매량 변화·행사·수집 방식의 영향과 원인은 별도 확인해야 합니다.'},
]);

const round = value => Math.round(value * 1000000) / 1000000;
const sum = values => values.reduce((a, b) => a + b, 0);
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const validId = value => typeof value === 'string' && value.length > 0 && value.length <= 128 && value.trim() === value;
const median = values => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

function dayNumber(day) {
  if (typeof day !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const time = Date.parse(`${day}T00:00:00Z`);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== day) return null;
  return time / MS_PER_DAY;
}

const dayString = value => new Date(value * MS_PER_DAY).toISOString().slice(0, 10);
const weekday = day => new Date(`${day}T00:00:00Z`).getUTCDay();

function resultShell(input) {
  return {
    schema_version: 'p2_detector_result_v1',
    detector_version: DETECTOR_VERSION,
    batch_id: validId(input?.batch_id) ? input.batch_id : null,
    scope_key: validId(input?.scope_key) ? input.scope_key : null,
    product_id: validId(input?.product_id) ? input.product_id : null,
    source_as_of: typeof input?.source_as_of === 'string' ? input.source_as_of : null,
    data_status: typeof input?.data_status === 'string' ? input.data_status : null,
    timezone: 'Asia/Seoul',
    unit: 'complaint_episode',
    status: 'INVALID_INPUT',
    alert_level: 'unavailable',
    summary: '',
    reason_codes: [],
    signals: [],
    evidence: {required_history_days: DETECTOR_PARAMETERS.baseline_days + DETECTOR_PARAMETERS.monitor_days},
    daily_series: [],
    parameters: {...DETECTOR_PARAMETERS},
    warnings: BASE_WARNINGS.map(item => ({...item})),
  };
}

/**
 * @param {object} input
 * @param {string} input.batch_id
 * @param {string} input.scope_key One permitted scope, never a sum of scopes.
 * @param {string} input.product_id
 * @param {'ELIGIBLE'|'LOW_SAMPLE'|'DATA_MISSING'|'QUALITY_BLOCKED'} input.data_status
 * @param {string=} input.source_as_of Explicitly zoned ISO timestamp.
 * @param {{start_day:string,end_day_exclusive:string,complete:boolean,zero_fill_missing:boolean,missing_days?:string[]}} input.coverage
 * @param {{batch_id:string,scope_key:string,product_id:string,day:string,primary_issue:string,episode_count:number,unresolved_count?:number}[]} input.rows
 * @returns {object} A serializable result. Invalid input returns a reason; it does not throw.
 */
export function analyzeSeries(input) {
  const result = resultShell(input);
  const stop = (status, code, message) => Object.assign(result, {
    status, alert_level: 'unavailable', summary: message, reason_codes: [code],
  });

  if (!isRecord(input)) return stop('INVALID_INPUT', 'INPUT_NOT_OBJECT', '분석 입력은 객체여야 합니다.');
  for (const key of ['batch_id', 'scope_key', 'product_id']) {
    if (!validId(input[key])) return stop('INVALID_INPUT', 'CONTEXT_REQUIRED', `${key}가 없거나 올바르지 않습니다.`);
  }
  if (!KNOWN_DATA_STATUSES.has(input.data_status)) {
    return stop('INVALID_INPUT', 'DATA_STATUS_INVALID', '원본 데이터 상태를 확인할 수 없습니다.');
  }
  if (!isRecord(input.coverage)) return stop('INVALID_INPUT', 'COVERAGE_REQUIRED', '확인된 수집 시작일과 종료일이 필요합니다.');
  const coverage = input.coverage;
  const start = dayNumber(coverage.start_day);
  const end = dayNumber(coverage.end_day_exclusive);
  if (start === null || end === null || end <= start) {
    return stop('INVALID_INPUT', 'COVERAGE_DATES_INVALID', '수집 기간은 유효한 날짜와 배타적 종료일로 지정해야 합니다.');
  }
  const coverageDays = end - start;
  if (coverageDays > DETECTOR_PARAMETERS.maximum_coverage_days) {
    return stop('INVALID_INPUT', 'COVERAGE_TOO_LARGE', '한 번에 최대 366일의 집계 데이터만 분석합니다.');
  }
  if (typeof coverage.complete !== 'boolean' || typeof coverage.zero_fill_missing !== 'boolean') {
    return stop('INVALID_INPUT', 'COVERAGE_FLAGS_REQUIRED', '수집 완료 여부와 빈 날짜의 0건 처리 여부를 명시해야 합니다.');
  }
  Object.assign(result.evidence, {
    coverage_start: coverage.start_day,
    coverage_end_exclusive: coverage.end_day_exclusive,
    coverage_days: coverageDays,
    baseline_days: DETECTOR_PARAMETERS.baseline_days,
    monitor_days: DETECTOR_PARAMETERS.monitor_days,
    zero_filled_days: 0,
  });
  if (input.source_as_of !== undefined && input.source_as_of !== null) {
    if (typeof input.source_as_of !== 'string' || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(input.source_as_of) || !Number.isFinite(Date.parse(input.source_as_of))) {
      return stop('INVALID_INPUT', 'SOURCE_AS_OF_INVALID', '원천 기준 시각에는 시간대가 포함된 유효한 시각이 필요합니다.');
    }
    const lastBucketEnd = Date.parse(`${coverage.end_day_exclusive}T00:00:00+09:00`);
    if (lastBucketEnd > Date.parse(input.source_as_of)) {
      return stop('INVALID_INPUT', 'UNFINISHED_BUCKET', '원천 기준 시각 이후의 날짜 또는 아직 끝나지 않은 일별 구간이 포함되어 있습니다.');
    }
  } else {
    result.warnings.push({code: 'SOURCE_AS_OF_NOT_SUPPLIED', message: '원천 기준 시각이 없어 수집 종료일과 추출 시각의 일치 여부는 확인하지 못했습니다.'});
  }
  if (!Array.isArray(input.rows) || input.rows.length > DETECTOR_PARAMETERS.maximum_input_rows) {
    return stop('INVALID_INPUT', 'ROWS_INVALID', '일별 행 배열이 필요하며 한 번에 최대 20,000행을 받습니다.');
  }

  const declaredMissing = new Set();
  if (coverage.missing_days !== undefined) {
    if (!Array.isArray(coverage.missing_days)) return stop('INVALID_INPUT', 'MISSING_DAYS_INVALID', '수집 누락일은 날짜 배열로 지정해야 합니다.');
    for (const day of coverage.missing_days) {
      const number = dayNumber(day);
      if (number === null || number < start || number >= end) return stop('INVALID_INPUT', 'MISSING_DAYS_INVALID', '누락일은 수집 기간 안의 유효한 날짜여야 합니다.');
      declaredMissing.add(day);
    }
  }
  const counts = new Map();
  const seenKeys = new Set();
  for (const row of input.rows) {
    if (!isRecord(row)) return stop('INVALID_INPUT', 'ROW_INVALID', '일별 집계에 객체가 아닌 행이 있습니다.');
    for (const key of ['batch_id', 'scope_key', 'product_id']) {
      if (row[key] !== input[key]) return stop('INVALID_INPUT', 'MIXED_CONTEXT', '다른 배치·팀 범위·상품의 행이 섞여 있어 분석을 중단했습니다.');
    }
    const number = dayNumber(row.day);
    if (number === null || number < start || number >= end) return stop('INVALID_INPUT', 'ROW_DAY_INVALID', '수집 기간 밖의 날짜 또는 올바르지 않은 날짜가 있습니다.');
    if (!validId(row.primary_issue)) return stop('INVALID_INPUT', 'ISSUE_REQUIRED', '이슈별 중복 검사에 필요한 primary_issue가 없습니다.');
    if (!Number.isSafeInteger(row.episode_count) || row.episode_count < 0) {
      return stop('INVALID_INPUT', 'COUNT_INVALID', '불만 사례 수는 0 이상의 안전한 정수여야 합니다.');
    }
    if (row.unresolved_count !== undefined && (!Number.isSafeInteger(row.unresolved_count) || row.unresolved_count < 0 || row.unresolved_count > row.episode_count)) {
      return stop('INVALID_INPUT', 'UNRESOLVED_COUNT_INVALID', '미해결 사례 수는 전체 사례 수를 넘을 수 없습니다.');
    }
    const uniqueKey = `${row.day}\u0000${row.primary_issue}`;
    if (seenKeys.has(uniqueKey)) return stop('INVALID_INPUT', 'DUPLICATE_ROW', '같은 날짜·이슈의 중복 행이 있어 이중 집계를 막았습니다.');
    seenKeys.add(uniqueKey);
    const total = (counts.get(row.day) ?? 0) + row.episode_count;
    if (!Number.isSafeInteger(total)) return stop('INVALID_INPUT', 'COUNT_OVERFLOW', '합산 건수가 안전한 정수 범위를 넘었습니다.');
    counts.set(row.day, total);
  }
  const monitorStart = end - DETECTOR_PARAMETERS.monitor_days;
  const baselineStart = monitorStart - DETECTOR_PARAMETERS.baseline_days;
  for (let number = start; number < end; number++) {
    const day = dayString(number);
    const present = counts.has(day);
    const isMissing = declaredMissing.has(day) || (!present && !(coverage.complete && coverage.zero_fill_missing));
    const zeroFilled = !present && !isMissing;
    if (zeroFilled) result.evidence.zero_filled_days++;
    result.daily_series.push({
      day,
      episode_count: isMissing ? null : (counts.get(day) ?? 0),
      source_state: isMissing ? 'missing' : zeroFilled ? 'confirmed_zero' : 'observed',
      phase: number < baselineStart ? 'context' : number < monitorStart ? 'baseline' : 'monitor',
      expected_count: null,
      spike_threshold_count: null,
      standardized_deviation: null,
      cusum: null,
      signals: [],
    });
  }

  if (input.data_status === 'DATA_MISSING' || input.data_status === 'QUALITY_BLOCKED') {
    return stop('DATA_BLOCKED', input.data_status, '원본 집계의 데이터 누락 또는 품질 문제가 해결된 뒤 탐지할 수 있습니다.');
  }
  if (!coverage.complete || result.daily_series.some(point => point.episode_count === null)) {
    result.evidence.missing_days = result.daily_series.filter(point => point.episode_count === null).map(point => point.day);
    return stop('INCOMPLETE_DATA', 'COVERAGE_INCOMPLETE', '수집 누락과 0건을 구분할 수 없어 탐지를 보류했습니다. 누락일을 0건으로 추정하지 않습니다.');
  }
  if (coverageDays < result.evidence.required_history_days) {
    return stop('INSUFFICIENT_HISTORY', 'HISTORY_TOO_SHORT', `확인된 일별 이력은 ${coverageDays}일입니다. 기준 21일과 관찰 7일, 총 28일이 필요합니다.`);
  }
  if (input.data_status === 'LOW_SAMPLE') {
    result.warnings.push({code: 'SOURCE_LOW_SAMPLE', message: 'P0 위험도는 표본 부족 상태입니다. 이 탐지는 별도의 일별 사례 수 조건으로만 수행하며 P0 점수·순위를 만들지 않습니다.'});
  }

  const baseline = result.daily_series.filter(point => point.phase === 'baseline');
  const monitored = result.daily_series.filter(point => point.phase === 'monitor');
  const baselineCounts = baseline.map(point => point.episode_count);
  const baselineTotal = sum(baselineCounts);
  const baselineMean = baselineTotal / baseline.length;
  const monitorTotal = sum(monitored.map(point => point.episode_count));
  const expectedByWeekday = {};
  for (let day = 0; day < 7; day++) {
    expectedByWeekday[day] = median(baseline.filter(point => weekday(point.day) === day).map(point => point.episode_count));
  }
  const residuals = baseline.map(point => point.episode_count - expectedByWeekday[weekday(point.day)]);
  const residualCenter = median(residuals);
  const mad = median(residuals.map(value => Math.abs(value - residualCenter)));
  const dispersion = Math.max(DETECTOR_PARAMETERS.minimum_scale, Math.sqrt(baselineMean), DETECTOR_PARAMETERS.scaled_mad_factor * mad);
  Object.assign(result.evidence, {
    baseline_start: dayString(baselineStart),
    baseline_end_exclusive: dayString(monitorStart),
    monitor_start: dayString(monitorStart),
    monitor_end_exclusive: coverage.end_day_exclusive,
    baseline_total: baselineTotal,
    baseline_mean: round(baselineMean),
    monitor_total: monitorTotal,
    weekday_expected: {...expectedByWeekday},
    residual_mad: round(mad),
    dispersion_scale: round(dispersion),
    expected_monitor_total: sum(monitored.map(point => expectedByWeekday[weekday(point.day)])),
  });
  for (const point of result.daily_series) {
    if (point.phase !== 'context') point.expected_count = expectedByWeekday[weekday(point.day)];
  }

  if (baselineTotal < DETECTOR_PARAMETERS.minimum_baseline_episodes) {
    const activeDays = monitored.filter(point => point.episode_count > 0).length;
    const peak = Math.max(...monitored.map(point => point.episode_count));
    const newActivity = monitorTotal >= DETECTOR_PARAMETERS.new_activity_minimum_episodes &&
      (activeDays >= DETECTOR_PARAMETERS.new_activity_minimum_active_days || peak >= DETECTOR_PARAMETERS.new_activity_minimum_episodes);
    if (newActivity) {
      result.status = 'WATCH';
      result.alert_level = 'watch';
      result.reason_codes = ['LOW_BASELINE_NEW_ACTIVITY'];
      result.summary = `기준 21일 ${baselineTotal}건에 비해 관찰 7일 ${monitorTotal}건이 확인되었습니다. 낮은 기준 표본 때문에 이상 확정 대신 신규 발생 관찰로 표시합니다.`;
      result.signals.push({
        type: 'NEW_ACTIVITY', severity: 'watch',
        start_day: monitored.find(point => point.episode_count > 0).day,
        end_day: [...monitored].reverse().find(point => point.episode_count > 0).day,
        observed_count: monitorTotal,
        expected_count: null,
        description: result.summary,
        evidence: {baseline_total: baselineTotal, baseline_days: baseline.length, monitor_total: monitorTotal, active_days: activeDays, peak_count: peak},
      });
      for (const point of monitored) if (point.episode_count > 0) point.signals.push('NEW_ACTIVITY');
    } else {
      result.status = 'LOW_BASELINE';
      result.alert_level = 'unavailable';
      result.reason_codes = ['BASELINE_EPISODES_TOO_FEW'];
      result.summary = `기준 21일의 불만 사례가 ${baselineTotal}건으로 적어 변화 탐지를 보류합니다. 관찰 7일은 ${monitorTotal}건입니다.`;
    }
    return result;
  }

  let cusum = 0;
  let elevatedStreak = 0;
  let sustainedStart = null;
  const sustainedCrossings = [];
  for (const point of monitored) {
    const expected = point.expected_count;
    const excess = point.episode_count - expected;
    const z = excess / dispersion;
    point.spike_threshold_count = Math.ceil(expected + Math.max(DETECTOR_PARAMETERS.spike_z_threshold * dispersion, DETECTOR_PARAMETERS.spike_minimum_excess));
    // Cap one day's positive contribution so a one-day jump cannot itself
    // masquerade as a sustained shift. A separate spike rule handles that jump.
    cusum = Math.max(0, cusum + Math.min(z, DETECTOR_PARAMETERS.cusum_positive_z_cap) - DETECTOR_PARAMETERS.cusum_reference);
    const elevated = excess >= Math.max(1, dispersion * DETECTOR_PARAMETERS.cusum_reference);
    elevatedStreak = elevated ? elevatedStreak + 1 : 0;
    if (elevatedStreak === 1) sustainedStart = point.day;
    if (!elevated) sustainedStart = null;
    point.standardized_deviation = round(z);
    point.cusum = round(cusum);

    if (z >= DETECTOR_PARAMETERS.spike_z_threshold && excess >= DETECTOR_PARAMETERS.spike_minimum_excess) {
      point.signals.push('POINT_SPIKE');
      result.signals.push({
        type: 'POINT_SPIKE', severity: 'warning', start_day: point.day, end_day: point.day,
        observed_count: point.episode_count, expected_count: expected,
        description: `${point.day} 불만 ${point.episode_count}건으로 같은 요일 기준 ${expected}건을 크게 웃돌았습니다. 원인 확인이 필요합니다.`,
        evidence: {excess_count: excess, standardized_deviation: round(z), threshold: DETECTOR_PARAMETERS.spike_z_threshold, dispersion_scale: round(dispersion)},
      });
    }
    if (cusum >= DETECTOR_PARAMETERS.cusum_threshold && elevatedStreak >= DETECTOR_PARAMETERS.sustained_minimum_streak) {
      point.signals.push('SUSTAINED_INCREASE');
      sustainedCrossings.push({start_day: sustainedStart, day: point.day, cusum, elevated_streak: elevatedStreak});
    }
  }
  // One signal per contiguous elevated run, rather than an alert for every day.
  const runs = new Map();
  for (const crossing of sustainedCrossings) {
    const prior = runs.get(crossing.start_day);
    runs.set(crossing.start_day, {
      ...crossing,
      first_detected_day: prior?.first_detected_day ?? crossing.day,
      maximum_cusum: Math.max(prior?.maximum_cusum ?? 0, crossing.cusum),
    });
  }
  for (const run of runs.values()) {
    const points = monitored.filter(point => point.day >= run.start_day && point.day <= run.day);
    const observed = sum(points.map(point => point.episode_count));
    const expected = sum(points.map(point => point.expected_count));
    result.signals.push({
      type: 'SUSTAINED_INCREASE', severity: 'warning', start_day: run.start_day, end_day: run.day,
      observed_count: observed, expected_count: expected,
      description: `${run.start_day}부터 ${points.length}일 연속 기준보다 높은 건수가 이어져 누적 변화 기준을 넘었습니다.`,
      evidence: {first_detected_day: run.first_detected_day, elevated_days: points.length, maximum_cusum: round(run.maximum_cusum), threshold: DETECTOR_PARAMETERS.cusum_threshold},
    });
  }
  Object.assign(result.evidence, {
    max_standardized_deviation: round(Math.max(...monitored.map(point => point.standardized_deviation))),
    max_cusum: round(Math.max(...monitored.map(point => point.cusum))),
    last_cusum: monitored.at(-1).cusum,
    signal_count: result.signals.length,
  });
  if (result.signals.length) {
    result.status = 'ALERT';
    result.alert_level = 'warning';
    result.reason_codes = [...new Set(result.signals.map(signal => signal.type))];
    const spikeDays = result.signals.filter(signal => signal.type === 'POINT_SPIKE').length;
    const sustainedRuns = result.signals.filter(signal => signal.type === 'SUSTAINED_INCREASE').length;
    result.summary = `관찰 7일에 확인된 신호는 ${[spikeDays ? `하루 급증 ${spikeDays}회` : '', sustainedRuns ? `지속 증가 ${sustainedRuns}구간` : ''].filter(Boolean).join(', ')}입니다. 이 결과는 조사 신호이며 제품 결함이나 책임을 확정하지 않습니다.`;
  } else {
    result.status = 'NORMAL';
    result.alert_level = 'none';
    result.reason_codes = ['NO_THRESHOLD_CROSSING'];
    result.summary = '관찰 7일에 설정한 급증·누적 증가 기준을 넘는 신호가 없습니다. 문제가 없다는 확정 판단은 아닙니다.';
  }
  return result;
}
