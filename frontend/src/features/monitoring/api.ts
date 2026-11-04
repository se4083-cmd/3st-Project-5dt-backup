import { ApiError } from "../../api";
import type { AuthManager } from "../../auth/store";
import { createP1Client } from "../p1/client";
import { parseAiCalls, parseJobs, parseSummary, type JobKind, type JobStatus } from "./contracts";

export function createMonitoringClient(auth: AuthManager) {
  const client = createP1Client(auth);
  async function get<T>(endpoint: string, params: URLSearchParams, parse: (data: unknown) => T, signal: AbortSignal) {
    const response = await client.get(`/api/v1/admin/p1/monitoring/${endpoint}?${params}`, signal);
    try { return { data: parse(response.data), requestId: response.requestId }; }
    catch (error) {
      if (error instanceof ApiError) throw new ApiError(error.status, error.code, response.requestId);
      throw error;
    }
  }
  // Explicit selected teams are checked again against the response, including an omitted all-teams query.
  const params = (team: string) => new URLSearchParams(team ? [["team_ids", team]] : []);
  return {
    summary(team: string, teams: string[], kind: JobKind | undefined, signal: AbortSignal) {
      const q = params(team); if (kind) q.set("job_kind", kind);
      return get("summary", q, data => parseSummary(data, teams, kind), signal);
    },
    jobs(team: string, teams: string[], kind: JobKind | undefined, status: JobStatus | undefined, limit: number, cursor: string | null, signal: AbortSignal) {
      const q = params(team); if (kind) q.set("job_kind", kind); if (status) q.set("status", status);
      q.set("limit", String(limit)); if (cursor) q.set("cursor", cursor);
      return get("jobs", q, data => parseJobs(data, teams, kind, status, limit), signal);
    },
    aiCalls(team: string, teams: string[], signal: AbortSignal) {
      return get("ai-calls", params(team), data => parseAiCalls(data, teams), signal);
    },
  };
}
