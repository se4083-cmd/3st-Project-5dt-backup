import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { parseQueue, parseVocList } from "../operations";

describe("Backend A read contract", () => {
  it("rejects malformed queue counts and duplicate ticket identifiers", () => {
    const row = {
      ticket_id: "t1", cycle_no: 1, route_team_id: null, reason_code: "UNASSIGNED",
      stage: "WAITING_FOR_SUPPORT", queued_at: "2026-11-02T01:00:00Z",
      waiting_seconds: 20, automatic_state: "PAUSED",
    };
    const base = { items: [row], next_cursor: null, total: 1, counts: { UNASSIGNED: 1 }, as_of: "2026-11-02T01:00:00Z" };
    expect(parseQueue(base).total).toBe(1);
    expect(() => parseQueue({ ...base, total: 0 })).toThrow(ApiError);
    expect(() => parseQueue({ ...base, items: [row, row], total: 2 })).toThrow(ApiError);
    expect(() => parseQueue({ ...base, counts: { UNASSIGNED: -1 } })).toThrow(ApiError);
  });
  it("preserves unavailable and low-sample as null instead of zero", () => {
    expect(parseVocList({ availability: "UNAVAILABLE", reason: "NO_PUBLISHED_BATCH", meta: null, items: [] }))
      .toMatchObject({ availability: "UNAVAILABLE", meta: null, items: [] });
    const meta = { batch_id: "batch", scope_key: "ALL4", source: "LOCAL_SYNTHETIC",
      source_as_of: "2026-11-02T01:00:00Z", stale: false, is_current: true };
    const risk = { product_id: "p1", data_status: "LOW_SAMPLE", score: null, rank: null, risk_band: null,
      metrics: { C: 2, P: 1, S: 1, N: 5, M: 0, U: 0, K: 0, top_issue: null } };
    expect(parseVocList({ availability: "AVAILABLE", reason: null, meta, items: [risk] }).items[0].score).toBeNull();
    expect(() => parseVocList({ availability: "AVAILABLE", reason: null, meta, items: [{ ...risk, score: "0.000000" }] })).toThrow(ApiError);
  });
});
