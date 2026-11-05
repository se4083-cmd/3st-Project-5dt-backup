import { ApiError } from "../../api";
import type { AuthManager } from "../../auth/store";
import { parseVocList } from "../../operations";
import { workspaceClient } from "../workspace/client";
import { invalid, object, same, scope, unique, uuid } from "../workspace/validate";
import { parseVOC, parseVOCHistory, type GenerateBody, type ReviewBody } from "./contracts";
export function createVOCClient(auth: AuthManager) {
  const c = workspaceClient(auth), root = "/api/v1/admin/p1/voc-proposals";
  return {
    async history(cursor: string | null, signal: AbortSignal) { const allowed = c.access("P1_VOC_READ"), q = new URLSearchParams({ limit: "20" }); if (cursor) q.set("cursor", cursor); return c.decode(c.get(`${root}?${q}`, signal), v => parseVOCHistory(v, allowed)); },
    async detail(id: string, signal: AbortSignal) { const allowed = c.access("P1_VOC_READ"); id = uuid(id); return c.decode(c.get(`${root}/${id}`, signal), v => parseVOC(v, allowed, id)); },
    async generate(body: GenerateBody, key: string) {
      const allowed = c.access("P1_VOC_GENERATE", body.team_ids); uuid(body.product_id); if (body.team_ids.length > 8) throw new ApiError(422, "INVALID_TEAM_COUNT");
      return c.decode(c.post(root, body, key), v => { const data = parseVOC(v, allowed); if (data.product_id !== body.product_id || !same(data.team_ids, body.team_ids)) invalid(); return data; });
    },
    async review(id: string, body: ReviewBody, key: string) {
      const allowed = c.access("P1_VOC_REVIEW"); id = uuid(id);
      if (!Number.isSafeInteger(body.expected_revision) || body.expected_revision < 1 || !["APPROVED", "REJECTED"].includes(body.decision) || !body.reason.trim() || [...body.reason].length > 500) throw new ApiError(422, "INVALID_REVIEW");
      return c.decode(c.post(`${root}/${id}/reviews`, body, key), v => { const data = parseVOC(v, allowed, id); if (data.status !== body.decision || data.revision !== body.expected_revision + 1) invalid(); return data; });
    },
    async products(teams: string[], signal: AbortSignal) {
      c.access("P1_VOC_GENERATE", teams); if (teams.length > 8) throw new ApiError(422, "INVALID_TEAM_COUNT");
      const q = new URLSearchParams(teams.map(t => ["team_ids", t]));
      const parse = (v: unknown) => { const list = parseVocList(v); if (list.meta && !same(scope(object(object(v).meta).team_ids, teams), teams)) invalid(); return { ...list, items: list.items.map(i => ({ ...i, product_id: uuid(i.product_id) })) }; };
      const top = await c.decode(auth.request(`/api/v1/admin/analytics/voc/top?${q}`, { signal }), parse);
      if (!top.data.meta) return top;
      q.set("batch_id", uuid(top.data.meta.batch_id));
      const rest = await c.decode(auth.request(`/api/v1/admin/analytics/voc/unavailable?${q}`, { signal }), parse);
      if (rest.data.meta?.batch_id !== top.data.meta.batch_id) invalid();
      const items = [...top.data.items, ...rest.data.items]; unique(items.map(i => i.product_id)); return { ...top, data: { ...top.data, items } };
    },
  };
}
