import { ApiError, requestJson } from "./api";
import type { Profile } from "./fixtures";

export type Page<T> = { items: T[]; next_cursor: string | null };
export type QueueItem = {
  ticket_id: string;
  cycle_no: number;
  reason_code: string;
  route_team_id: string | null;
  stage: string;
  queued_at: string;
  waiting_seconds: number;
  automatic_state: string;
};
export type QueuePage = Page<QueueItem> & {
  total: number;
  counts: Record<string, number>;
  as_of: string;
};
export type StaffDetail = {
  ticket_id: string;
  customer_ref: string;
  cycle_no: number;
  revision: number;
  as_of: string;
  material_status: string;
  current_proposals: {
    suggestion_id: string;
    record_state: string;
    evidence_state: string;
    synthetic: boolean;
    approvals: { record_state: string; usable_for_execution: false }[];
  }[];
  execution_authority: "DISPLAY_ONLY_NOT_AUTHORIZATION";
};
export type Followup = {
  action_id: string;
  ticket_id: string | null;
  product_id: string | null;
  kind: string;
  status: "OPEN" | "IN_PROGRESS" | "DONE" | "CANCELLED";
  owner_user_id: string | null;
  due_at: string | null;
  revision: number;
  needs_handover: boolean;
  public_note: string | null;
  internal_note: string | null;
};
export type VocRisk = {
  product_id: string;
  data_status: "ELIGIBLE" | "LOW_SAMPLE" | "DATA_MISSING" | "QUALITY_BLOCKED";
  score: string | null;
  rank: number | null;
  risk_band: string | null;
  metrics: {
    C: number;
    P: number;
    S: number;
    N: number;
    M: number;
    U: number;
    K: number;
    top_issue: string | null;
  };
};
export type VocMeta = {
  batch_id: string;
  scope_key: string;
  source: "LOCAL_SYNTHETIC" | "FABRIC";
  source_as_of: string;
  stale: boolean;
  is_current: boolean;
};
export type VocList = {
  availability: "AVAILABLE" | "UNAVAILABLE";
  reason: string | null;
  meta: VocMeta | null;
  items: VocRisk[];
};
export type ProductDetail = Omit<VocList, "items"> & {
  product: VocRisk | null;
  trend: { day: string; episode_count: number; unresolved_count: number }[];
};
export type QualitySample = {
  sample_id: string;
  message_id: string;
  rubric_version: string;
  assigned_reviewer_id: string;
  status: "OPEN" | "VOID";
  current_revision: number;
  selected_at: string;
};
export type QualityMaterial = {
  sample_id: string;
  origin: "APPLICATION" | "SYNTHETIC" | "UNKNOWN";
  material_state: string;
  reply: string | null;
  question: string | null;
  model_version: string | null;
  prompt_version: string | null;
  as_of: string;
};
export type ControlState = {
  paused: boolean;
  revision: number;
  generation: number;
  reason_code: string;
  changed_at: string;
};
export type Customer360 = {
  customer_id: string;
  as_of: string;
  scope_policy: "per-ticket-v1";
  total_ticket_count: number;
  unresolved_ticket_count: number;
  reopened_ticket_count: number;
  followup_count: number;
  facts: [string, string, string];
  summary_contract: { status: "NOT_GENERATED" };
  recent_tickets: { ticket_id: string; stage: string; created_at: string }[];
};
export type Improvement = {
  action_id: string;
  product_id: string;
  status: Followup["status"];
  plan_access: "AVAILABLE" | "COMPARISON_SCOPE_DENIED";
  plan_refresh_required: boolean;
  current_plan_revision: number;
  analysis: { availability: "UNAVAILABLE"; reason: string; metrics: null };
};
export type OperationsClient = {
  getQueue(scope: "ROUTED" | "UNROUTED", reason: string, cursor: string, signal: AbortSignal): Promise<QueuePage>;
  getStaffDetail(id: string, signal: AbortSignal): Promise<StaffDetail>;
  getCustomer360(id: string, signal: AbortSignal): Promise<Customer360>;
  getFollowups(status: string, cursor: string, signal: AbortSignal): Promise<Page<Followup>>;
  getVocTop(signal: AbortSignal): Promise<VocList>;
  getVocImprovements(cursor: string, signal: AbortSignal): Promise<Page<Improvement>>;
  getVocUnavailable(batch: string, signal: AbortSignal): Promise<VocList>;
  getProductDetail(id: string, batch: string, signal: AbortSignal): Promise<ProductDetail>;
  getQualitySamples(cursor: string, signal: AbortSignal): Promise<Page<QualitySample>>;
  getQualityMaterial(id: string, signal: AbortSignal): Promise<QualityMaterial>;
  getControl(signal: AbortSignal): Promise<ControlState>;
};

