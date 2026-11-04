import { ApiError, parseSession } from "../api";
import { permissions, type Permission, type Session } from "../domain";

export type P1Session = Session & { capabilities: string[] };
const uuid = /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i;
export function parseP1Session(value: unknown): P1Session {
  const base = parseSession(value);
  const v = value as Record<string, unknown>;
  if (base.role !== "ADMIN" || !base.active || !uuid.test(base.userId) ||
      !base.allowedTeamIds.length || !base.allowedTeamIds.every(t => uuid.test(t)) ||
      new Set(base.allowedTeamIds).size !== base.allowedTeamIds.length ||
      !Array.isArray(v.capabilities) || !v.capabilities.every(c => typeof c === "string" && /^[A-Z][A-Z0-9_]{0,79}$/.test(c))) {
    throw new ApiError(0, "INVALID_RESPONSE");
  }
  const capabilities = [...new Set(v.capabilities as string[])].sort();
  // Reuse only identical, explicitly granted legacy capabilities. Do not invent
  // INQUIRY_READ/FOLLOWUP_READ/QUALITY rights from ADMIN or the team list.
  return { ...base, capabilities, permissions: [...new Set([...base.permissions,
    ...capabilities.filter(c => permissions.includes(c as Permission)) as Permission[]])] };
}
export function hasCapability(session: P1Session | null, capability: string): boolean {
  return !!session?.active && session.role === "ADMIN" && session.allowedTeamIds.length > 0 && session.capabilities.includes(capability);
}
