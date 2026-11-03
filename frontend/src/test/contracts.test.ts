import { describe, expect, it, vi } from "vitest";
import { can, countTotal, overdueMinutes, percent } from "../domain";
import {
  ApiError,
  createHttpClient,
  parseOverview,
  parseSession,
  requestJson,
} from "../api";
import { fixtureOverview, fixtureSession } from "../fixtures";

describe("Manager scope and workload contract", () => {
  it("requires active ADMIN, explicit permission and a non-empty team scope", () => {
    const manager = fixtureSession("manager");
    expect(can(manager, "OPERATIONS_READ")).toBe(true);
    for (const profile of ["agent", "customer", "inactive"] as const)
      expect(can(fixtureSession(profile), "OPERATIONS_READ")).toBe(false);
    expect(can({ ...manager, allowedTeamIds: [] }, "OPERATIONS_READ")).toBe(
      false,
    );
    expect(can(fixtureSession("limited"), "AUTOMATION_MANAGE")).toBe(false);
    expect(
      parseSession({ ...manager, permissions: ["UNKNOWN"] }).permissions,
    ).toEqual([]);
    expect(() => parseSession({ ...manager, active: "true" })).toThrow(
      ApiError,
    );
  });
  it("separates current tickets, follow-up tasks and period cycle KPI", () => {
    const manager = fixtureSession("manager"),
      overview = parseOverview(fixtureOverview(manager), manager);
    expect(countTotal(overview.workload)).toBe(14);
    expect(overview.workload.FOLLOWUP_PENDING).toBe(5);
    expect(overview.openFollowupTasks).toBe(6);
    expect(overview.previewTickets).toHaveLength(4);
    expect(percent(94, 120)).toBe(78.3);
    expect(percent(0, 0)).toBeNull();
    expect(overdueMinutes("2026-11-02T01:00:00Z", "2026-11-02T01:00:00Z")).toBe(
      0,
    );
  });
  it("rejects another user/scope, invalid counts, duplicate tickets and invalid analytics", () => {
    const session = fixtureSession("manager"),
      value = fixtureOverview(session);
    const invalid = [
      { ...value, userId: "other-user" },
      { ...value, scopeKey: "OTHER" },
      { ...value, workload: { ...value.workload, REVIEW: -1 } },
      { ...value, workload: { ...value.workload, REVIEW: 1 } },
      { ...value, reviewOverdue: 5 },
      { ...value, asOf: "2026-11-02T10:00:00" },
      {
        ...value,
        previewTickets: [value.previewTickets[0], value.previewTickets[0]],
      },
      {
        ...value,
        analytics: { status: "ready", numerator: 121, denominator: 120 },
      },
    ];
    for (const response of invalid)
      expect(() => parseOverview(response, session)).toThrow(ApiError);
    expect(
      parseOverview(fixtureOverview(session, "empty"), session).workload.REVIEW,
    ).toBe(0);
    expect(
      parseOverview(fixtureOverview(session, "not_ready"), session).analytics
        .status,
    ).toBe("not_ready");
  });
});
describe("read-only API boundary", () => {
  it("does not guess missing endpoints or fall back to fixtures", async () => {
    const client = createHttpClient({}),
      spy = vi.spyOn(globalThis, "fetch");
    await expect(
      client.getSession(new AbortController().signal),
    ).rejects.toMatchObject({ code: "CONTRACT_NOT_CONFIGURED" });
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
  it("keeps safe error code/trace and does not reflect the server message", async () => {
    const fake = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "RATE_LIMITED",
              trace_id: "trace-01",
              message: "<script>private detail</script>",
            },
          }),
          { status: 429 },
        ),
      );
    await expect(
      requestJson("/api/test", new AbortController().signal, fake),
    ).rejects.toMatchObject({
      status: 429,
      code: "RATE_LIMITED",
      traceId: "trace-01",
      message: "RATE_LIMITED",
    });
    expect(fake.mock.calls[0][1]).toMatchObject({
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
    });
    expect(fake.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });
  it("rejects non-JSON successful responses and reports network failure", async () => {
    await expect(
      requestJson(
        "/api/test",
        new AbortController().signal,
        vi.fn().mockResolvedValue(new Response("<html>login</html>")),
      ),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    await expect(
      requestJson(
        "/api/test",
        new AbortController().signal,
        vi.fn().mockRejectedValue(new Error("offline")),
      ),
    ).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
