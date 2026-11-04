import { ApiError } from "../../api";

export const jobKinds = ["AUTO", "HANDOFF"] as const;
export const jobStatuses = ["PENDING", "RUNNING", "RETRY", "SUCCEEDED", "FAILED", "HANDED_OFF", "CANCELLED"] as const;
export type JobKind = typeof jobKinds[number];
export type JobStatus = typeof jobStatuses[number];
type RecordValue = Record<string, unknown>;
function invalid(): never { throw new ApiError(0, "INVALID_RESPONSE"); }
function object(value: unknown): RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : invalid();
}
function text(value: unknown): string { return typeof value === "string" && value.length > 0 ? value : invalid(); }
function integer(value: unknown): number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : invalid(); }
function bool(value: unknown): boolean { return typeof value === "boolean" ? value : invalid(); }
function literal<T extends string>(value: unknown, values: readonly T[]): T { return values.includes(value as T) ? value as T : invalid(); }
function timestamp(value: unknown): string {
  const s = text(value);
  return /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(s) && Number.isFinite(Date.parse(s)) ? s : invalid();
}
function uuid(value: unknown): string {
  const s = text(value);
  return /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(s) ? s.toLowerCase() : invalid();
}
function strings(value: unknown): string[] { return Array.isArray(value) ? value.map(text) : invalid(); }
function scope(value: unknown, expected: string[]): string[] {
  const ids = Array.isArray(value) ? value.map(uuid) : invalid();
  if (new Set(ids).size !== ids.length || [...ids].sort().join() !== [...expected].map(s => s.toLowerCase()).sort().join()) invalid();
  return ids;
}
function envelope(value: unknown, teams: string[]) {
  const r = object(value);
  return { r, as_of: timestamp(r.as_of), selected_team_ids: scope(r.selected_team_ids, teams) };
}
function unobserved(value: unknown) {
  const r = object(value);
  literal(r.availability, ["UNOBSERVED"]);
  literal(r.coverage, ["NONE"]);
  literal(r.reason, ["NO_INSTRUMENTED_PROVIDER"]);
  for (const field of ["observation_started_at", "attempts", "errors", "retries"]) if (r[field] !== null) invalid();
  return { unobserved_components: strings(r.unobserved_components) };
}
function analytics(value: unknown, teams: string[]) {
  const r = object(value);
  literal(r.connection_status, ["UNOBSERVED"]);
  if (r.availability === "UNAVAILABLE") {
    if (r.meta !== null) invalid();
    return { availability: "UNAVAILABLE" as const, reason: literal(r.reason, ["NO_PUBLISHED_BATCH", "SCOPE_NOT_PROVIDED"]), meta: null };
  }
  literal(r.availability, ["AVAILABLE"]);
  if (r.reason !== null) invalid();
  const m = object(r.meta);
  scope(m.team_ids, teams);
  return { availability: "AVAILABLE" as const, reason: null, meta: {
    batch_id: text(m.batch_id), source: literal(m.source, ["LOCAL_SYNTHETIC", "FABRIC"]),
    source_as_of: timestamp(m.source_as_of), generated_at: timestamp(m.generated_at),
    published_at: timestamp(m.published_at), window_end: timestamp(m.window_end), stale: bool(m.stale),
    origin_verification: literal(m.origin_verification, ["SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED"]),
  } };
}
export function parseSummary(value: unknown, teams: string[], kind?: JobKind) {
  const { r, ...base } = envelope(value, teams), j = object(r.jobs), raw = object(j.raw_counts);
  literal(r.coverage, ["ROUTED_CURRENT_CYCLE_VERSION"]);
  literal(j.unit, ["job"]);
  const kinds = kind ? [kind] : jobKinds;
  if (Object.keys(raw).sort().join() !== [...kinds].sort().join()) invalid();
  const raw_counts = kinds.map(job_kind => {
    const row = object(raw[job_kind]);
    return { job_kind, counts: jobStatuses.map(status => ({ status, count: integer(row[status]) })) };
  });
  const a = object(r.automation);
  let automation: { availability: "AVAILABLE"; paused: boolean } | { availability: "UNAVAILABLE"; reason: string };
  if (a.availability === "AVAILABLE") {
    automation = { availability: "AVAILABLE", paused: bool(object(a.state).paused) };
  } else {
    literal(a.availability, ["UNAVAILABLE"]);
    if (a.state !== null) invalid();
    automation = { availability: "UNAVAILABLE", reason: literal(a.reason, ["PERMISSION_REQUIRED", "AUTOMATION_CONTROL_UNAVAILABLE"]) };
  }
  const tasks = object(r.p1_tasks);
  literal(tasks.availability, ["UNAVAILABLE"]);
  literal(tasks.coverage, ["NO_TASK_PRODUCER"]);
  if (tasks.counts !== null) invalid();
  return { ...base, jobs: {
    eligible_pending: integer(j.eligible_pending), active_running: integer(j.active_running), retry_wait: integer(j.retry_wait),
    expired_running: integer(j.expired_running), superseded: integer(j.superseded), current_failed: integer(j.current_failed),
    generation_mismatch: j.generation_mismatch === null ? null : integer(j.generation_mismatch), raw_counts,
  }, automation, analytics: analytics(r.analytics, teams), ai: unobserved(r.ai) };
}
const safeErrors = ["AUTOMATION_PAUSED", "AUTOMATION_GENERATION_CHANGED", "LEASE_EXPIRED", "MAX_ATTEMPTS", "TIMEOUT", "RATE_LIMITED", "PROVIDER_UNAVAILABLE", "UNKNOWN_ERROR"] as const;
export function parseJobs(value: unknown, teams: string[], kind?: JobKind, status?: JobStatus, limit = 20) {
  const { r, ...base } = envelope(value, teams);
  if (!Array.isArray(r.items) || r.items.length > limit) invalid();
  const items = r.items.map(value => {
    const j = object(value), job_kind = literal(j.job_kind, jobKinds), job_status = literal(j.status, jobStatuses);
    if ((kind && job_kind !== kind) || (status && job_status !== status)) invalid();
    return { job_id: uuid(j.job_id), ticket_id: uuid(j.ticket_id), job_kind, status: job_status,
      attempt: integer(j.attempt), updated_at: timestamp(j.updated_at), next_attempt_at: timestamp(j.next_attempt_at),
      lease_expires_at: j.lease_expires_at === null ? null : timestamp(j.lease_expires_at),
      error_code: j.error_code === null ? null : literal(j.error_code, safeErrors),
      scope_status: literal(j.scope_status, ["CURRENT", "SUPERSEDED"]), data_origin: text(j.data_origin),
      cycle_no: integer(j.cycle_no), expected_ticket_version: integer(j.expected_ticket_version),
    };
  });
  if (new Set(items.map(j => j.job_id)).size !== items.length) invalid();
  const next_cursor = r.next_cursor === null ? null : text(r.next_cursor);
  if (next_cursor && (!items.length || next_cursor.length > 512)) invalid();
  return { ...base, items, next_cursor };
}
export function parseAiCalls(value: unknown, teams: string[]) {
  const { r, ...base } = envelope(value, teams), observed = unobserved(r);
  for (const field of ["attempt_count", "failed_attempt_count", "retry_attempt_count", "error_rate", "counts_by_code", "started_count", "unknown_count"]) if (r[field] !== null) invalid();
  const sources = object(r.sources);
  if (sources.MOCK !== null || sources.AZURE_OPENAI !== null) invalid();
  const from = timestamp(r.from), to = timestamp(r.to), duration = Date.parse(to) - Date.parse(from);
  if (duration <= 0 || duration > 7 * 86400_000) invalid();
  return { ...base, ...observed, from, to };
}
export type MonitorSummary = ReturnType<typeof parseSummary>;
export type JobPage = ReturnType<typeof parseJobs>;
export type AiCalls = ReturnType<typeof parseAiCalls>;
