# React JWT / P1 API 통신 기반

기준 `02242912ea7545a511296dc73531d4045afd8784`, feature/backend-plus.

## 현재 구현 범위

기존 P0 합성 화면·운영 홈 KPI·원래 메뉴/레이아웃을 유지하고 JWT/P1 통신을 별도로 추가했다. 운영 모니터링·VOC·정책 본 화면은 구현하지 않았으며 권한 검사된 준비 화면만 제공한다. FastAPI 코드/마이그레이션/OpenAPI, package manifests/lockfile, 기존 Dashboard/Workspaces/fixtures/useResource 및 기존 테스트는 변경하지 않았다.

- 기본 VITE_DATA_MODE=mock: 기존 P0 합성 화면을 그대로 사용한다. 추가 `P1 API 로그인` 진입은 실제 인증용 `/p1` 경로이며 mock 프로필로 서버 권한을 만들지 않는다.
- VITE_DATA_MODE=http: 기존 화면에도 실제 인증 게이트를 적용한다. 기존 Overview DTO의 실제 서버 API는 아직 없으므로 VITE_OVERVIEW_PATH가 비어 있으면 기존 CONTRACT_NOT_CONFIGURED 안내를 유지한다. P1 toolbar는 운영 홈 조회 실패와 독립적으로 이용 가능하다. 값을 임의로 /staff/workload로 지정해 KPI를 바꾸지 않는다.
- `/p1` 연결 상태, `/p1/monitoring/*`, `/p1/voc/*`, `/p1/policies/*`, `/p1/policy-comparisons/*` 준비 경로가 있다. READ capability에 따라 메뉴와 직접 URL을 모두 검사한다. 실제 기능 데이터/쓰기 UI는 다음 단계다.

## 인증·세션 흐름

로그인 폼 → POST `/api/v1/auth/login` JSON `{login_name,password}` → access_token/token_type/expires_in 검증 → 메모리 보관 → GET `/api/v1/admin/p1/session` Bearer → 활성 ADMIN·UUID user/team·capabilities 응답 검증 → 허용 메뉴와 범위 표시.

토큰/비밀번호를 localStorage/sessionStorage/URL/로그/화면에 저장·표시하지 않는다. 폼 제출 시 비밀번호 입력 상태를 지운다. JWT는 서버 세션으로 검증하고 브라우저의 role 선택값이나 JWT decode로 권한을 만들지 않는다. 새로고침하면 메모리 인증은 사라진다. 로그아웃은 클라이언트 메모리/요청/보호 화면만 제거하며 서버 토큰 폐기 API를 호출하지 않는다. refresh-token API는 없고 `expires_in` 종료 시 재로그인을 요구한다.

401은 즉시 토큰·session·진행 요청을 제거한다. 이후 연결 화면은 재로그인을 요구한다. 오래된 로그인/응답/401이 새 로그인 상태를 지우지 못하도록 token generation·epoch와 AbortController를 함께 검사한다. fetch가 AbortSignal을 무시하거나 JSON body가 늦게 도착해도 이전 결과를 반환하지 않는다.

수동 재조회·창 focus/탭 복귀 및 가시 탭의60초 간격 세션 재조회로 capability/팀 변경을 확인한다. 재조회 시작부터 이전 보호 하위 트리를 제거하고 유효한 새 세션에서만 다시 렌더한다. 실패·범위 거부·비활성화는 이전 데이터를 유지하지 않는다. 새 capability를 포함하는 cache key와 기존 useResource의 즉시 scope 제거/늦은 응답 차단을 재사용한다. 사용자·권한 변경이 push로 전달되는 기능은 없으므로 서버는 매 요청 권한을 계속 확인한다.

세션403/503 때는 보호 데이터 없이 blocked 상태로 두고 수동 재조회/다른 계정 로그인을 제공한다. P1_DISABLED/VOC_DISABLED/POLICY_DISABLED는 기능 비활성 안내로 분리한다. 기능 플래그 조회 API는 없으며 준비 화면은 기능별 data API를 자동 호출하지 않는다. 메뉴의 capability 노출이 해당 기능 flag=true라는 뜻은 아니다.

P1_SESSION.capabilities를 별도 보존하고 READ 권한으로 준비 메뉴/직접 경로를 검사한다. 기존 permissions와 동일한 이름의 명시 capability만 기존 읽기 메뉴에 전달한다. ADMIN만으로 INQUIRY_READ/FOLLOWUP_READ/QUALITY 권한을 임의 부여하지 않는다. 이후 기능별 생성·검토 버튼에는 WRITE/GENERATE/REVIEW를 각각 추가 검사해야 한다.

## P1 클라이언트