const object = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new ApiError(0, "INVALID_RESPONSE");
  return v as Record<string, unknown>;
};
const str = (v: unknown) => {
  if (typeof v !== "string" || !v.trim()) throw new ApiError(0, "INVALID_RESPONSE");
  return v;
};
const count = (v: unknown) => {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < 0) throw new ApiError(0, "INVALID_RESPONSE");
  return v;
};
const date = (v: unknown) => {
  const value = str(v);
  if (!/(Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value)))
    throw new ApiError(0, "INVALID_RESPONSE");
  return value;
};
const nullable = (v: unknown, parse: (v: unknown) => string) => v === null ? null : parse(v);
const optionalText = (v: unknown) => {
  if (v === null) return null;
  if (typeof v !== "string") throw new ApiError(0, "INVALID_RESPONSE");
  return v;
};
const page = <T>(v: unknown, parse: (v: unknown) => T): Page<T> => {
  const data = object(v);
  if (!Array.isArray(data.items) || !(data.next_cursor === null || typeof data.next_cursor === "string"))
    throw new ApiError(0, "INVALID_RESPONSE");
  return { items: data.items.map(parse), next_cursor: data.next_cursor };
};
const queueItem = (v: unknown): QueueItem => {
  const d = object(v);
  return {
    ticket_id: str(d.ticket_id), cycle_no: count(d.cycle_no), reason_code: str(d.reason_code),
    route_team_id: nullable(d.route_team_id, str), stage: str(d.stage),
    queued_at: date(d.queued_at), waiting_seconds: count(d.waiting_seconds),
    automatic_state: str(d.automatic_state),
  };
};
export const parseQueue = (v: unknown): QueuePage => {
  const d = object(v), p = page(d, queueItem), rawCounts = object(d.counts);
  const counts = Object.fromEntries(Object.entries(rawCounts).map(([k, value]) => [k, count(value)]));
  const total = count(d.total);
  if (p.items.length > total || Object.values(counts).reduce((a, b) => a + b, 0) !== total ||
      new Set(p.items.map((x) => x.ticket_id)).size !== p.items.length)
    throw new ApiError(0, "INVALID_RESPONSE");
  return { ...p, total, counts, as_of: date(d.as_of) };
};
export const parseStaffDetail = (v: unknown): StaffDetail => {
  const d = object(v);
  if (!Array.isArray(d.current_proposals) || d.execution_authority !== "DISPLAY_ONLY_NOT_AUTHORIZATION")
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    ticket_id: str(d.ticket_id), customer_ref: str(d.customer_ref),
    cycle_no: count(d.cycle_no), revision: count(d.revision), as_of: date(d.as_of),
    material_status: str(d.material_status),
    current_proposals: d.current_proposals.map((item) => {
      const p = object(item);
      if (typeof p.synthetic !== "boolean" || !Array.isArray(p.approvals))
        throw new ApiError(0, "INVALID_RESPONSE");
      return {
        suggestion_id: str(p.suggestion_id), record_state: str(p.record_state),
        evidence_state: str(p.evidence_state), synthetic: p.synthetic,
        approvals: p.approvals.map((value) => {
          const a = object(value);
          if (a.usable_for_execution !== false) throw new ApiError(0, "INVALID_RESPONSE");
          return { record_state: str(a.record_state), usable_for_execution: false as const };
        }),
      };
    }),
    execution_authority: "DISPLAY_ONLY_NOT_AUTHORIZATION",
  };
};
const followup = (v: unknown): Followup => {
  const d = object(v);
  if (!["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"].includes(String(d.status)) ||
      typeof d.needs_handover !== "boolean")
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    action_id: str(d.action_id), ticket_id: nullable(d.ticket_id, str),
    product_id: nullable(d.product_id, str), kind: str(d.kind),
    status: d.status as Followup["status"], owner_user_id: nullable(d.owner_user_id, str),
    due_at: nullable(d.due_at, date), revision: count(d.revision),
    needs_handover: d.needs_handover,
    public_note: optionalText(d.public_note), internal_note: optionalText(d.internal_note),
  };
};
const risk = (v: unknown): VocRisk => {
  const d = object(v), m = object(d.metrics);
  if (!["ELIGIBLE", "LOW_SAMPLE", "DATA_MISSING", "QUALITY_BLOCKED"].includes(String(d.data_status)))
    throw new ApiError(0, "INVALID_RESPONSE");
  const score = d.score === null ? null : str(d.score);
  if (score !== null && (!/^\d+(\.\d+)?$/.test(score) || Number(score) > 100))
    throw new ApiError(0, "INVALID_RESPONSE");
  if ((d.data_status === "ELIGIBLE" && (score === null || d.rank === null || d.rank === 0 || d.risk_band === null)) ||
      (d.data_status !== "ELIGIBLE" && (score !== null || d.rank !== null || d.risk_band !== null)))
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    product_id: str(d.product_id), data_status: d.data_status as VocRisk["data_status"],
    score, rank: d.rank === null ? null : count(d.rank),
    risk_band: nullable(d.risk_band, str),
    metrics: {
      C: count(m.C), P: count(m.P), S: count(m.S), N: count(m.N),
      M: count(m.M), U: count(m.U), K: count(m.K),
      top_issue: nullable(m.top_issue, str),
    },
  };
};
const meta = (v: unknown): VocMeta | null => {
  if (v === null) return null;
  const d = object(v);
  if (!["LOCAL_SYNTHETIC", "FABRIC"].includes(String(d.source)) ||
      typeof d.stale !== "boolean" || typeof d.is_current !== "boolean")
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    batch_id: str(d.batch_id), scope_key: str(d.scope_key),
    source: d.source as VocMeta["source"], source_as_of: date(d.source_as_of),
    stale: d.stale, is_current: d.is_current,
  };
};
export const parseVocList = (v: unknown): VocList => {
  const d = object(v);
  if (!["AVAILABLE", "UNAVAILABLE"].includes(String(d.availability)) || !Array.isArray(d.items))
    throw new ApiError(0, "INVALID_RESPONSE");
  const m = meta(d.meta);
  if ((d.availability === "AVAILABLE") !== (m !== null) ||
      (d.availability === "UNAVAILABLE" && d.items.length))
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    availability: d.availability as VocList["availability"],
    reason: nullable(d.reason, str), meta: m, items: d.items.map(risk),
  };
};
const productDetail = (v: unknown): ProductDetail => {
  const d = object(v), base = parseVocList({ ...d, items: [] });
  if (!Array.isArray(d.trend)) throw new ApiError(0, "INVALID_RESPONSE");
  return {
    availability: base.availability, reason: base.reason, meta: base.meta,
    product: d.product === null ? null : risk(d.product),
    trend: d.trend.map((item) => {
      const t = object(item);
      return { day: str(t.day), episode_count: count(t.episode_count), unresolved_count: count(t.unresolved_count) };
    }),
  };
};
const qualitySample = (v: unknown): QualitySample => {
  const d = object(v);
  if (!["OPEN", "VOID"].includes(String(d.status))) throw new ApiError(0, "INVALID_RESPONSE");
  return {
    sample_id: str(d.sample_id), message_id: str(d.message_id),
    rubric_version: str(d.rubric_version), assigned_reviewer_id: str(d.assigned_reviewer_id),
    status: d.status as QualitySample["status"], current_revision: count(d.current_revision),
    selected_at: date(d.selected_at),
  };
};
const material = (v: unknown): QualityMaterial => {
  const d = object(v);
  if (!["APPLICATION", "SYNTHETIC", "UNKNOWN"].includes(String(d.origin)))
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    sample_id: str(d.sample_id), origin: d.origin as QualityMaterial["origin"],
    material_state: str(d.material_state), reply: optionalText(d.reply),
    question: optionalText(d.question), model_version: nullable(d.model_version, str),
    prompt_version: nullable(d.prompt_version, str), as_of: date(d.as_of),
  };
};
const control = (v: unknown): ControlState => {
  const d = object(v);
  if (typeof d.paused !== "boolean") throw new ApiError(0, "INVALID_RESPONSE");
  return {
    paused: d.paused, revision: count(d.revision), generation: count(d.generation),
    reason_code: str(d.reason_code), changed_at: date(d.changed_at),
  };
};
const customer360 = (v: unknown): Customer360 => {
  const d = object(v), summary = object(d.summary_contract);
  if (d.scope_policy !== "per-ticket-v1" || summary.status !== "NOT_GENERATED" ||
      !Array.isArray(d.facts) || d.facts.length !== 3 || !Array.isArray(d.recent_tickets))
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    customer_id: str(d.customer_id), as_of: date(d.as_of), scope_policy: "per-ticket-v1",
    total_ticket_count: count(d.total_ticket_count),
    unresolved_ticket_count: count(d.unresolved_ticket_count),
    reopened_ticket_count: count(d.reopened_ticket_count),
    followup_count: count(d.followup_count),
    facts: d.facts.map(str) as [string, string, string],
    summary_contract: { status: "NOT_GENERATED" },
    recent_tickets: d.recent_tickets.map((item) => {
      const t = object(item);
      return { ticket_id: str(t.ticket_id), stage: str(t.stage), created_at: date(t.created_at) };
    }),
  };
};
const improvement = (v: unknown): Improvement => {
  const d = object(v), f = object(d.followup), a = object(d.analysis);
  if (!["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"].includes(String(f.status)) ||
      !["AVAILABLE", "COMPARISON_SCOPE_DENIED"].includes(String(d.plan_access)) ||
      typeof d.plan_refresh_required !== "boolean" ||
      a.availability !== "UNAVAILABLE" || a.metrics !== null)
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    action_id: str(d.action_id), product_id: str(d.product_id),
    status: f.status as Followup["status"], plan_access: d.plan_access as Improvement["plan_access"],
    plan_refresh_required: d.plan_refresh_required, current_plan_revision: count(d.current_plan_revision),
    analysis: { availability: "UNAVAILABLE", reason: str(a.reason), metrics: null },
  };
};

