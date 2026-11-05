import { ApiError } from "../../api";
import type { AuthManager } from "../../auth/store";
import { hasCapability } from "../../auth/session";
export type Saved = { href: string; requestId?: string; replayed?: boolean; status?: string; reason?: string | null };
export type Intent = { body: object; key: string; owner: string; teams: string[]; capability: string; readCapability: string; phase: "sending" | "error" | "conflict" | "done"; error?: ApiError; saved?: Saved };
// Intent/key/body survive navigation and same-login revalidation, never logout.
export class Mutations {
  private entries: Record<string, Intent> = {};
  private jobs = new Map<string, () => Promise<Saved>>();
  private listeners = new Set<() => void>();
  constructor(private auth: AuthManager) {
    auth.subscribe(() => {
      const state = auth.getSnapshot();
      if (["anonymous", "authenticating"].includes(state.phase)) { this.jobs.clear(); this.replace({}); }
      else if (state.phase === "ready") {
        const next = Object.fromEntries(Object.entries(this.entries).filter(([slot, e]) => {
          const keep = state.session?.userId === e.owner && hasCapability(state.session, e.capability) && hasCapability(state.session, e.readCapability) && e.teams.every(id => state.session!.allowedTeamIds.includes(id));
          if (!keep) this.jobs.delete(slot); return keep;
        })); this.replace(next);
      }
    });
  }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getSnapshot = () => this.entries;
  private replace(entries: Record<string, Intent>) { this.entries = entries; this.listeners.forEach(l => l()); }
  reset(slot: string) { if (this.entries[slot]?.phase === "sending") return; this.jobs.delete(slot); const next = { ...this.entries }; delete next[slot]; this.replace(next); }
  start<T extends object>(slot: string, body: T, teams: string[], capability: string, readCapability: string, execute: (body: T, key: string) => Promise<Saved>) {
    const s = this.auth.getSnapshot();
    if (this.entries[slot] || s.phase !== "ready" || !hasCapability(s.session, capability) || !hasCapability(s.session, readCapability) || !teams.length || !teams.every(t => s.session!.allowedTeamIds.includes(t))) return Promise.resolve();
    const original = structuredClone(body), key = `p1-${crypto.randomUUID()}`;
    const entry: Intent = { body: original, key, teams: [...teams], owner: s.session!.userId, capability, readCapability, phase: "error" };
    this.entries = { ...this.entries, [slot]: entry }; this.jobs.set(slot, () => execute(original, key));
    return this.send(slot);
  }
  retry(slot: string) { return this.entries[slot]?.phase === "error" ? this.send(slot) : Promise.resolve(); }
  private async send(slot: string) {
    const entry = this.entries[slot], job = this.jobs.get(slot);
    if (!entry || !job || entry.phase === "sending") return;
    this.replace({ ...this.entries, [slot]: { ...entry, phase: "sending", error: undefined } });
    try { const saved = await job(); if (this.entries[slot]?.key === entry.key) this.replace({ ...this.entries, [slot]: { ...entry, phase: "done", saved } }); }
    catch (error) {
      if (this.entries[slot]?.key !== entry.key) return;
      const safe = error instanceof ApiError ? error : new ApiError(0, "WRITE_OUTCOME_UNKNOWN");
      this.replace({ ...this.entries, [slot]: { ...entry, phase: safe.status === 409 ? "conflict" : "error", error: safe } });
    }
  }
}
const stores = new WeakMap<AuthManager, Mutations>();
export function mutations(auth: AuthManager) { let s = stores.get(auth); if (!s) { s = new Mutations(auth); stores.set(auth, s); } return s; }
