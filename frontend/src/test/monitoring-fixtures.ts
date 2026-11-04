// Synthetic fixtures matching the current FastAPI monitoring contract; no external telemetry.
export const teamA = "00000000-0000-0000-0000-000000000002";
export const teamB = "00000000-0000-0000-0000-000000000003";
export const asOf = "2026-11-04T03:00:00Z";
const counts = () => ({ PENDING: 0, RUNNING: 0, RETRY: 0, SUCCEEDED: 0, FAILED: 0, HANDED_OFF: 0, CANCELLED: 0 });
export const unobserved = () => ({ availability: "UNOBSERVED", coverage: "NONE", observation_started_at: null, attempts: null, errors: null, retries: null, reason: "NO_INSTRUMENTED_PROVIDER", unobserved_components: ["BACKEND_B", "P1_VOC", "AZURE_OPENAI", "AZURE_SEARCH", "FABRIC_CONNECTION"] });
export function summary(teams = [teamA], kind = "") {
  return { as_of: asOf, selected_team_ids: teams, coverage: "ROUTED_CURRENT_CYCLE_VERSION", excluded_definition: "Server definitions",
    automation: { availability: "UNAVAILABLE", state: null, reason: "PERMISSION_REQUIRED" },
    jobs: { unit: "job", raw_counts: kind ? { [kind]: counts() } : { AUTO: counts(), HANDOFF: counts() }, eligible_pending: 0, active_running: 0, retry_wait: 0, expired_running: 0, generation_mismatch: null, superseded: 0, current_failed: 0 },
    p1_tasks: { unit: "task", availability: "UNAVAILABLE", counts: null, coverage: "NO_TASK_PRODUCER", reason: "VOC_AND_POLICY_NOT_IMPLEMENTED" },
    analytics: { availability: "UNAVAILABLE", reason: "NO_PUBLISHED_BATCH", meta: null, connection_status: "UNOBSERVED" }, ai: unobserved(),
  };
}
export const analyticsMeta = (teams = [teamA], stale = true, source = "LOCAL_SYNTHETIC") => ({ batch_id: "synthetic-batch", source, source_as_of: "2026-10-31T03:00:00Z", generated_at: "2026-10-31T03:00:00Z", published_at: "2026-11-01T03:00:00Z", window_end: "2026-10-30T15:00:00Z", stale, origin_verification: "SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED", team_ids: teams });
export const job = (id = "00000000-0000-0000-0000-000000000010") => ({ job_id: id, ticket_id: "00000000-0000-0000-0000-000000000020", job_kind: "AUTO", status: "FAILED", attempt: 3, next_attempt_at: asOf, lease_expires_at: null, updated_at: asOf, cycle_no: 1, expected_ticket_version: 2, scope_status: "CURRENT", data_origin: "SYNTHETIC", error_code: "TIMEOUT" });
export const page = (teams = [teamA], items: ReturnType<typeof job>[] = [], next_cursor: string | null = null) => ({ as_of: asOf, selected_team_ids: teams, items, next_cursor });
export const aiCalls = (teams = [teamA]) => ({ ...unobserved(), as_of: asOf, selected_team_ids: teams, from: "2026-11-03T03:00:00Z", to: asOf, attempt_count: null, failed_attempt_count: null, retry_attempt_count: null, error_rate: null, counts_by_code: null, started_count: null, unknown_count: null, sources: { MOCK: null, AZURE_OPENAI: null } });
export const monitorSession = (teams = [teamA], caps = ["P1_MONITOR_READ"]) => ({ userId: "00000000-0000-0000-0000-000000000001", displayName: "테스트 관리자", role: "ADMIN", active: true, permissions: ["OPERATIONS_READ"], allowedTeamIds: teams, scopeKey: "scope-test", capabilities: caps });
export const json = (value: unknown, status = 200, requestId = "monitor-test-request") => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", "X-Request-ID": requestId } });
