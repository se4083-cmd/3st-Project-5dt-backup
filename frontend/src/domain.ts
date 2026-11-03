export const permissions = [
  "OPERATIONS_READ",
  "INQUIRY_READ",
  "FOLLOWUP_READ",
  "PRODUCT_READ",
  "AUTOMATION_MANAGE",
] as const;
export type Permission = (typeof permissions)[number];
export type Role = "ADMIN" | "AGENT" | "ANALYST" | "CUSTOMER";
export type Session = {
  userId: string;
  displayName: string;
  role: Role;
  active: boolean;
  permissions: Permission[];
  allowedTeamIds: string[];
  scopeKey: string;
};
export const workStates = [
  "REVIEW",
  "WORKING",
  "FOLLOWUP_PENDING",
  "AI_RUNNING",
] as const;
export type WorkState = (typeof workStates)[number];
export const workLabels: Record<WorkState, string> = {
  REVIEW: "검토 대기",
  WORKING: "내가 처리 중",
  FOLLOWUP_PENDING: "후속 대기",
  AI_RUNNING: "AI 안내 진행",
};
export type TicketPreview = {
  id: string;
  subject: string;
  reason: string;
  state: WorkState;
  firstResponseDueAt: string;
};
export type Analytics =
  | { status: "not_ready" }
  | {
      status: "ready" | "stale";
      asOf: string;
      periodLabel: string;
      numerator: number;
      denominator: number;
    };
export type Overview = {
  userId: string;
  scopeKey: string;
  asOf: string;
  source: "synthetic" | "live";
  workload: Record<WorkState, number>;
  reviewOverdue: number;
  openFollowupTasks: number;
  previewTickets: TicketPreview[];
  analytics: Analytics;
};
export function can(session: Session | null, permission: Permission): boolean {
  return (
    !!session?.active &&
    session.role === "ADMIN" &&
    session.allowedTeamIds.length > 0 &&
    session.permissions.includes(permission)
  );
}
export const sessionKey = (s: Session) =>
  JSON.stringify([
    s.userId,
    s.role,
    s.active,
    s.scopeKey,
    [...s.permissions].sort(),
    [...s.allowedTeamIds].sort(),
  ]);
export function countTotal(workload: Overview["workload"]) {
  return workStates.reduce((sum, key) => sum + workload[key], 0);
}
export function percent(n: number, d: number) {
  return d === 0 ? null : Number(((n / d) * 100).toFixed(1));
}
export const kst = (value: string) =>
  new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
export const overdueMinutes = (due: string, asOf: string) =>
  Math.max(0, Math.ceil((Date.parse(asOf) - Date.parse(due)) / 60_000));