const batch = "11111111-1111-4111-8111-111111111111";
const productA = "22222222-2222-4222-8222-222222222222";
const productB = "33333333-3333-4333-8333-333333333333";
const sampleId = "44444444-4444-4444-8444-444444444444";
const at = "2026-11-02T01:00:00Z";
const mockMeta: VocMeta = { batch_id: batch, scope_key: "ALL4", source: "LOCAL_SYNTHETIC", source_as_of: at, stale: false, is_current: true };
const risks: VocRisk[] = [
  { product_id: productA, data_status: "ELIGIBLE", score: "72.430000", rank: 1, risk_band: "HIGH",
    metrics: { C: 42, P: 28, S: 85, N: 16, M: 12, U: 8, K: 4, top_issue: "DAMAGED" } },
  { product_id: productB, data_status: "LOW_SAMPLE", score: null, rank: null, risk_band: null,
    metrics: { C: 3, P: 28, S: 2, N: 8, M: 1, U: 0, K: 0, top_issue: "DELIVERY_DELAY" } },
];
const mockQueue: QueueItem[] = [
  { ticket_id: "T-2401", cycle_no: 1, route_team_id: "DELIVERY", reason_code: "HUMAN_REQUEST", stage: "WAITING_FOR_SUPPORT", queued_at: at, waiting_seconds: 1200, automatic_state: "NOT_APPLICABLE" },
  { ticket_id: "T-2402", cycle_no: 1, route_team_id: "RETURN_REFUND", reason_code: "AUTO_FAILED", stage: "WAITING_FOR_SUPPORT", queued_at: at, waiting_seconds: 900, automatic_state: "HUMAN_REVIEW_REQUIRED" },
  { ticket_id: "T-2403", cycle_no: 1, route_team_id: "DELIVERY", reason_code: "UNASSIGNED", stage: "WAITING_FOR_SUPPORT", queued_at: at, waiting_seconds: 400, automatic_state: "PAUSED" },
];
const mockFollowups: Followup[] = [
  { action_id: "F-101", ticket_id: "T-2401", product_id: null, kind: "고객 재안내", status: "OPEN", owner_user_id: "demo-manager-1", due_at: "2026-11-03T01:00:00Z", revision: 1, needs_handover: false, public_note: "확인 후 다시 안내하겠습니다.", internal_note: "주문 상태 재확인" },
  { action_id: "F-102", ticket_id: null, product_id: productA, kind: "포장 개선", status: "IN_PROGRESS", owner_user_id: null, due_at: "2026-11-05T01:00:00Z", revision: 2, needs_handover: true, public_note: null, internal_note: "담당자 인수 필요" },
];
const wait = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = setTimeout(resolve, 90);
  signal.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
});
const params = (values: Record<string, string>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v) p.set(k, v);
  return p.size ? `?${p}` : "";
};
const uuid = (value: string) => {
  if (!/^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value))
    throw new ApiError(422, "INVALID_ID");
  return value;
};