`createP1Client(auth)`의 get(path,signal), post(path,body,idempotencyKey,signal)를 제공한다. 반환값은 `{data:unknown,status,requestId?,idempotencyReplayed}`다. 기능별 DTO runtime parser는 각 본 화면 구현 단계에서 붙인다.

- 로컬 `/api/v1/admin/p1/` 경로만 허용하며 URL 정규화 후 namespace 탈출·외부 URL·backslash·fragment를 거부한다. 토큰 전달 transport는 로컬 `/api/v1/`만 허용한다.
- Bearer, JSON body, AbortSignal, no-store, redirect:error, credentials:omit를 처리한다.
- POST는 유효한 Idempotency-Key(8–128, 영문/숫자/._:-)를 필수로 받는다. 클라이언트가 키를 자동 재생성하거나 실패한 POST를 자동 재시도하지 않는다. 같은 사용자 의도의 재시도는 같은 key/body를 사용하고, 사용자 수정은 새 의도로 처리한다.
- error.code와 body request_id/호환 trace_id, X-Request-ID를 안전한 형식으로 정규화한다. 원시 서버 message·HTML·인증정보는 사용자에게 반영하지 않는다. 200 malformed JSON은 INVALID_RESPONSE다.
- caller abort는 전파하며 세션 교체 후 성공 결과도 폐기한다. 요청 취소가 서버의 이미 커밋된 쓰기까지 rollback한다는 의미는 아니다. 향후 기능 UI에서는 결과가 불명확한 쓰기를 같은 멱등키로 확인하고 상세/이력을 조회해야 한다.
- 기존 P0 adapter에는 인증 fetch만 주입하고 기존 DTO 계산/응답 검증을 유지한다. API 오류 시 mock으로 전환하지 않는다.

## 로컬 실행

1. 기존 Backend A 문서에 따라 별도 로컬 PostgreSQL에서 head0010을 준비한다. 실제 `.env`/키는 Git에 넣지 않는다.
2. 서버 P1_ENABLED=true, 활성 ADMIN의 SQL 팀 grant와 필요한 명시 capability를 준비한다. 이 작업은 권한을 자동 부여하는 기능을 추가하지 않았다.
3. Backend A를127.0.0.1:8000에서 실행한다.
4. frontend/에서 npm ci, npm run dev를 실행하고 `#/p1`로 이동한다. 기본 Mock P0 화면의 `P1 API 로그인`으로도 진입 가능하다.
5. Vite `/api` proxy는 기본 http://127.0.0.1:8000이다. 다른 로컬 포트는 VITE_API_PROXY_TARGET로 지정한다. loopback HTTP(S) origin만 허용하고 credentials/query/path는 금지한다. 이 값은 공개 URL이며 비밀값이 아니다. 기존 Vitest 설정은 유지했다.

프로덕션 reverse proxy/origin/CORS 구성은 별도다. 실제 공개 Azure API로 연결된 배포를 검증한 결과가 아니다.

## 현재 백엔드에 없는 프론트 참조 API

frontend/src/operations.ts에 기존 팀원 코드로 남아 있으며 대체하거나 삭제하지 않았다.

| 실제 참조 | 현재 backend-plus OpenAPI | 영향 |
|---|---|---|
| GET /api/v1/staff/voc-improvements | 없음 | 기존 제품 화면의 VOC 조치 조회는 HTTP 연결 미완료 |
| GET /api/v1/staff/quality/samples | 없음 | 품질 표본 목록 HTTP 연결 미완료 |
| POST /api/v1/staff/quality/samples/{id}/material | 없음 | 품질 자료 HTTP 연결 미완료 |
| 기존 React Overview DTO용 endpoint | 합의된 대응 API 없음 | P0 HTTP 운영 홈 adapter는 별도 계약 필요 |

기존 `/api/v1/admin/p1/voc-proposals`는 위 VOC 조치 API와 다른 기능이다. 임의 치환하지 않는다. 전체 제품·팀 이름 카탈로그 및 정책 source 문서 검색도 현재 API가 있다고 가정하지 않는다. UUID와 확인된 실제 응답만 사용한다.

## 검증/한계

[검증 보고서](p1-auth-verification.md)를 참조한다. 실제 frontend AuthManager/P1 client 코드를 Vite proxy→로컬 Uvicorn→격리 PostgreSQL에 연결해 로그인·세션·명시 팀/capability·요청 ID와 잘못된 로그인401을 검증했다. 이는 실제 브라우저 E2E나 실제 Azure OpenAI/Fabric/RAG/Search/Backend B 연결 검증이 아니다. 쓰기 화면·운영 모니터링/VOC/정책 본 화면은 이번 범위가 아니다.
