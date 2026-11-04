/**
 * Product aggregate adapter for the verified CS Flow synthetic delivery.
 * Pure ESM; safe in Node, Workers, and browsers. No source metric is recalculated.
 * Scope selection is a demo navigation feature, NOT a production authorization check.
 */

export const FIXTURE_SCHEMA_VERSION = "csflow.product-insights.fixture.v1";

export class DataContractError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "DataContractError";
    this.code = code;
  }
}

const clone = value => JSON.parse(JSON.stringify(value));
const keyFor = row => [row.batch_id, row.scope_key, row.product_id].join("|");
const DAY_MS = 86_400_000;
const nonnegativeInteger = n => Number.isSafeInteger(n) && n >= 0;
const isDay = value => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

function requireShape(data) {
  if (!data || data.schema_version !== FIXTURE_SCHEMA_VERSION
      || ![data.products, data.risks, data.daily, data.batches].every(Array.isArray)) {
    throw new DataContractError("INVALID_FIXTURE", "상품 집계 데이터의 형식이 맞지 않습니다.");
  }
}

function resolveBatch(data, batchId) {
  requireShape(data);
  const id = batchId ?? data.default_batch_id;
  if (typeof id !== "string" || !id) {
    throw new DataContractError("BATCH_REQUIRED", "조회할 데이터 배치를 지정해 주세요.");
  }
  const matches = data.batches.filter(row => row.batch_id === id);
  if (matches.length !== 1) {
    throw new DataContractError("UNKNOWN_BATCH", "확인된 데이터 배치가 아닙니다.");
  }
  return matches[0];
}

function resolveScopeRows(data, scopeKey, batchId) {
  const batch = resolveBatch(data, batchId);
  if (typeof scopeKey !== "string" || !scopeKey) {
    throw new DataContractError("SCOPE_REQUIRED", "조회할 팀 범위를 지정해 주세요.");
  }
  const rows = data.risks.filter(row => row.batch_id === batch.batch_id && row.scope_key === scopeKey);
  if (!rows.length) {
    throw new DataContractError("UNKNOWN_SCOPE", "선택한 배치에 해당 팀 범위가 없습니다.");
  }
  if (new Set(rows.map(row => row.product_id)).size !== rows.length) {
    throw new DataContractError("DUPLICATE_RISK", "같은 상품의 집계가 중복되어 조회를 중단했습니다.");
  }
  return { batch, rows };
}

function scopeTeams(scopeKey) {
  return scopeKey === "ALL4" ? ["T1", "T2", "T3", "T4"] : scopeKey.split("+");
}

export function scopeLabel(scopeKey) {
  return scopeKey === "ALL4" ? "전체 4개 팀" : `${scopeTeams(scopeKey).join(" · ")} 팀`;
}

/** Returns ALL4 first, followed by the named team combinations. */
export function listScopes(data, batchId) {
  const batch = resolveBatch(data, batchId);
  const scopeKeys = [...new Set(data.risks.filter(row => row.batch_id === batch.batch_id).map(row => row.scope_key))];
  scopeKeys.sort((a, b) => {
    if (a === "ALL4") return -1;
    if (b === "ALL4") return 1;
    return scopeTeams(a).length - scopeTeams(b).length || a.localeCompare(b);
  });
  return scopeKeys.map(scope_key => {
    const rows = data.risks.filter(row => row.batch_id === batch.batch_id && row.scope_key === scope_key);
    return {
      scope_key,
      label: scopeLabel(scope_key),
      team_codes: scopeTeams(scope_key),
      is_all: scope_key === "ALL4",
      product_count: rows.length,
      eligible_count: rows.filter(row => row.data_status === "ELIGIBLE").length,
    };
  });
}

/** Returns one exact scope; sorts by the existing source rank without recomputing it. */
export function getProductsForScope(data, scopeKey, batchId) {
  const { rows } = resolveScopeRows(data, scopeKey, batchId);
  const products = new Map(data.products.map(row => [row.product_id, row]));
  const joined = rows.map(risk => {
    const product = products.get(risk.product_id);
    if (!product) throw new DataContractError("MISSING_PRODUCT", "상품 메타데이터를 찾을 수 없습니다.");
    return { product, risk };
  });
  joined.sort((a, b) => {
    const ar = a.risk.rank ?? Number.POSITIVE_INFINITY;
    const br = b.risk.rank ?? Number.POSITIVE_INFINITY;
    if (ar !== br) return ar - br;
    return (a.product.sku ?? a.product.name ?? a.product.product_id)
      .localeCompare(b.product.sku ?? b.product.name ?? b.product.product_id);
  });
  return clone(joined);
}

