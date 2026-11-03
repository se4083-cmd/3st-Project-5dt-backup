import { ApiError, parseOverview, type ApiClient } from "./api";
import { permissions, type Session, type Overview } from "./domain";

export const scenarios = [
  "normal",
  "loading",
  "empty",
  "network",
  "401",
  "403",
  "404",
  "409",
  "422",
  "429",
  "503",
  "not_ready",
  "stale",
] as const;
export type Scenario = (typeof scenarios)[number];
export const scenarioLabels: Record<Scenario, string> = {
  normal: "정상",
  loading: "로딩 유지",
  empty: "빈 결과",
  network: "통신 오류",
  "401": "인증 만료",
  "403": "권한 없음",
  "404": "대상 없음",
  "409": "버전 충돌",
  "422": "잘못된 조건",
  "429": "요청 제한",
  "503": "서비스 지연",
  not_ready: "분석 미집계",
  stale: "이전 정상 분석",
};
export type Profile =
  "manager" | "limited" | "agent" | "customer" | "inactive" | "signed_out";
export const profileLabels: Record<Profile, string> = {
  manager: "전체 팀 Manager",
  limited: "배송팀 Manager",
  agent: "상담사 · 접근 제한",
  customer: "고객 · 접근 제한",
  inactive: "비활성 계정",
  signed_out: "로그아웃",
};
export function fixtureSession(profile: Profile): Session {
  return {
    userId: profile === "limited" ? "demo-manager-2" : "demo-manager-1",
    displayName: profile === "limited" ? "배송팀 관리자" : "운영 관리자",
    role:
      profile === "agent"
        ? "AGENT"
        : profile === "customer"
          ? "CUSTOMER"
          : "ADMIN",
    active: profile !== "inactive",
    permissions:
      profile === "limited"
        ? ["OPERATIONS_READ", "INQUIRY_READ"]
        : [...permissions],
    allowedTeamIds:
      profile === "limited"
        ? ["DELIVERY"]
        : ["DELIVERY", "RETURN_REFUND", "PRODUCT_PAYMENT", "ACCOUNT_EXCEPTION"],
    scopeKey: profile === "limited" ? "DELIVERY" : "ALL4",
  };
}
export function fixtureOverview(
  session: Session,
  scenario: Scenario = "normal",
): Overview {
  const limited = session.scopeKey === "DELIVERY",
    empty = scenario === "empty";
  const tickets: Overview["previewTickets"] = [
    {
      id: "T-2401",
      subject: "상품 파손 확인",
      reason: "사람 연결 요청",
      state: "REVIEW",
      firstResponseDueAt: "2026-11-02T00:40:00Z",
    },
    {
      id: "T-2402",
      subject: "반품 조건 문의",
      reason: "정책 충돌",
      state: "REVIEW",
      firstResponseDueAt: "2026-11-02T00:55:00Z",
    },
    {
      id: "T-2403",
      subject: "배송 조회",
      reason: "주문 확인 실패",
      state: "REVIEW",
      firstResponseDueAt: "2026-11-02T01:30:00Z",
    },
    {
      id: "T-2404",
      subject: "결제 확인",
      reason: "조회 재시도 소진",
      state: "REVIEW",
      firstResponseDueAt: "2026-11-02T02:00:00Z",
    },
  ];
  return {
    userId: session.userId,
    scopeKey: session.scopeKey,
    asOf: "2026-11-02T01:00:00Z",
    source: "synthetic",
    workload: empty
      ? { REVIEW: 0, WORKING: 0, FOLLOWUP_PENDING: 0, AI_RUNNING: 0 }
      : limited
        ? { REVIEW: 1, WORKING: 1, FOLLOWUP_PENDING: 2, AI_RUNNING: 0 }
        : { REVIEW: 4, WORKING: 3, FOLLOWUP_PENDING: 5, AI_RUNNING: 2 },
    reviewOverdue: empty || limited ? 0 : 2,
    openFollowupTasks: empty ? 0 : limited ? 3 : 6,
    previewTickets: empty ? [] : limited ? [tickets[2]] : tickets,
    analytics:
      scenario === "not_ready" || limited || empty
        ? { status: "not_ready" }
        : {
            status: scenario === "stale" ? "stale" : "ready",
            asOf: "2026-10-31T03:00:00Z",
            periodLabel: "최근 7일 · 독립 합성 예시",
            numerator: 94,
            denominator: 120,
          },
  };
}
function delay(signal: AbortSignal, duration = 300): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, duration);
    signal.addEventListener("abort", abort, { once: true });
  });
}
export function createMockClient(
  profile: Profile,
  scenario: Scenario,
): ApiClient {
  return {
    async getSession(signal) {
      await delay(signal, 100);
      if (profile === "signed_out") throw new ApiError(401, "SESSION_EXPIRED");
      return fixtureSession(profile);
    },
    async getOverview(session, signal) {
      await delay(signal, scenario === "loading" ? 2_147_000_000 : 300);
      if (scenario === "network") throw new ApiError(0, "NETWORK_ERROR");
      if (/^\d+$/.test(scenario))
        throw new ApiError(Number(scenario), "DEMO_ERROR", "demo-" + scenario);
      return parseOverview(fixtureOverview(session, scenario), session);
    },
  };
}