export function createOperationsClient(mock: boolean, profile: Profile, transport: typeof fetch = fetch): OperationsClient {
  if (mock) return {
    async getQueue(scope, reason, cursor, signal) {
      await wait(signal);
      const visible = profile === "limited" ? mockQueue.filter((x) => x.route_team_id === "DELIVERY") : mockQueue;
      const filtered = visible.filter((x) => (scope === "UNROUTED" ? x.route_team_id === null : x.route_team_id !== null) && (!reason || x.reason_code === reason));
      const offset = cursor ? Number(cursor) : 0;
      return { items: filtered.slice(offset, offset + 2), next_cursor: offset + 2 < filtered.length ? String(offset + 2) : null,
        total: filtered.length, counts: Object.fromEntries([...new Set(filtered.map((x) => x.reason_code))].map((k) => [k, filtered.filter((x) => x.reason_code === k).length])), as_of: at };
    },
    async getStaffDetail(id, signal) {
      await wait(signal);
      const item = mockQueue.find((x) => x.ticket_id === id && (profile !== "limited" || x.route_team_id === "DELIVERY"));
      if (!item) throw new ApiError(404, "RESOURCE_NOT_FOUND");
      return { ticket_id: id, customer_ref: "55555555-5555-4555-8555-555555555555", cycle_no: 1, revision: 2, as_of: at,
        material_status: "SYNTHETIC_ONLY", current_proposals: [{
          suggestion_id: "66666666-6666-4666-8666-666666666666", record_state: "SYNTHETIC_HISTORY",
          evidence_state: "MISSING", synthetic: true, approvals: [],
        }], execution_authority: "DISPLAY_ONLY_NOT_AUTHORIZATION" };
    },
    async getCustomer360(id, signal) {
      await wait(signal);
      if (id !== "55555555-5555-4555-8555-555555555555") throw new ApiError(404, "RESOURCE_NOT_FOUND");
      return {
        customer_id: id, as_of: at, scope_policy: "per-ticket-v1",
        total_ticket_count: profile === "limited" ? 1 : 3,
        unresolved_ticket_count: 1, reopened_ticket_count: 1, followup_count: 2,
        facts: [`허용된 문의 이력 ${profile === "limited" ? 1 : 3}건`, "현재 미해결 문의 1건", "후속 업무 2건"],
        summary_contract: { status: "NOT_GENERATED" },
        recent_tickets: [{ ticket_id: "T-2401", stage: "WAITING_FOR_SUPPORT", created_at: at }],
      };
    },
    async getFollowups(status, cursor, signal) {
      await wait(signal);
      const items = mockFollowups.filter((x) => (!status || x.status === status) && (profile !== "limited" || x.ticket_id === "T-2401"));
      const offset = cursor ? Number(cursor) : 0;
      return { items: items.slice(offset, offset + 2), next_cursor: offset + 2 < items.length ? String(offset + 2) : null };
    },
    async getVocTop(signal) { await wait(signal); return { availability: "AVAILABLE", reason: null, meta: mockMeta, items: [risks[0]] }; },
    async getVocImprovements(_cursor, signal) {
      await wait(signal);
      return { items: [{ action_id: "F-102", product_id: productA, status: "IN_PROGRESS",
        plan_access: "AVAILABLE", plan_refresh_required: false, current_plan_revision: 2,
        analysis: { availability: "UNAVAILABLE", reason: "EFFECT_INTEGRATION_NOT_IMPLEMENTED", metrics: null } }], next_cursor: null };
    },
    async getVocUnavailable(batchId, signal) {
      await wait(signal);
      if (batchId !== batch) throw new ApiError(404, "RESOURCE_NOT_FOUND");
      return { availability: "AVAILABLE", reason: null, meta: mockMeta, items: [risks[1]] };
    },
    async getProductDetail(id, batchId, signal) {
      await wait(signal);
      if (batchId !== batch) throw new ApiError(404, "RESOURCE_NOT_FOUND");
      const product = risks.find((x) => x.product_id === id);
      if (!product) throw new ApiError(404, "RESOURCE_NOT_FOUND");
      return { availability: "AVAILABLE", reason: null, meta: mockMeta, product, trend: [
        { day: "2026-10-31", episode_count: 8, unresolved_count: 2 },
        { day: "2026-11-01", episode_count: 11, unresolved_count: 3 },
      ] };
    },
    async getQualitySamples(_cursor, signal) {
      await wait(signal);
      return { items: [{ sample_id: sampleId, message_id: "77777777-7777-4777-8777-777777777777", rubric_version: "DEV_QUALITY_V1",
        assigned_reviewer_id: "88888888-8888-4888-8888-888888888888", status: "OPEN", current_revision: 1, selected_at: at }], next_cursor: null };
    },
    async getQualityMaterial(id, signal) {
      await wait(signal);
      if (id !== sampleId) throw new ApiError(404, "RESOURCE_NOT_FOUND");
      return { sample_id: id, origin: "SYNTHETIC", material_state: "INSUFFICIENT_MATERIAL",
        reply: "상품 상태를 확인한 후 안내드리겠습니다.", question: "상품이 파손되어 도착했어요.",
        model_version: "demo-v1", prompt_version: "demo-v1", as_of: at };
    },
    async getControl(signal) { await wait(signal); return { paused: true, revision: 3, generation: 2, reason_code: "OPERATOR_PAUSE", changed_at: at }; },
  };
  const get = (path: string, signal: AbortSignal) => requestJson(path, signal, transport);
  const post = (path: string, body: object, signal: AbortSignal) => requestJson(path, signal, transport, { method: "POST", body });
  return {
    async getQueue(scope, reason, cursor, signal) {
      return parseQueue(await get(`/api/v1/staff/exception-queue${params({ queue_scope: scope, reason, cursor })}`, signal));
    },
    async getStaffDetail(id, signal) {
      return parseStaffDetail(await post(`/api/v1/staff/tickets/${uuid(id)}/internal`, { purpose_code: "ACTIVE_SUPPORT", include_history: false }, signal));
    },
    async getCustomer360(id, signal) {
      return customer360(await post(`/api/v1/staff/customers/${uuid(id)}/360`, { purpose_code: "ACTIVE_SUPPORT" }, signal));
    },
    async getFollowups(status, cursor, signal) {
      return page(await get(`/api/v1/staff/followups${params({ status, cursor })}`, signal), followup);
    },
    async getVocTop(signal) { return parseVocList(await get("/api/v1/admin/analytics/voc/top", signal)); },
    async getVocImprovements(cursor, signal) {
      return page(await get(`/api/v1/staff/voc-improvements${params({ cursor })}`, signal), improvement);
    },
    async getVocUnavailable(batchId, signal) {
      return parseVocList(await get(`/api/v1/admin/analytics/voc/unavailable${params({ batch_id: uuid(batchId) })}`, signal));
    },
    async getProductDetail(id, batchId, signal) {
      const data = productDetail(await get(`/api/v1/admin/analytics/products/${uuid(id)}${params({ batch_id: uuid(batchId) })}`, signal));
      if (data.availability === "AVAILABLE" &&
          (data.meta?.batch_id !== batchId || data.product?.product_id !== id))
        throw new ApiError(0, "INVALID_RESPONSE");
      return data;
    },
    async getQualitySamples(cursor, signal) {
      return page(await get(`/api/v1/staff/quality/samples${params({ cursor })}`, signal), qualitySample);
    },
    async getQualityMaterial(id, signal) {
      return material(await post(`/api/v1/staff/quality/samples/${uuid(id)}/material`, { purpose_code: "QUALITY_REVIEW" }, signal));
    },
    async getControl(signal) { return control(await get("/api/v1/staff/automation-control", signal)); },
  };
}