/**
 * Returns raw daily issue rows plus explicit seven-day fixture coverage.
 * Missing dates before coverage.start_day are never filled or inferred.
 */
export function getProductContext(data, { product_id, scope_key, batch_id } = {}) {
  const { batch, rows } = resolveScopeRows(data, scope_key, batch_id);
  const product = data.products.find(row => row.product_id === product_id);
  const risk = rows.find(row => row.product_id === product_id);
  if (!product || !risk) {
    throw new DataContractError("UNKNOWN_PRODUCT", "선택한 팀 범위에서 상품을 찾을 수 없습니다.");
  }
  const daily = data.daily.filter(row => row.batch_id === batch.batch_id
    && row.scope_key === scope_key && row.product_id === product_id)
    .sort((a, b) => a.day.localeCompare(b.day) || a.primary_issue.localeCompare(b.primary_issue));
  const coverage = data.coverage_by_batch?.[batch.batch_id];
  if (!coverage) throw new DataContractError("MISSING_COVERAGE", "일별 자료의 확인된 기간이 없습니다.");
  if (risk.window_end !== batch.manifest?.window_end || risk.source_as_of !== batch.source_as_of) {
    throw new DataContractError("MIXED_SNAPSHOT", "상품 점수와 배치의 기준 시점이 일치하지 않습니다.");
  }
  const dailyCount = daily.reduce((sum, row) => sum + row.episode_count, 0);
  const unresolvedCount = daily.reduce((sum, row) => sum + row.unresolved_count, 0);
  if (dailyCount !== risk.metrics.C || unresolvedCount !== risk.metrics.U) {
    throw new DataContractError("DAILY_TOTAL_MISMATCH", "상품 집계와 일별 사례 합계가 일치하지 않습니다.");
  }
  return clone({ product, risk, daily, batch, coverage });
}

/** Convenient UI totals, computed within ONE selected scope only. */
export function getScopeSummary(data, scopeKey, batchId) {
  const { batch, rows } = resolveScopeRows(data, scopeKey, batchId);
  const data_quality_counts = {};
  for (const row of rows) data_quality_counts[row.data_status] = (data_quality_counts[row.data_status] ?? 0) + 1;
  const coverage = data.coverage_by_batch?.[batch.batch_id];
  return {
    batch_id: batch.batch_id,
    scope_key: scopeKey,
    product_count: rows.length,
    eligible_count: data_quality_counts.ELIGIBLE ?? 0,
    low_sample_count: data_quality_counts.LOW_SAMPLE ?? 0,
    flagged_count: rows.filter(row => row.data_status === "ELIGIBLE" && row.score >= 60).length,
    complaint_episodes: rows.reduce((sum, row) => sum + row.metrics.C, 0),
    unresolved_episodes: rows.reduce((sum, row) => sum + row.metrics.U, 0),
    data_quality_counts,
    source_as_of: batch.source_as_of,
    start_day: coverage?.start_day ?? null,
    end_day_exclusive: coverage?.end_day_exclusive ?? null,
    coverage_days: coverage?.days ?? null,
    is_demo: batch.data_origin === "SYNTHETIC" || batch.is_current !== true,
    is_current: batch.is_current === true,
    batch_status: batch.status,
  };
}

/**
 * Whole-fixture contract check. Invoke once when accepting a new aggregate input.
 * This verifies aggregate consistency; it does not prove source ingestion completeness.
 */
