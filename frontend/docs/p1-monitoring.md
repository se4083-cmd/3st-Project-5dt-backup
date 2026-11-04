# P1 운영 모니터링 React 구현·검증

2026-11-04 · 작업 브랜치 `feature/backend-plus` · 기준 HEAD `0a40cf39b167f53917693d67515490535c76f0fb`.
이 기록은 해당 HEAD 위의 미커밋 변경을 검증한 결과다. 커밋·push·Azure 배포는 수행하지 않았다.

## 화면과 인증

`#/p1/monitoring`은 기존 AppShell·좌측 메뉴·모바일 하단 탐색·P1 상단 메뉴를 유지한다. 기존 운영 홈·P0 KPI 계산·기존 API adapter는 변경하지 않았다. 운영 홈 기본 모드는 계속 Mock이며, P1 모니터링은 Mock 모드에서도 실제 로그인과 HTTP API를 사용한다. API 오류를 합성 데이터로 대체하지 않는다.

기존 메모리 JWT AuthManager, P1 client, AbortSignal, 401 보호 데이터 제거, capability guard를 재사용한다. `P1_MONITOR_READ`가 없으면 메뉴와 직접 URL 접근을 차단하고 모니터링 API를 호출하지 않는다. 서버는 매 요청에서 권한·팀을 다시 확인한다. 별도 기능 플래그 조회 API는 없으므로 메뉴 표시만으로 서버 활성 상태를 추측하지 않는다. 세션 또는 개별 조회의 `503 P1_DISABLED`를 기능 비활성 안내로 표시한다.

기존 세션 재확인(포커스 복귀·가시 상태에서 60초마다·수동 재확인)은 보호 화면을 해제하고 새 세션으로 다시 마운트한다. 이에 따라 필터와 페이지도 초기화된다. 새 계정·팀·권한에 이전 데이터나 진행 중인 응답이 남지 않는다. 페이지의 전체 새로고침도 커서를 초기화한다.

## 실제 API 계약

모든 경로는 `/api/v1/admin/p1/monitoring` 아래이며 Bearer JWT와 `P1_MONITOR_READ`가 필요하다. GET 조회만 구현했으므로 쓰기·멱등키·자동화 제어 변경은 없다.

| 요청 | 전송하는 필터 | 화면 반영 |
|---|---|---|
| `GET /summary` | 선택한 `team_ids`, `job_kind` | 현재 작업 지표, 이전 이력 포함 원본 상태별 집계, 자동화 제어 조회 가능 상태, 분석 배치 최신성 |
| `GET /jobs` | 선택한 `team_ids`, `job_kind`, `status`, `limit`, `cursor` | 작업 이력, 현재/이전 회차·버전, 합성 출처, 안전한 오류 코드, 서버 시각 |
| `GET /ai-calls` | 선택한 `team_ids` | 서버 기본 최근 24시간 관측 기간, 미관측 구성요소 |

팀 선택은 모든 허용 팀 또는 단일 허용 팀이다. 모든 허용 팀을 선택하면 `team_ids`를 생략한다. 팀 이름 API가 없으므로 세션의 실제 UUID로 표시한다. 작업 종류는 AUTO/HANDOFF이며 집계·목록에만, 상태는 PENDING/RUNNING/RETRY/SUCCEEDED/FAILED/HANDED_OFF/CANCELLED이며 목록에만 적용한다. 페이지 크기는 20/50/100이다. 커서는 해석하지 않고 URL 인코딩하여 전달한다. 서버가 전체 건수를 제공하지 않으므로 전체 페이지 수나 전체 작업 수를 만들지 않는다.

응답 parser는 표시할 필드의 타입·숫자·timezone 시각, 선택 팀과 응답 팀의 일치, 작업 종류·상태 조건, 페이지 크기·중복 ID·커서를 검증한다. AVAILABLE 분석 데이터의 팀 범위도 검사한다. 잘못된 응답은 INVALID_RESPONSE로 처리하고 요청 ID를 유지하며 수치를 표시하지 않는다. 필터가 바뀌면 이전 요청을 중단하고 이전 응답을 폐기한다.

## 상태와 지표 의미

