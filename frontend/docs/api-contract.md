# 1주차 화면 데이터 계약 · 합의용 초안

**확정된 백엔드 API 명세가 아닙니다.** `Session`, `Overview`는 1주차 화면과 개발 응답 사이의 TypeScript 계약입니다. 실제 연결 전 Backend A/B가 필드·권한·경로를 합의하고 adapter를 맞춥니다.

기존 구현은 데이터 파이프라인의 분석 조회 API이며 관리자 인증·현재 티켓 원장 API를 대신하지 않습니다. 그 서비스의 reader/publisher 토큰을 프런트엔드로 전달하지 않습니다.

## 기존 기획과 구분

- v4.1 명시: `POST /api/auth/login` → `{access_token, expires_in}`. 실제 로그인 연결과 토큰 보관·갱신 정책은 이번 구현에 포함하지 않았습니다.
- v4.1 명시: `GET /api/agent/tickets?state=ESCALATED`, 문의 상세, A/B의 담당 인수·초안·승인·발송.
- **미확정:** 현재 사용자/권한 조회, 운영 홈 통합 조회, 필터와 카운트 DTO, Manager 배정 자격.
- HTTP adapter는 동일 출처 세션/BFF 방식의 제안이며 JWT 전달 방식과 동일하다고 간주하지 않습니다. 실연동 결정 전 `.env.local` 경로는 비워둡니다.

## 인증 정보 최소 필드

```json
{
  "userId": "demo-manager-1",
  "displayName": "운영 관리자",
  "role": "ADMIN",
  "active": true,
  "permissions": ["OPERATIONS_READ", "INQUIRY_READ", "FOLLOWUP_READ", "PRODUCT_READ", "AUTOMATION_MANAGE"],
  "allowedTeamIds": ["DELIVERY", "RETURN_REFUND", "PRODUCT_PAYMENT", "ACCOUNT_EXCEPTION"],
  "scopeKey": "ALL4"
}
```

권한 이름은 이번 화면 경계를 표현하기 위한 제안입니다. 기존 시스템에 이미 존재하는 권한 문자열이라는 뜻이 아닙니다. 범위가 바뀌면 `scopeKey`도 바뀌어야 하며, 프런트엔드에서 query나 역할 선택기로 허용 팀을 확장하지 않습니다. 서버는 매 요청 재검증하고 403/404를 반환해야 합니다.

Manager 화면 진입은 활성 ADMIN + `OPERATIONS_READ` + 비어 있지 않은 허용 팀을 요구합니다. 개별 메뉴는 해당 기능 권한을 추가 검사합니다. AGENT/ANALYST/CUSTOMER 계정은 현재 Manager 앱에 자동 승격하지 않습니다. 추후 분석가 전용 화면은 별도 요구사항입니다.

## 운영 홈 응답 최소 필드

```json
{
  "userId": "demo-manager-1",
  "scopeKey": "ALL4",
  "asOf": "2026-11-02T01:00:00Z",
  "source": "synthetic",
  "workload": {"REVIEW": 4, "WORKING": 3, "FOLLOWUP_PENDING": 5, "AI_RUNNING": 2},
  "reviewOverdue": 2,
  "openFollowupTasks": 6,
  "previewTickets": [
    {"id":"T-2401","subject":"상품 파손 확인","reason":"사람 연결 요청","state":"REVIEW","firstResponseDueAt":"2026-11-02T00:40:00Z"}
  ],
  "analytics": {
    "status": "ready",
    "asOf": "2026-10-31T03:00:00Z",
    "periodLabel": "최근 7일 · 독립 합성 예시",
    "numerator": 94,
    "denominator": 120
  }
}
```

`analytics`는 `{ "status": "not_ready" }`도 허용합니다. 이전 정상 배치 유지 시 `status=stale`와 **원래 배치 시각**을 함께 보냅니다. 조회 실패를 `not_ready`, 빈 배열 또는 0으로 대체하지 않습니다. 새로운 권한 범위에 이전 범위의 분석을 재사용하지 않습니다.

