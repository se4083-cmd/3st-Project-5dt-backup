import { ApiError } from "../../api";
import { hasCapability } from "../../auth/session";
import type { AuthManager } from "../../auth/store";
import type { ApiResponse } from "../../auth/transport";
import { createP1Client } from "../p1/client";
import { scope } from "./validate";
export function workspaceClient(auth: AuthManager) {
  const client = createP1Client(auth);
  function access(capability: string, teams?: string[]) {
    const { phase, session } = auth.getSnapshot();
    if (phase !== "ready" || !hasCapability(session, capability)) throw new ApiError(403, "EXPLICIT_PERMISSION_REQUIRED");
    if (teams) scope(teams, session!.allowedTeamIds);
    return session!.allowedTeamIds;
  }
  async function decode<T>(request: Promise<ApiResponse>, parse: (v: unknown) => T) {
    const r = await request;
    try { return { ...r, data: parse(r.data) }; }
    catch (error) { if (error instanceof ApiError) throw new ApiError(error.status, error.code, r.requestId); throw error; }
  }
  return { ...client, access, decode };
}