| 서버 응답 | 화면 |
|---|---|
| 유효한 작업 집계 `0`, 빈 `items` | 0건. 빈 목록은 정상 조회라고 명시 |
| `generation_mismatch: null` | 미확인. 0으로 치환하지 않음 |
| 자동화 `UNAVAILABLE / PERMISSION_REQUIRED` | 제어 조회 권한 필요. 일시 정지로 추측하지 않음 |
| AI `UNOBSERVED`, 건수·에러율 `null` | 미관측. 0건/0% 또는 정상 호출로 표시하지 않음 |
| 분석 `NO_PUBLISHED_BATCH` | 미게시, 최신성 판단 불가 |
| 분석 `SCOPE_NOT_PROVIDED` | 선택 팀 데이터 없음, 최신성 판단 불가 |
| 분석 AVAILABLE, `meta.stale: true` | 오래된 데이터와 서버가 제공한 원천·생성·게시·기간 종료 시각 |
| 분석 AVAILABLE, `meta.stale: false` | 서버 최신성 기준 충족. 브라우저에서 임의 임계값을 적용하지 않음 |
| `LOCAL_SYNTHETIC` | 합성 분석 데이터 |
| `FABRIC` | 서비스 선언 출처. 실제 연결 미관측·별도 검증 안 됨을 명시 |
| 서버 오류·네트워크 오류·형식 오류 | 해당 조회의 오류와 추적 ID. 실패를 0건으로 대체하지 않음 |
| `P1_DISABLED` | 기능 비활성. 일반 네트워크 재시도와 구분 |
| 401 | 토큰·보호 화면 제거, 재로그인 |

집계 단위는 문의 수가 아닌 작업 수다. 현재 작업은 문의의 cycle/version과 일치하는 작업이다. 실행 가능 대기는 시각·세대·정지 조건을 반영하되 실제 worker 실행 보장은 아니다. 원본 상태 집계에는 이전 이력이 포함된다. 임대 만료·세대 불일치 등은 중복될 수 있으므로 합산하지 않는다. 미배정·허용되지 않은 팀은 서버에서 제외한다. `NO_TASK_PRODUCER`는 백그라운드 작업 집계 불가로 설명하며 VOC·정책 API 전체가 없다는 뜻으로 표시하지 않는다.

세 API는 독립 조회이며 시각·요청 ID도 각각 표시한다. 작업 종류·상태 변경이 모든 지표에 적용되는 것처럼 표시하지 않는다. 목록 페이지 간 변경이 발생할 수 있어 고정 스냅샷이라고 주장하지 않는다.

## 변경 파일

- `src/features/monitoring/MonitoringPage.tsx`: 화면·필터·페이지·각 상태와 부분 오류 표시.
- `src/features/monitoring/api.ts`: 기존 P1 transport를 사용하는 세 조회와 DTO 검증 연결.
- `src/features/monitoring/contracts.ts`: 현재 FastAPI 응답의 runtime parser.
- `src/features/monitoring/monitoring.css`: 해당 화면에 한정한 반응형 스타일.
- `src/features/p1/Foundation.tsx`: 모니터링 준비 route를 실제 화면으로 연결. VOC·정책 준비 route 유지.
- `src/test/monitoring-{contracts.test.ts,ui.test.tsx,fixtures.ts}`: 새 계약·화면·합성 fixture.
- `src/test/auth-ui.test.tsx`: 준비 화면 검사의 대상을 아직 준비 상태인 VOC로 이동. 기존 검사를 삭제하거나 완화하지 않음.
- `README.md`, `docs/p1-monitoring.md`: 현재 화면과 실제 검증 기록.

## 실행한 검증

