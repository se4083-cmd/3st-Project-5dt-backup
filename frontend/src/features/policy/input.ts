import { ApiError } from "../../api";
export type Content = { title: string; body: string; source_document_id: string | null };
export type RegisterBody = Content & { policy_key: string; team_ids: string[] };
export type AppendBody = Content & { expected_previous_version: number };
export type CompareBody = { from_version_id: string | null; to_version_id: string };
export type ReviewBody = { expected_revision: number; decision: "APPROVED" | "REJECTED"; reason: string };
export const normalize = (s: string) => s.replace(/\r\n?/g, "\n");
function lines(s: string) { const rows = s.split(/[\n\r\v\f\u001c-\u001e\u0085\u2028\u2029]/); if (!rows.at(-1)) rows.pop(); return rows.length; }
export function contentError(c: Content) {
  for (const [name, raw, max] of [["제목", c.title, 200], ["본문", c.body, 20000]] as const) { const s = normalize(raw); if (!s.replace(/[\s\u001c-\u001f\u0085]/g, "") || s.includes("\0") || [...s].length > max || lines(s) > 500) return `${name}: 비공백·NUL 없음·최대${max}자·500줄이 필요합니다.`; }
  if (c.source_document_id && !/^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(c.source_document_id)) return "출처 문서 ID는 UUID여야 합니다.";
  return null;
}
export function prepare(c: Content): Content { if (contentError(c)) throw new ApiError(422, "INVALID_POLICY_CONTENT"); return { title: normalize(c.title), body: normalize(c.body), source_document_id: c.source_document_id?.toLowerCase() || null }; }
export function registerError(c: RegisterBody) { return !/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(c.policy_key) ? "정책 key는 영문 시작·영문/숫자/_.-·최대64자입니다." : !c.team_ids.length || c.team_ids.length > 8 || new Set(c.team_ids).size !== c.team_ids.length ? "팀을 중복 없이 1–8개 선택하세요." : contentError(c); }
