# Frontend ↔ Backend A/B 인수 현황

기준: Backend A `origin/feature/backend-a`의 0.9.0 문서·스키마를 2026-11-04 로컬에서 확인. 이 문서는 화면 구현 경계이며 서버 배포 완료나 통합 검증을 뜻하지 않습니다.

## 지금 연결한 조회 계약

|화면|Backend A 요청|현재 UI 처리|
|---|---|---|
|문의 예외 큐|`GET /api/v1/staff/exception-queue`|ROUTED/UNROUTED, reason, cursor, total/as_of. 큐 노출과 상세 권한 분리|
|문의 내부 근거|`POST /api/v1/staff/tickets/{id}/internal`|purpose_code=ACTIVE_SUPPORT. 표시용 근거만 사용, 실행 승인 없음|
|고객 360|`POST /api/v1/staff/customers/{id}/360`|purpose_code=ACTIVE_SUPPORT. 허용된 이력, NOT_GENERATED 정형 사실|
|후속 업무|`GET /api/v1/staff/followups`|status/cursor. needs_handover 및 후속 revision 표시|
|VOC|`GET /api/v1/admin/analytics/voc/top`, `/voc/unavailable`, `/products/{id}`|batch_id 고정, score null·stale·합성 출처 표시|
|VOC 조치|`GET /api/v1/staff/voc-improvements`|계획 revision, 비교 범위 제한, 효과 UNAVAILABLE 표시|
|AI 품질|`GET /api/v1/staff/quality/samples`, `POST /samples/{id}/material`|표본 목록과 지정 평가 자료. purpose_code=QUALITY_REVIEW|
|자동화|`GET /api/v1/staff/automation-control`|paused·revision·generation·변경 시각 조회만|

Backend A의 오류는 `{error:{code,request_id}}`입니다. 공통 client는 `request_id`와 기존 `trace_id`를 안전한 길이·문자 형식에서만 추적 ID로 표시하고 서버 원문 `message`는 출력하지 않습니다.

## 팀 합의가 필요한 연결 조건

1. **인증과 세션:** Backend A `POST /auth/login`은 Bearer JWT를 반환하고 `GET /auth/me`는 user_id/login_name/role만 반환합니다. 기존 프런트엔드 `Session`의 permissions/allowedTeamIds/scopeKey를 채울 현재 권한·팀 범위 계약이 필요합니다. `GET /staff/capabilities`는 일부 명시 권한만 제공하며 팀 목록·scope 버전을 제공하지 않습니다. 프런트엔드가 팀 범위를 추측하지 않습니다.
2. **브라우저 연결:** 현재 HTTP adapter는 동일 출처 쿠키/BFF 제안입니다. Azure Backend A의 Bearer 방식과 CORS 빈 목록에 바로 연결되지 않습니다. 팀은 BFF/프록시 또는 메모리 토큰 전달 방식을 선택하고 허용 origin을 확정해야 합니다. 서비스 키와 reader/publisher 토큰은 브라우저로 전달하지 않습니다.
3. **운영 홈:** `Overview`는 1주차 제안 DTO입니다. Backend A의 `/staff/workload`는 다른 단위·스키마이고 통합 운영 홈 API가 아닙니다. 자동 안내율의 분모와 as_of를 혼합하지 않고 별도 adapter를 합의합니다.
4. **고객 답변·인수:** Backend A/B와 실제 인수, 제안 검토, 승인, 발송의 상태 전이·권한·revision·멱등키를 확정한 뒤 UI 명령을 연결합니다. 큐의 `AUTO_FAILED`를 이미 사람에게 배정된 것으로 표시하지 않습니다.
5. **P2/L3:** 다중 테넌트, 실제 판매 채널 연동, 결정 실행·되돌리기는 현재 화면의 실행 기능이 아닙니다. 테넌트 경계·외부 효과·감사·이의 신청 정책과 API 계약이 정해지면 별도 연결합니다.

## 검증 기준

- 합성 fixture는 실제 Backend A의 UUID·scope·점수 산식 검증을 대신하지 않습니다. 특히 운영 홈의 `T-2401`과 같은 표시용 ID는 실서버의 UUID가 아닙니다.
- 응답의 null/UNAVAILABLE/LOW_SAMPLE을 0으로 바꾸지 않습니다. VOC 점수는 관리 우선순위이며 결함 확정이 아닙니다. 효과 분석은 현재 `EFFECT_INTEGRATION_NOT_IMPLEMENTED`입니다.
- `/quality`는 수동 표본입니다. 실제 전체 AI 정답률을 의미하지 않습니다. 마스킹된 평가 자료도 PII 제거 보장이 아닙니다.
- 실제 연동 검증에는 최소한 ADMIN/제한 팀/무권한, 401·403·404·409·422·429·503, 배치 교체, 권한 중간 변경, 2페이지 cursor, 후속 인수 필요 사례를 포함합니다.
