import { ApiError } from "../../api";
export const invalid = (): never => { throw new ApiError(0, "INVALID_RESPONSE"); };
export const object = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : invalid();
export const array = (v: unknown): unknown[] => Array.isArray(v) ? v : invalid();
export const text = (v: unknown, max = 20000): string => typeof v === "string" && !!v.trim() && [...v].length <= max ? v : invalid();
export const literal = <T extends string>(v: unknown, choices: readonly T[]): T => choices.includes(v as T) ? v as T : invalid();
export const uuid = (v: unknown): string => typeof v === "string" && /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v) ? v.toLowerCase() : invalid();
export const timestamp = (v: unknown): string => typeof v === "string" && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)) ? v : invalid();
export const hash = (v: unknown): string => typeof v === "string" && /^[a-f\d]{64}$/.test(v) ? v : invalid();
export const bool = (v: unknown): boolean => typeof v === "boolean" ? v : invalid();
export const count = (v: unknown): number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 ? v : invalid();
export const positive = (v: unknown): number => { const n = count(v); return n > 0 ? n : invalid(); };
export const number = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number => typeof v === "number" && Number.isFinite(v) && v >= min && v <= max ? v : invalid();
export const nullable = <T,>(v: unknown, parse: (v: unknown) => T): T | null => v === null ? null : parse(v);
export const unique = (ids: string[]): string[] => new Set(ids).size === ids.length ? ids : invalid();
export function scope(v: unknown, allowed: string[]) {
  const ids = unique(array(v).map(uuid));
  if (!ids.length || !ids.every(id => allowed.includes(id))) invalid();
  return ids.sort();
}
export const same = (a: string[], b: string[]) => [...a].sort().join() === [...b].sort().join();
export function page<T>(v: unknown, parse: (v: unknown) => T, id: (v: T) => string, limit = 20) {
  const r = object(v), items = array(r.items).map(parse), next_cursor = nullable(r.next_cursor, v => text(v, 512));
  unique(items.map(id)); if (items.length > limit || (next_cursor && !items.length)) invalid();
  return { items, next_cursor };
}
