import { array, bool, count, hash, invalid, literal, nullable, object, page, positive, scope, text, timestamp, unique, uuid } from "../workspace/validate";
const status = (v: unknown) => literal(v, ["PENDING_REVIEW", "APPROVED", "REJECTED"]);
export function parseVersion(v: unknown, pid: string) {
  const r = object(v); if (uuid(r.policy_id) !== pid) invalid();
  const source_document_id = nullable(r.source_document_id, uuid), source = object(r.source_snapshot);
  let source_snapshot = null;
  if (source_document_id) { if (uuid(source.document_id) !== source_document_id) invalid(); literal(source.verification, ["LOCAL_RECORD_MATCH_NOT_EXTERNAL_RAG_VERIFICATION"]); source_snapshot = { document_id: source_document_id, version: positive(source.version), content_hash: hash(source.content_hash), body_hash: hash(source.body_hash), policy_key: text(source.policy_key, 64), origin: text(source.origin, 80) }; }
  else if (Object.keys(source).length) invalid();
  return { policy_id: pid, version_id: uuid(r.version_id), version_no: positive(r.version_no), title: text(r.title, 200), body: text(r.body, 20000), content_hash: hash(r.content_hash), source_document_id, source_snapshot, status: status(r.status), revision: positive(r.revision), created_by: uuid(r.created_by), created_at: timestamp(r.created_at) };
}
export function parsePolicy(v: unknown, allowed: string[], expected?: string) {
  const r = object(v), policy_id = uuid(r.policy_id); if (expected && policy_id !== expected) invalid(); literal(r.activation, ["NOT_SUPPORTED"]);
  const versions = array(r.versions).map(v => parseVersion(v, policy_id)), latest_version = positive(r.latest_version), versions_truncated = bool(r.versions_truncated);
  unique(versions.map(v => v.version_id)); if (!versions.length || versions.length > 100 || versions[0].version_no !== latest_version || versions.some((v, i) => i > 0 && v.version_no !== versions[i - 1].version_no - 1) || versions_truncated !== (latest_version > versions.length)) invalid();
  return { policy_id, policy_key: text(r.policy_key, 64), scope_hash: hash(r.scope_hash), latest_version, versions, versions_truncated, team_ids: scope(r.team_ids, allowed), created_by: uuid(r.created_by), created_at: timestamp(r.created_at), activation: "NOT_SUPPORTED" as const };
}
function reference(v: unknown) {
  const r = object(v), relation = literal(r.relation, ["RECORDED_POLICY_CITATION", "RULE_CO_USED_WITH_POLICY_CITATION"]), rule_id = nullable(r.rule_id, uuid), rule_version = nullable(r.rule_version, positive), rule_origin = nullable(r.rule_origin, v => text(v, 80)), rule_active = nullable(r.rule_active, bool);
  if (relation === "RULE_CO_USED_WITH_POLICY_CITATION" ? !rule_id || !rule_version || !rule_origin || rule_active === null : rule_id !== null || rule_version !== null) invalid();
  return { suggestion_id: uuid(r.suggestion_id), document_id: uuid(r.document_id), document_version: positive(r.document_version), source_active_at_analysis: bool(r.source_active_at_analysis), relation, rule_id, rule_version, rule_origin, rule_active, category: text(r.category, 80), origin: text(r.origin, 80), document_origin: text(r.document_origin, 80) };
}
function domain(v: unknown, rules = false) {
  const r = object(v), state = literal(r.status, ["RECORDED_LINKS", "UNCONFIRMED"]), links = array(r.links).map(reference), observed_reference_count = count(r.observed_reference_count);
  if (r.actual_affected_count !== null || r.runtime_effect !== "UNCONFIRMED" || observed_reference_count !== links.length || (state === "RECORDED_LINKS") !== !!links.length || links.some(l => (l.relation === "RULE_CO_USED_WITH_POLICY_CITATION") !== rules)) invalid();
  return { status: state, reason: text(r.reason, 200), links, observed_reference_count };
}
function impact(v: unknown) {
  const r = object(v); literal(r.coverage, ["SCOPED_LOCAL_RECORDED_SUGGESTIONS"]);
  for (const key of ["faq_catalog", "rule_condition_dependency", "backend_b_runtime", "rag_index", "azure_ai_search"]) literal(r[key], ["UNCONFIRMED"]);
  const result = { as_of: timestamp(r.as_of), source_validation: literal(r.source_validation, ["VERIFIED_SNAPSHOT", "UNCONFIRMED"]), source_reason: text(r.source_reason, 200), scanned_count: count(r.scanned_count), truncated: bool(r.truncated), faq: domain(r.faq), auto_replies: domain(r.auto_replies), automation_rules: domain(r.automation_rules, true) };
  if (result.scanned_count > 1000 || result.source_validation === "UNCONFIRMED" && [result.faq, result.auto_replies, result.automation_rules].some(d => d.links.length)) invalid(); return result;
}
function diff(v: unknown) {
  const r = object(v), kind = literal(r.kind, ["INITIAL_VERSION", "NO_CHANGE", "METADATA_ONLY", "CONTENT_CHANGED"]);
  const changes = array(r.changes).map(v => {
    const a = object(v), operation = literal(a.operation, ["replace", "delete", "insert"]), old_start = count(a.old_start), old_end = count(a.old_end), new_start = count(a.new_start), new_end = count(a.new_end);
    const line = (v: unknown) => typeof v === "string" ? v : invalid(), before = array(a.before).map(line), after = array(a.after).map(line);
    if (old_end < old_start || new_end < new_start || old_end > 500 || new_end > 500 || before.length !== old_end - old_start || after.length !== new_end - new_start) invalid();
    if (operation === "insert" ? before.length !== 0 || !after.length : operation === "delete" ? !before.length || after.length !== 0 : !before.length || !after.length) invalid();
    return { operation, old_start, old_end, new_start, new_end, before, after };
  });
  if (changes.some((c, i) => i > 0 && (c.old_start < changes[i - 1].old_end || c.new_start < changes[i - 1].new_end))) invalid();
  const title_before = nullable(r.title_before, v => text(v, 200)), title_after = text(r.title_after, 200), body_changed = bool(r.body_changed), from_hash = nullable(r.from_hash, hash), to_hash = hash(r.to_hash);
  if (body_changed !== !!changes.length || (kind === "INITIAL_VERSION") !== (title_before === null && from_hash === null) || kind === "CONTENT_CHANGED" && !body_changed || ["NO_CHANGE", "METADATA_ONLY"].includes(kind) && body_changed || kind === "NO_CHANGE" && (title_before !== title_after || from_hash !== to_hash) || kind === "METADATA_ONLY" && title_before === title_after) invalid();
  return { kind, title_before, title_after, body_changed, from_hash, to_hash, changes };
}
export function parseComparison(v: unknown, expected?: string, pid?: string) {
  const r = object(v), comparison_id = uuid(r.comparison_id), policy_id = uuid(r.policy_id), to_version_id = uuid(r.to_version_id), from_version_id = nullable(r.from_version_id, uuid); if (expected && comparison_id !== expected || pid && policy_id !== pid) invalid(); literal(r.activation, ["NOT_SUPPORTED"]);
  const reviews = array(r.reviews).map(v => { const a = object(v); if (uuid(a.comparison_id) !== comparison_id || uuid(a.version_id) !== to_version_id) invalid(); return { review_id: uuid(a.review_id), reviewed_by: uuid(a.reviewed_by), decision: literal(a.decision, ["APPROVED", "REJECTED"]), reason: text(a.reason, 500), created_at: timestamp(a.created_at) }; }); unique(reviews.map(r => r.review_id));
  const state = status(r.status), candidate_status = status(r.candidate_status), reviewable = bool(r.reviewable), d = diff(r.diff);
  if (reviewable && (state !== "PENDING_REVIEW" || candidate_status !== "PENDING_REVIEW") || (state === "PENDING_REVIEW" ? !!reviews.length : !reviews.length || reviews.at(-1)!.decision !== state || reviewable) || (from_version_id === null) !== (d.kind === "INITIAL_VERSION")) invalid();
  return { comparison_id, policy_id, from_version_id, to_version_id, status: state, candidate_status, reviewable, revision: positive(r.revision), diff: d, impact: impact(r.impact), analysis_hash: hash(r.analysis_hash), reviews, created_by: uuid(r.created_by), created_at: timestamp(r.created_at), activation: "NOT_SUPPORTED" as const };
}
export function parseVersions(v: unknown, pid: string, before: number | null, limit = 20) {
  const r = object(v), items = array(r.items).map(v => parseVersion(v, pid)), next_before_version = nullable(r.next_before_version, positive); unique(items.map(i => i.version_id));
  if (items.length > limit || items.some((v, i) => before !== null && v.version_no >= before || i > 0 && v.version_no >= items[i - 1].version_no) || next_before_version !== null && (items.length !== limit || items.at(-1)?.version_no !== next_before_version)) invalid(); return { items, next_before_version };
}
export const policiesPage = (v: unknown, allowed: string[]) => page(v, v => parsePolicy(v, allowed), p => p.policy_id);
export const comparisonsPage = (v: unknown, pid: string) => page(v, v => parseComparison(v, undefined, pid), c => c.comparison_id);
export type Policy = ReturnType<typeof parsePolicy>;
export type Version = ReturnType<typeof parseVersion>;
export type Comparison = ReturnType<typeof parseComparison>;