export function validateFixture(data) {
  const errors = [];
  try { requireShape(data); } catch (error) { return { valid: false, errors: [error.code], counts: null }; }
  const productIds = new Set();
  for (const row of data.products) {
    if (typeof row.product_id !== "string" || !row.product_id || productIds.has(row.product_id)) errors.push("PRODUCT_KEY");
    productIds.add(row.product_id);
  }
  const batches = new Map();
  for (const batch of data.batches) {
    if (batches.has(batch.batch_id)) errors.push("BATCH_KEY");
    batches.set(batch.batch_id, batch);
    const coverage = data.coverage_by_batch?.[batch.batch_id];
    if (!coverage || !isDay(coverage.start_day) || !isDay(coverage.end_day_exclusive)
      || coverage.start_day >= coverage.end_day_exclusive
      || (Date.parse(coverage.end_day_exclusive) - Date.parse(coverage.start_day)) / DAY_MS !== coverage.days) {
      errors.push("COVERAGE_CONTRACT");
    }
  }
  if (!batches.has(data.default_batch_id)) errors.push("DEFAULT_BATCH");
  const risks = new Map();
  const ranksByScope = new Map();
  for (const risk of data.risks) {
    const key = keyFor(risk);
    if (risks.has(key)) errors.push("DUPLICATE_RISK");
    risks.set(key, risk);
    if (!productIds.has(risk.product_id) || !batches.has(risk.batch_id)) errors.push("RISK_REFERENCE");
    if (!/^(ALL4|T[1-4](\+T[1-4]){0,2})$/.test(risk.scope_key)
      || new Set(scopeTeams(risk.scope_key)).size !== scopeTeams(risk.scope_key).length) errors.push("SCOPE_KEY");
    const m = risk.metrics ?? {};
    if (![m.C, m.P, m.S, m.N, m.M, m.U, m.K].every(nonnegativeInteger)
      || m.N > m.S || m.M > m.C || m.U > m.C || m.K > m.C) errors.push("METRIC_CONSTRAINT");
    if (risk.data_status === "ELIGIBLE") {
      if (!Number.isFinite(risk.score) || risk.score < 0 || risk.score > 100
        || !Number.isSafeInteger(risk.rank) || risk.rank < 1) errors.push("ELIGIBLE_SCORE_RANK");
      const scopeKey = `${risk.batch_id}|${risk.scope_key}`;
      if (!ranksByScope.has(scopeKey)) ranksByScope.set(scopeKey, []);
      ranksByScope.get(scopeKey).push(risk.rank);
    } else if (risk.score !== null || risk.rank !== null || risk.risk_band !== null) {
      errors.push("INELIGIBLE_NULLS");
    }
    const batch = batches.get(risk.batch_id);
    if (batch && (risk.window_end !== batch.manifest?.window_end || risk.source_as_of !== batch.source_as_of)) errors.push("MIXED_SNAPSHOT");
  }
  for (const ranks of ranksByScope.values()) {
    ranks.sort((a, b) => a - b);
    if (ranks.some((rank, i) => rank !== i + 1)) errors.push("RANK_CONTINUITY");
  }
  const dailyKeys = new Set();
  const totals = new Map();
  for (const row of data.daily) {
    const key = keyFor(row);
    const dailyKey = `${key}|${row.day}|${row.primary_issue}`;
    if (dailyKeys.has(dailyKey)) errors.push("DUPLICATE_DAILY");
    dailyKeys.add(dailyKey);
    if (!risks.has(key)) errors.push("DAILY_REFERENCE");
    const coverage = data.coverage_by_batch?.[row.batch_id];
    if (!isDay(row.day) || !coverage || row.day < coverage.start_day || row.day >= coverage.end_day_exclusive) errors.push("DAILY_WINDOW");
    if (!nonnegativeInteger(row.episode_count) || !nonnegativeInteger(row.unresolved_count)
      || row.unresolved_count > row.episode_count) errors.push("DAILY_COUNT");
    const sum = totals.get(key) ?? { C: 0, U: 0 };
    sum.C += row.episode_count;
    sum.U += row.unresolved_count;
    totals.set(key, sum);
  }
  for (const [key, risk] of risks) {
    const total = totals.get(key) ?? { C: 0, U: 0 };
    if (total.C !== risk.metrics?.C || total.U !== risk.metrics?.U) errors.push("DAILY_TOTAL_MISMATCH");
  }
  return {
    valid: errors.length === 0,
    errors: [...new Set(errors)],
    counts: {
      products: data.products.length,
      risks: data.risks.length,
      daily: data.daily.length,
      batches: data.batches.length,
      scopes: new Set(data.risks.map(row => row.scope_key)).size,
    },
  };
}
