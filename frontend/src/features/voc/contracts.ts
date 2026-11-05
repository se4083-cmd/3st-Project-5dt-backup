import { array, bool, count, hash, invalid, literal, nullable, number, object, page, same, scope, text, timestamp, unique, uuid } from "../workspace/validate";
export const statuses = ["PENDING_REVIEW", "APPROVED", "REJECTED", "INSUFFICIENT_DATA", "FAILED"] as const;
export const evidenceIds = ["risk", "repeat", "rate", "trend"] as const;
const code = (v: unknown) => typeof v === "string" && /^[A-Z][A-Z0-9_]{0,79}$/.test(v) ? v : invalid();
function windows(v: unknown) {
  const r = object(v);
  return { history_start: timestamp(r.history_start), operational_start: timestamp(r.operational_start), sales_start: timestamp(r.sales_start), prior_start: timestamp(r.prior_start), recent_start: timestamp(r.recent_start), window_end: timestamp(r.window_end) };
}
function metadata(v: unknown, teams: string[]) {
  const r = object(v); if (!same(scope(r.team_ids, teams), teams)) invalid();
  literal(r.origin_verification, ["SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED"]);
  return { batch_id: uuid(r.batch_id), scope_key: text(r.scope_key, 64), source: literal(r.source, ["LOCAL_SYNTHETIC", "FABRIC"]), source_as_of: timestamp(r.source_as_of), generated_at: timestamp(r.generated_at), published_at: timestamp(r.published_at), stale: bool(r.stale), windows: windows(r.windows) };
}
function facts(v: unknown, product: string, scopeKey: string) {
  const r = object(v), risk = object(r.risk), repeat = object(r.repeat), rate = object(r.rate), trend = object(r.trend);
  literal(rate.denominator_scope, ["GLOBAL_PRODUCT_PAID_28D"]);
  const daily = array(trend.daily).map(v => {
    const d = object(v), day = text(d.day, 10);
    if (uuid(d.product_id) !== product || d.scope_key !== scopeKey || !/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(day))) invalid();
    return { day, primary_issue: code(d.primary_issue), episode_count: count(d.episode_count), unresolved_count: count(d.unresolved_count) };
  });
  const score = nullable(risk.score, v => typeof v === "string" && /^\d+(\.\d+)?$/.test(v) && Number(v) <= 100 ? v : invalid());
  return { risk: { score, risk_band: nullable(risk.risk_band, v => literal(v, ["NORMAL", "WATCH", "HIGH"])), data_status: code(risk.data_status), rule_version: text(risk.rule_version, 64) },
    repeat: { C: count(repeat.C), M: count(repeat.M), K: count(repeat.K), top_issue: nullable(repeat.top_issue, code), issue_concentration: nullable(repeat.issue_concentration, v => number(v, 0, 1)) },
    rate: { N: count(rate.N), S: count(rate.S), raw_rate: nullable(rate.raw_rate, v => number(v, 0, 1)), smoothed_rate: number(rate.smoothed_rate, 0, 1), cohort_inquiry_ratio: nullable(rate.cohort_inquiry_ratio, v => number(v, 0, 1)) },
    trend: { recent_count: count(trend.recent_count), prior_count: count(trend.prior_count), growth: nullable(trend.growth, v => number(v, -1, 10 ** 12)), windows: windows(trend.windows), daily } };
}
export function parseVOC(v: unknown, allowed: string[], expectedId?: string) {
  const r = object(v), request_id = uuid(r.request_id), product_id = uuid(r.product_id), team_ids = scope(r.team_ids, allowed), e = object(r.evidence);
  if (expectedId && request_id !== expectedId || uuid(e.product_id) !== product_id) invalid();
  literal(e.fabric_connection, ["UNVERIFIED"]); literal(e.score_meaning, ["MANAGEMENT_PRIORITY_NOT_DEFECT_RATE_OR_CONFIRMED_DEFECT"]);
  const meta = nullable(e.meta, v => metadata(v, team_ids)), f = e.facts === undefined ? null : facts(e.facts, product_id, meta?.scope_key ?? "");
  if (f && (!meta || JSON.stringify(f.trend.windows) !== JSON.stringify(meta.windows))) invalid();
  const batch_id = nullable(r.batch_id, uuid); if ((meta?.batch_id ?? null) !== batch_id) invalid();
  const proposal = nullable(r.proposal, v => {
    const recommendations = array(object(v).recommendations).map(v => { const a = object(v), ids = unique(array(a.evidence_ids).map(v => literal(v, evidenceIds))); if (!ids.length) invalid(); return { title: text(a.title, 160), action: text(a.action, 1000), evidence_ids: ids }; });
    if (!recommendations.length || recommendations.length > 5 || new Set(recommendations.flatMap(r => r.evidence_ids)).size !== 4) invalid(); return { recommendations };
  });
  const reviews = array(r.reviews).map(v => { const a = object(v); return { review_id: uuid(a.review_id), reviewed_by: uuid(a.reviewed_by), decision: literal(a.decision, ["APPROVED", "REJECTED"]), reason: text(a.reason, 500), created_at: timestamp(a.created_at) }; });
  unique(reviews.map(i => i.review_id));
  const status = literal(r.status, statuses), reason_code = nullable(r.reason_code, code), revision = count(r.revision);
  if (revision < 1) invalid();
  if (["FAILED", "INSUFFICIENT_DATA"].includes(status)) { if (proposal || !reason_code || reviews.length) invalid(); }
  else if (!proposal || !f || !meta || reason_code !== null || (status === "PENDING_REVIEW" ? !!reviews.length : !reviews.length || reviews.at(-1)!.decision !== status)) invalid();
  return { request_id, product_id, team_ids, batch_id, created_by: uuid(r.created_by), status, revision, provider: literal(r.provider, ["MOCK", "AZURE_OPENAI"]), model_deployment: nullable(r.model_deployment, v => text(v, 200)), evidence: { meta, facts: f }, evidence_hash: hash(r.evidence_hash), proposal, reason_code, reviews, created_at: timestamp(r.created_at), updated_at: timestamp(r.updated_at) };
}
export const parseVOCHistory = (v: unknown, allowed: string[]) => page(v, v => parseVOC(v, allowed), i => i.request_id);
export type VOC = ReturnType<typeof parseVOC>;
export type GenerateBody = { product_id: string; team_ids: string[] };
export type ReviewBody = { expected_revision: number; decision: "APPROVED" | "REJECTED"; reason: string };