`previewTickets`는 일부 미리보기이므로 그 길이로 전체 카운트를 만들지 않습니다. 위 축약 JSON은 1개 미리보기이고 실제 fixture에는 4개가 있습니다. 서버의 정렬 순서를 유지합니다. 원문 대화·전화·고객명·내부 메모를 홈 응답에 넣지 않습니다.

## 카운트 정의 제안

공통 단위는 같은 기준 시각에서 **현재 회차만 보는 고유 문의 수**입니다. 이전 회차와 완료 문의는 제외합니다. 아래 화면 상태는 기존 DB 상태 enum 자체가 아니라 서버가 원장·배정·자동화 상태를 확인해 제공할 표시용 분류입니다.

|값|화면 의미|주의|
|---|---|---|
|REVIEW|허용 팀에서 관리자 검토가 필요한 대기 문의|완료된 자동 안내 제외. 담당·사람 경로 조건은 A/B와 확정|
|WORKING|현재 로그인 관리자가 처리 중인 문의|다른 담당자의 처리 중 문의를 내 업무로 포함하지 않음|
|FOLLOWUP_PENDING|현재 업무 범위에서 필수 후속 확인을 기다리는 문의|후속 업무 행 수와 다름. 현재 회차 상태 기준|
|AI_RUNNING|현재 업무 범위에서 실제 자동 안내 작업이 진행 중인 문의|최근 자동 완료 회차 수와 다름|
|reviewOverdue|REVIEW 중 첫 응답이 없고 `asOf > dueAt`인 문의|기한과 같은 시각은 초과 아님. 배정해도 기한 초기화 금지|
|openFollowupTasks|허용 업무 범위의 미완료 후속 업무 수|티켓·제품 업무 단위. FOLLOWUP_PENDING과 합산하지 않음|

네 카드의 합계는 **이 화면의 현재 업무 집합 합계**입니다. 전체 회사/스토어의 모든 미해결 문의 수라고 주장하지 않습니다. 다중 담당자·미분류·대기 중 작업·보류 문의를 어디에 포함할지와 중복 우선순위는 Backend A/B가 구현 전에 확정해야 합니다. 분류되지 않은 문의를 임의로 버리고 전체 집계라고 표시하지 않습니다.

1주차 fixture는 위 네 상태에 분명히 속하는 4+3+5+2=14건의 독립 예시입니다. 후속 업무는 6개로 두어 문의 수 5건과 혼동하지 않도록 했습니다. 과거 정적 시연의 5개 후속을 변경한 원장이 아니라 별도 개발 fixture입니다.

## 오류 및 응답 검증

기획의 오류 형태는 `{error:{code,message,trace_id}}`입니다. UI는 HTTP 상태와 정해진 코드로 안내 문구를 선택하며 서버 원문 오류를 그대로 출력하지 않습니다.

|상태|공통 UI 동작|
|---|---|
|401|현재 응답을 제거하고 재인증 안내. 개발 모드에만 시연 복구 버튼|
|403|보호 데이터 제거·권한 없음. 다른 팀 데이터를 대신 표시하지 않음|
|404|미존재와 범위 밖을 같은 메시지로 표시|
|409|이전 값을 성공으로 표시하지 않고 새 상태 조회|
|422|조회 조건 수정 안내|
|429|자동 무한 재시도 없이 대기 안내·수동 재시도|
|503 / 통신 실패|0건으로 대체하지 않고 오류 안내·수동 재시도|

응답 검증은 사용자·scope 일치, 필수 필드, 음수/정수 카운트, 중복 문의 ID, 시간대 없는 시각 거부, 분자≤분모를 검사합니다. 성과 분모 0은 `—`입니다. 같은 범위의 이전 정상 분석 보관 여부는 서버의 명시적 `stale` 응답을 따릅니다.

읽기 요청은 GET·no-store·동일 출처 세션만 사용합니다. 응답에 문제가 있으면 mock으로 조용히 전환하지 않습니다. 쓰기용 멱등성·버전·회차·CSRF는 2주차 실제 쓰기 계약에서 추가해야 합니다.
