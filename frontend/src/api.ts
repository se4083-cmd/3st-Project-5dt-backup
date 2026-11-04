import {
  permissions,
  workStates,
  type Session,
  type Overview,
  type Permission,
  type WorkState,
} from "./domain";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public traceId?: string,
  ) {
    super(code);
  }
}
export function errorText(error: ApiError): {
  title: string;
  message: string;
  retry: boolean;
} {
  const values: Record<string, [string, string, boolean]> = {
    P1_DISABLED: ["P1 기능이 비활성화되어 있습니다", "서버의 P1 활성화 설정을 확인해 주세요.", false],
    VOC_DISABLED: ["VOC 기능이 비활성화되어 있습니다", "서버의 VOC 활성화 설정을 확인해 주세요.", false],
    POLICY_DISABLED: ["정책 기능이 비활성화되어 있습니다", "서버의 정책 활성화 설정을 확인해 주세요.", false],
    SESSION_EXPIRED: ["다시 로그인해 주세요", "세션이 만료되어 보호 데이터를 제거했습니다.", false],
    CONTRACT_NOT_CONFIGURED: [
      "백엔드 연결 준비 중",
      "인증 정보와 운영 홈의 API 계약을 먼저 설정해 주세요.",
      false,
    ],
    INVALID_RESPONSE: [
      "응답 형식을 확인해 주세요",
      "약속한 응답과 달라 업무 수치를 표시하지 않았습니다.",
      true,
    ],
    SCOPE_MISMATCH: [
      "조회 범위가 변경되었습니다",
      "이전 계정 또는 다른 팀의 데이터는 표시하지 않습니다.",
      true,
    ],
    ANALYTICS_NOT_READY: [
      "아직 분석 결과가 없습니다",
      "최초 정상 분석 전에는 점수와 성과를 표시하지 않습니다.",
      true,
    ],
    NETWORK_ERROR: [
      "연결을 확인해 주세요",
      "데이터를 가져오지 못했습니다. 연결 후 다시 시도해 주세요.",
      true,
    ],
  };
  const statuses: Record<number, [string, string, boolean]> = {
    401: [
      "로그인이 필요합니다",
      "인증이 만료되었거나 로그아웃되었습니다. 다시 로그인해 주세요.",
      false,
    ],
    403: [
      "이 화면을 볼 권한이 없습니다",
      "허용된 역할과 업무 범위를 관리자에게 확인해 주세요.",
      false,
    ],
    404: [
      "대상을 찾을 수 없습니다",
      "항목이 없거나 현재 허용 범위 밖에 있습니다.",
      false,
    ],
    409: [
      "최신 상태를 확인해 주세요",
      "다른 변경이 먼저 반영되었습니다. 새 상태를 불러와 주세요.",
      true,
    ],
    422: [
      "조회 조건을 확인해 주세요",
      "요청한 조건이 유효하지 않습니다. 조건을 수정해 주세요.",
      false,
    ],
    429: [
      "잠시 후 다시 시도해 주세요",
      "요청이 많아 조회가 제한되었습니다.",
      true,
    ],
    503: [
      "서비스 연결이 지연되고 있습니다",
      "확인되지 않은 값을 0건으로 표시하지 않습니다.",
      true,
    ],
  };
  const [title, message, retry] = values[error.code] ??
    statuses[error.status] ?? [
      "조회 중 오류가 발생했습니다",
      "잠시 후 다시 시도해 주세요.",
      true,
    ];
  return { title, message, retry };
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(0, "INVALID_RESPONSE");
  return value as Record<string, unknown>;
}
const text = (v: unknown): string => {
  if (typeof v !== "string" || !v.trim())
    throw new ApiError(0, "INVALID_RESPONSE");
  return v;
};
const number = (v: unknown): number => {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < 0)
    throw new ApiError(0, "INVALID_RESPONSE");
  return v;
};
const timestamp = (v: unknown): string => {
  const s = text(v);
  if (!/(Z|[+-]\d\d:\d\d)$/.test(s) || !Number.isFinite(Date.parse(s)))
    throw new ApiError(0, "INVALID_RESPONSE");
  return s;
};
export function parseSession(value: unknown): Session {
  const v = record(value);
  if (
    !["ADMIN", "AGENT", "ANALYST", "CUSTOMER"].includes(String(v.role)) ||
    typeof v.active !== "boolean" ||
    !Array.isArray(v.permissions) ||
    !Array.isArray(v.allowedTeamIds)
  )
    throw new ApiError(0, "INVALID_RESPONSE");
  if (
    !v.permissions.every((p) => typeof p === "string") ||
    !v.allowedTeamIds.every((t) => typeof t === "string" && t.trim())
  )
    throw new ApiError(0, "INVALID_RESPONSE");
  return {
    userId: text(v.userId),
    displayName: text(v.displayName),
    role: v.role as Session["role"],
    active: v.active,
    permissions: v.permissions.filter((p) =>
      permissions.includes(p as Permission),
    ) as Permission[],
    allowedTeamIds: v.allowedTeamIds as string[],
    scopeKey: text(v.scopeKey),
  };
}
export function parseOverview(value: unknown, session: Session): Overview {
  const v = record(value);
  if (v.userId !== session.userId || v.scopeKey !== session.scopeKey)
    throw new ApiError(403, "SCOPE_MISMATCH");
  const workload = record(v.workload),
    a = record(v.analytics);
  const counts = Object.fromEntries(
    workStates.map((s) => [s, number(workload[s])]),
  ) as Overview["workload"];
  if (
    !Array.isArray(v.previewTickets) ||
    !["synthetic", "live"].includes(String(v.source))
  )
    throw new ApiError(0, "INVALID_RESPONSE");
  const tickets = v.previewTickets.map((item) => {
    const t = record(item);
    if (t.state !== "REVIEW") throw new ApiError(0, "INVALID_RESPONSE");
    return {
      id: text(t.id),
      subject: text(t.subject),
      reason: text(t.reason),
      state: t.state as WorkState,
      firstResponseDueAt: timestamp(t.firstResponseDueAt),
    };
  });
  if (
    new Set(tickets.map((t) => t.id)).size !== tickets.length ||
    workStates.some(
      (s) => tickets.filter((t) => t.state === s).length > counts[s],
    )
  )
    throw new ApiError(0, "INVALID_RESPONSE");
  let analytics: Overview["analytics"];
  if (a.status === "not_ready") analytics = { status: "not_ready" };
  else if (a.status === "ready" || a.status === "stale") {
    const numerator = number(a.numerator),
      denominator = number(a.denominator);
    if (numerator > denominator) throw new ApiError(0, "INVALID_RESPONSE");
    analytics = {
      status: a.status,
      asOf: timestamp(a.asOf),
      periodLabel: text(a.periodLabel),
      numerator,
      denominator,
    };
  } else throw new ApiError(0, "INVALID_RESPONSE");
  const reviewOverdue = number(v.reviewOverdue);
  if (reviewOverdue > counts.REVIEW) throw new ApiError(0, "INVALID_RESPONSE");
  return {
    userId: session.userId,
    scopeKey: session.scopeKey,
    asOf: timestamp(v.asOf),
    source: v.source as Overview["source"],
    workload: counts,
    reviewOverdue,
    openFollowupTasks: number(v.openFollowupTasks),
    previewTickets: tickets,
    analytics,
  };
}
export type ApiClient = {
  getSession(signal: AbortSignal): Promise<Session>;
  getOverview(session: Session, signal: AbortSignal): Promise<Overview>;
};
function localPath(value: string | undefined) {
  if (!value || !/^\/api\/[a-zA-Z0-9/_-]+$/.test(value))
    throw new ApiError(0, "CONTRACT_NOT_CONFIGURED");
  return value;
}
export async function requestJson(
  path: string,
  signal: AbortSignal,
  transport: typeof fetch = fetch,
  options: { method?: "GET" | "POST"; body?: object } = {},
): Promise<unknown> {
  let response: Response;
  try {
    response = await transport(path, {
      signal,
      credentials: "same-origin",
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}),
      cache: "no-store",
      redirect: "error",
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(0, "NETWORK_ERROR");
  }
  if (!response.ok) {
    let code = "HTTP_ERROR",
      traceId: string | undefined;
    try {
      const body = record(await response.json());
      const e = record(body.error);
      if (typeof e.code === "string" && /^[A-Z0-9_]{1,80}$/.test(e.code))
        code = e.code;
      const requestId = e.request_id ?? e.trace_id;
      if (typeof requestId === "string" && /^[\w-]{1,80}$/.test(requestId))
        traceId = requestId;
    } catch {
      /* Server internals and HTML error bodies never enter the UI. */
    }
    throw new ApiError(response.status, code, traceId);
  }
  try {
    return await response.json();
  } catch {
    throw new ApiError(0, "INVALID_RESPONSE");
  }
}
export function createHttpClient(config: {
  sessionPath?: string;
  overviewPath?: string;
}, transport: typeof fetch = fetch): ApiClient {
  return {
    async getSession(signal) {
      return parseSession(
        await requestJson(localPath(config.sessionPath), signal, transport),
      );
    },
    async getOverview(session, signal) {
      return parseOverview(
        await requestJson(localPath(config.overviewPath), signal, transport),
        session,
      );
    },
  };
}