| 검증 | 결과 |
|---|---|
| `frontend/`에서 `npm test` | **73 passed** (기존 52 + 신규 21), 8 파일 |
| `npm run build` | TypeScript·Vite 성공 |
| `python -m scripts.check_p0_contract` | **37 P0 paths / 41 operations**, 원래 schema/security 유지 |
| `python -m scripts.check_handoff_contract` | 실제 OpenAPI·역할·public DTO·canonical hash 계약 PASS |
| SQLite 모니터링 + 기존 P1 OpenAPI 보존 검사 | **17 passed / 1 skipped**. 건너뛴 검사는 PostgreSQL 전용 동시성 검사 |
| 같은 검사의 `--database=postgres` 실행 | **18 passed**, repeatable-read 동시 변경 검사 포함 |
| 격리 PostgreSQL `alembic upgrade head`, `alembic check` | head0010 적용, 새 upgrade 연산 없음. 신규 마이그레이션·백엔드 변경 없음 |
| 실제 HTTP 로그인·세션·summary·jobs·ai-calls | **모두 200**, 기존 AuthManager와 새 MonitoringClient → 실제 Vite proxy → Uvicorn → PostgreSQL |
| Chromium headless 실제 React 화면 | 1440×1000, 390×844에서 화면·필터·페이지·빈 상태·복구 확인, 페이지 가로 넘침 없음, uncaught JS 오류 0 |

신규 React 검사는 0/null/미관측/미게시/오래된 데이터/조회 실패 분리, 잘못된 응답·다른 팀·필터 불일치 차단, endpoint별 필터 전달, opaque 커서, 페이지 초기화, capability/기능 플래그/401, 이전 요청 abort·늦은 응답 폐기, 세션 권한 철회 후 데이터 제거를 포함한다. 기존 P0 React 검사도 전부 실행했다.

SQLite 첫 시도는 제한 실행 환경의 TestClient 로컬 소켓 대기로 중단했고, 로컬 소켓을 허용한 환경에서 같은 검사를 재실행하여 위 결과를 확인했다. 기존 Starlette/httpx deprecation 경고 1건은 그대로다. 이번 프론트엔드 변경에서 전체 백엔드 530개 검사를 재실행한 결과로 주장하지 않는다.

실제 HTTP 검증 DB에는 합성 작업 26개를 넣었다. 허용된 작업 25개만 20+5개로 중복 없이 조회됐고, 다른 팀 작업 1개는 제외됐다. 선택 팀·AUTO·FAILED 필터는 3개, 실행 가능 대기는 22개, 빈 허용 팀은 0개, 미허용 팀은 403이었다. 이 숫자는 검증 fixture 결과이며 화면 상수가 아니다. 실제 AI 응답은 null/UNOBSERVED였고, 게시된 합성 분석 배치의 오래된 상태를 확인했다.

브라우저의 일반 조회·필터·페이지·빈 결과는 실제 로컬 HTTP/DB 응답을 사용했다. **500 오류와 503 P1_DISABLED 화면은 CDP 응답 Mock 주입으로 검사했다.** 이를 실제 서버 장애나 실제 기능 플래그 변경 검증으로 표시하지 않는다. Mock 해제 후 실제 조회 복구도 확인했다. 브라우저 localStorage/sessionStorage는 비어 있었다.

일회 검증 결과는 `/tmp/csflow-monitoring-http.json`, 화면 캡처는 `/tmp/csflow-monitoring-{desktop,mobile,disabled-mock}.png`에 보관했다. 실행 프로세스·테스트 전용 스키마를 정리하고 로컬 PostgreSQL을 종료했다. 비밀번호·JWT·DB URL은 결과 문서와 Git 변경에 포함하지 않았다.

## 남은 연결 범위

AI 호출 telemetry 생산자, 실제 Azure OpenAI/Fabric/Search/RAG/Backend B 연결, P1 백그라운드 작업 생산자는 검증하지 않았다. 현재 API가 미관측으로 명시하는 값을 추측하지 않는다. VOC·정책 본 화면과 운영 자동 적용 기능은 이번에 구현하지 않았다. 팀 이름·다중 팀 조합 선택 UI는 별도 계약/후속 범위다.

기존 P0 Overview 대응 계약 및 `/api/v1/staff/voc-improvements`, `/api/v1/staff/quality/samples`, `/api/v1/staff/quality/samples/{id}/material`의 미연결 상태는 그대로다. [인증·통신 기반 문서](p1-auth-foundation.md)의 목록을 참조하며 다른 API로 치환하지 않았다. 실제 Azure 배포·운영 고객 데이터·모든 브라우저/해상도 검증은 수행하지 않았다.
