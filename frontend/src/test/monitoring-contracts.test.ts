import { describe, expect, it } from "vitest";
import { parseAiCalls, parseJobs, parseSummary } from "../features/monitoring/contracts";
import { aiCalls, analyticsMeta, job, page, summary, teamA, teamB } from "./monitoring-fixtures";

describe("actual monitoring response boundaries", () => {
  it("keeps successful zero counts, unknown generation, and unobserved AI distinct", () => {
    const s = parseSummary(summary(), [teamA]);
    expect(s.jobs.current_failed).toBe(0);
    expect(s.jobs.generation_mismatch).toBeNull();
    expect(s.analytics.availability).toBe("UNAVAILABLE");
    expect(parseAiCalls(aiCalls(), [teamA]).unobserved_components).toContain("AZURE_OPENAI");
    expect(parseJobs(page(), [teamA]).items).toEqual([]);
  });
  it("rejects a wrong team scope in every endpoint and in published analytics", () => {
    expect(() => parseSummary(summary([teamB]), [teamA])).toThrow("INVALID_RESPONSE");
    expect(() => parseJobs(page([teamB]), [teamA])).toThrow("INVALID_RESPONSE");
    expect(() => parseAiCalls(aiCalls([teamB]), [teamA])).toThrow("INVALID_RESPONSE");
    expect(() => parseSummary({ ...summary(), analytics: { availability: "AVAILABLE", reason: null, meta: analyticsMeta([teamB]), connection_status: "UNOBSERVED" } }, [teamA])).toThrow();
  });
  it.each([undefined, null, -1, 0.5, "0"])("rejects missing or invalid job counts: %s", value => {
    expect(() => parseSummary({ ...summary(), jobs: { ...summary().jobs, current_failed: value } }, [teamA])).toThrow();
  });
  it("rejects invented zero telemetry and timezone-free timestamps", () => {
    expect(() => parseAiCalls({ ...aiCalls(), error_rate: 0 }, [teamA])).toThrow();
    expect(() => parseAiCalls({ ...aiCalls(), as_of: "2026-11-04T03:00:00" }, [teamA])).toThrow();
    expect(() => parseAiCalls({ ...aiCalls(), from: "2026-10-01T03:00:00Z" }, [teamA])).toThrow();
  });
  it("checks job filter consistency, duplicate IDs, page bounds and empty cursor pages", () => {
    expect(() => parseSummary(summary(), [teamA], "AUTO")).toThrow();
    expect(() => parseJobs(page([teamA], [job()]), [teamA], "HANDOFF")).toThrow();
    expect(() => parseJobs(page([teamA], [job()]), [teamA], undefined, "RUNNING")).toThrow();
    expect(() => parseJobs(page([teamA], [job(), job()]), [teamA])).toThrow();
    expect(() => parseJobs(page([teamA], [job()]), [teamA], undefined, undefined, 0)).toThrow();
    expect(() => parseJobs(page([teamA], [], "cursor"), [teamA])).toThrow();
  });
  it("accepts declared Fabric freshness without claiming connection verification", () => {
    const s = parseSummary({ ...summary(), analytics: { availability: "AVAILABLE", reason: null, meta: analyticsMeta([teamA], false, "FABRIC"), connection_status: "UNOBSERVED" } }, [teamA]);
    expect(s.analytics.meta?.stale).toBe(false);
    expect(s.analytics.meta?.origin_verification).toBe("SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED");
  });
});
