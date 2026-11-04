# Scope・Gold 수신/검증/게시 — 구현 확인과 미합의

## 팀과 scope

**구현 확인:** team_id는 teams.team_id UUID다. tickets.team_id는 현재 운영 귀속이고 NULL을 허용한다. assignments에는 회차별 배정 team_id, queue_routes에는 회차별 명시 route team_id가 있다. users.team_id는 상담사의 소속이며 user_team_scopes(user_id,team_id)가 실제 직원 조회 허용 집합이다. users.allowed_team_ids JSONB는 원 fixture/seed 메타데이터이고, JSON 배열만 편집해 권한을 얻는 구조가 아니다. API CurrentUser에는 user_id/login_name/role만 있고 allowed_team_ids 필드는 없다. team_categories가 상담사의 실제 업무 category scope를 제한한다.

**구현 확인:** 분석 조회는 ADMIN만 가능하며 DB에서 활성 team과 user_team_scopes를 join한 **현재 전체 허용 집합**이 기본 scope다. 반복 query `?team_ids=<uuid>&team_ids=<uuid>`로 허용 부분집합을 선택한다. empty/무권한은403 ANALYTICS_TEAM_SCOPE_DENIED, 중복은422 DUPLICATE_TEAM_FILTER다. 배치에 대한 과거 권한을 고정하지 않고 pinned 과거 batch도 현재 권한을 검사한다.

**구현 확인:** scope_key는 제출 manifest의 팀 집합 label이다. API에 scope_key를 입력해 권한을 고르는 기능은 없으며 모르는 query가 와도 권한 근거로 쓰지 않는다. UUID를 문자열 표준형으로 변환하고 set 비교, manifest는 canonical 과정에서 정렬한다. 서로 다른 key로 같은 팀 집합을 중복 제출하는 것도 SCOPE_SET_DUPLICATE다. 조회는 selected team set과 manifest.scopes.team_ids가 **정확히 같은 scope 하나**를 사용한다. 대응 집계가 없으면200 UNAVAILABLE/SCOPE_NOT_PROVIDED이지 ALL4 fallback이 아니다. team_id 문자열 이름/category로 팀 UUID를 추정하지 않는다.

**구현 확인:** 원 합성 fixture의 4팀 매핑은 다음과 같다. 이는 `scripts/prepare_analytics_fixture.py` 어댑터의 고정 매핑이며 **현재 배포 DB의 팀 inventory라는 뜻이 아니다.** minimal seed 예시 T1은 다른 UUID를 사용하므로 같은 T1 label만으로 두 데이터를 join하지 않는다.

| fixture label | 정확한 UUID |
|---|---|
| T1 | 863e9dc3-6c9f-5e86-b3b7-f639a91dbdd2 |
| T2 | 4a10ff03-d933-58aa-bfa2-e6c736275b70 |
| T3 | 6efbae37-4e53-59e9-b68c-9711bef485b1 |
| T4 | 6f797bdd-ec8f-5973-bb70-03d5a284d300 |

15개 조합은 T1/T2/T3/T4, T1+T2/T1+T3/T1+T4/T2+T3/T2+T4/T3+T4, T1+T2+T3/T1+T2+T4/T1+T3+T4/T2+T3+T4, ALL4다. [기계 판독 정확한 집합](samples/fixture-scope-map.json)을 제공한다. 일반 manifest는1–8팀/1–255scope를 지원하며 모든 조합 제출을 강제하지는 않는다. risk는 제출된 scope×product 전체를 요구하고, 미제공 팀 조합은 조회 unavailable이다.

**구현 확인:** TOP10은 선택된 scope에서 **Fabric이 계산해 제출한 rank≤10**이다. 전체 TOP10에서 특정 팀 행만 숨기면 해당 팀의 모집단·중복·분모/정규화·순위가 달라 정확한 팀 TOP10이 되지 않는다. 팀 점수/순위 합산도 하지 않는다. 같은 scope가 제품 상세·components·metrics·일별 trend에도 적용된다. 운영 티켓/고객360으로 이동할 때는 해당 운영 API의 권한을 다시 검사한다.

## 팀 재배정의 집계 귀속

**구현 확인:** 현재 tickets.team_id는 변경될 수 있고 재문의 때 NULL로 초기화된다. assignments는 ended_at/assigned_at/cycle_no를 보존하지만 같은 회차의 queue_routes는 revision을 올려 덮어쓰므로 모든 route 이력 테이블이 아니다. audit에는 team-before/after 전체 payload나 변경마다 ticket_version을 보장하는 구조가 없다. 팀 귀속은 category 추정으로 보완할 수 없다.

**구현 확인:** 합성 fixture adapter는 기존 계산 결과를 복사하고, fixture의 운영 KPI는 마지막 배정/상태 기반 근사다. 원장으로 최초 팀/사건시점 팀/해결 팀을 정확하게 재구성해 주는 운영 Export/집계 엔진은 A에 없다.

**팀 합의 필요:** KPI ticket creation cohort는 생성 시점, handoff 발생 시점, 해결 시점 중 어떤 팀에 귀속할지 정해야 한다. VOC episode의 first_team과 재배정/지연 라벨 처리, 과거 팀 비활성화와 현재 열람 권한의 구분도 필요하다. B의 명시적 assignment/route 이벤트에 ticket/cycle/version·team-before/after·effective_at·event_id를 추가할지는 새 버전 계약 제안이다. 현재 A DB에 그 필드가 모두 있다고 가정하지 않는다.

## 실제 경로와 인증

**구현 확인:** 요청받은 `POST /internal/analytics/publish`는 존재하지 않는다. 한 번의 요청으로 업로드/검증/게시하는 API도 없다. 실제 경로 대응은 아래와 같으며 모두 성공 HTTP200이다.

| 단계/조회 | 실제 경로 | 인증/응답 |
|---|---|---|
| 수신 | POST /api/v1/analytics/batches | 서비스 analytics:receive / Submission → BatchStatus |
| 검증 | POST /api/v1/analytics/batches/{batch_id}/validate | 서비스 analytics:receive / body 없음 → BatchStatus |
| 게시 | POST /api/v1/analytics/batches/{batch_id}/publish | 서비스 analytics:publish / body 없음 → BatchStatus |
| 배치 상태 | GET /api/v1/analytics/batches/{batch_id} | 서비스 analytics:receive / BatchStatus |
| TOP10 | GET /api/v1/admin/analytics/voc/top | 현재 ADMIN+team scope / VocList |
| 부족·차단 | GET /api/v1/admin/analytics/voc/unavailable | 동일 / VocList |
| 제품 상세·근거·추세 | GET /api/v1/admin/analytics/products/{product_id} | 동일 / ProductDetail |
| 운영 KPI | GET /api/v1/admin/analytics/kpi | 동일 / KpiResponse |

**구현 확인:** Bearer 서비스 JWT는 로그인용과 다른 키(48자 이상), HS256, issuer=`csflow-analytics-service`, audience=`csflow-analytics-ingest`, allowlist sub, exp/iat/nbf/sub/iss/aud 필수 및 문자열 permissions 배열을 검사한다. 관리자 역할만으로 게시하지 못한다. receive 권한만 있으면 publish403, publish 권한만으로 receive/validate/get은 불가다. 두 권한을 줄지 분리할지는 운영 합의다. 개발용 claims 예시는 [samples/service-claims.json](samples/service-claims.json)이며 서명된 토큰/비밀은 제공하지 않는다. 발급 시 실제 현재 NumericDate와 짧은 exp를 사용해야 한다.

**구현 확인:** 배포 문서/이전 증거에서 ANALYTICS_SERVICE_IDS=[]라 연결은503 ANALYTICS_SERVICE_AUTH_NOT_CONFIGURED다. 이번에는 Azure를 조회하거나 바꾸지 않았다. 실제 Fabric subject·발급기·회전·attestation/Managed Identity 연결은 미구현/팀 합의이며 문서 예시를 현재 동작하는 Fabric 자격정보로 해석하지 않는다.

## 실제 wire와 정규화

**구현 확인:** [실제 생성 OpenAPI 발췌](openapi-analytics.json)는 앱 create_app().openapi()로 만들고 관련8경로와 참조 schema를 모두 포함한다. 경로·요청/응답/중첩 필드/required/nullable/enum/보안은 해당 JSON이 규범이다. [완전한 작은 LOCAL_SYNTHETIC 요청](samples/publish-request.json)은 기존 minimal seed의 상품/팀 UUID를 쓰며 운영 DB에 보내라고 만든 자료가 아니다.

Submission은 `{manifest,payload}`다. manifest에는 batch_id/schema_version/rule_version/source/source_as_of/generated_at/windows/history·operational·sales·prior·recent·end/calendar_timezone/team_ids/product_ids/scopes/row_counts/payload_checksums/source_input_hashes/kpi_definition/product_kpi_definition/sales_denominator_scope가 있다. 정확한 nested 구조는 예시/OpenAPI를 따른다. payload는 다음 네 배열이고 요청 행에는 batch_id/data_origin/created_at/updated_at를 넣지 않는다. 서버가 배치와 저장 메타데이터를 채운다.

| payload | 배치 내 PK(grain) |
|---|---|
| analytics_daily | day,team_key,category |
| analytics_product_daily | day,product_id,category,issue_tag |
| analytics_product_voc_daily | scope_key,product_id,day,primary_issue |
| analytics_product_risk | scope_key,product_id |

**구현 확인:** analytics-v1/voc_rule_v1만 허용한다. 시간은 history_start≤operational_start<window_end≤source_as_of≤generated_at, generated_at≤현재+5분. sales/prior/recent는 end-28/-14/-7일, window_end는 Asia/Seoul 자정이다. source는 LOCAL_SYNTHETIC 또는 FABRIC이며 FABRIC도 인증 서비스의 선언이다. 응답의 origin_verification=SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED/validation_result.origin_verified=false는 실제 파이프라인 실행 인증이 아님을 나타낸다.

**구현 확인:** JSON object는 extra=forbid, NaN/Infinity 불허이며 nested fields도 allowlist다. customer/ticket ID/원문/메모/임의 URL/파일명은 모델에 없어422다. analytics_max_bytes 기본8,000,000 bytes는 body를 읽을 때 제한하고 네 배열 합계 기본20,000행을 검사한다. 각 배열 모델 최대20,000행/risk 최소1개, team 최대8/product 최대1,000/scope 최대255다. max_bytes/max_rows는 설정값이며 여기 수치는 기본이다.

**구현 확인:** [canonical 해시 벡터](../examples/canonical-hashes.json)와 app/analytics_canonical.py가 규범이다. UTF-8/ensure_ascii=false/공백 없음/sort_keys, UTC Z/ISO date/UUID, Decimal은 trailing zero를 제거한 **문자열**, 정수값 float는 JSON 정수, 유한수만 허용한다. 테이블은 위 PK를 `str` tuple로 정렬하며 manifest 집합/각 scope 팀/스코프를 정렬한다. Decimal50.000000은 `"50"`이고 score의 wire 예시도 문자열이다. payload_checksums는 테이블별 canonical JSON **배열** 해시, content_hash는 manifest+payload 전체 정규화 해시다. source_input_hashes는 원천 파일 bytes 해시로 별개다. JSONL bytes 해시를 payload 해시로 복사하지 않는다.

## 수신→검증→원자 게시

**구현 확인:** 수신 트랜잭션은 head(RECEIVED)/receipt(정규화 **전체 Submission**, 단순 payload 배열만 아님)/감사를 원자 저장한다. same batch_id + same content_hash 재요청은 기존 상태를 반환한다. 같은 ID 다른 내용은409 BATCH_CONTENT_CONFLICT다. 별도 Idempotency-Key 헤더를 받는 API가 아니다.

**구현 확인:** validate는 candidate head 잠금 후 스키마·버전·윈도·FK(실재 팀/상품)·scope·rowcount·checksum·중복PK·counter·risk coverage·trend 합계·상태/점수/rank/band를 검사한다. team/product 존재만 검사하며 활성 여부/운영 품질의 진실까지 증명하지 않는다. 통과하면4mart/validation/감사 원자 적재 후 VALIDATED. 실패는 FAILED와 안전한 codes, mart 미적재다. validate의200이 성공 판정은 아니며 `validation_result.passed`를 확인한다. validate를 재시도해도 RECEIVED가 아니면 기존 상태만 반환한다. FAILED 수정은 새 batch_id로 제출한다.

**구현 확인:** publish는 singleton publication pointer→candidate head 순으로 잠그고 VALIDATED/증거를 검사한 뒤 저장된4mart를 타입 재검증해 rowcount/hash를 확인한다. 이전 current=false + 신규 SUCCEEDED/current/published_at + pointer + 감사를 같은 트랜잭션으로 저장한다. partial UNIQUE가 current 하나를 보장한다. window_end/source_as_of 모두 비감소이고 둘 중 하나는 증가해야 한다. 오래된 도착/동시 게시 loser는409 BATCH_NOT_NEWER로 기존 결과를 유지한다. 과거 SUCCEEDED 재요청은200/is_current=false일 수 있고 current로 다시 승격하지 않는다.

**구현 확인:** DB trigger는 성공 batch의 is_current 외 내용을 불변, 성공4mart는 INSERT/UPDATE/DELETE 불가, receipt는 전 상태 payload/hash/ID 변경 및 DELETE 불가로 보호한다. 성공 receipt는 기타 변경도 불가다. superuser/DDL 권한이 trigger를 우회할 수 있으므로 최소 runtime 역할이 필요하다. 검증/트랜잭션 실패 시 이전 성공과 기준시각을 유지하며 최초에는200 UNAVAILABLE/NO_PUBLISHED_BATCH/meta=null이다. head에 current=false라는 이유만으로 삭제 가능 판정하지 않는다.

**구현 확인:** 관리자 조회는 인증부터 REPEATABLE READ를 시작해 batch·scope·집계·상세·meta를 같은 snapshot으로 읽는다. query batch_id로 과거 성공 고정 조회가 가능하다. 현재 권한을 매번 검사하고 HTTP no-store, 별도 서버 cache는 없다. meta.cache_fingerprint는 principal/content_hash/선택scope 해시이며 향후 cache key에도 batch와 현재 권한 검증이 필요하다. stale 기본24시간은 source_as_of 대비이며 window_end와 다르다.

## 응답과 오류 예시

**구현 확인:** BatchStatus 필드는 batch_id,status,content_hash,is_current,validation_passed,validated_at,published_at,validation_result다. validator_version/origin_verified/codes/passed는 **validation_result 내부**다. 받자마자 NOT_VALIDATED에서는 passed=false/codes만 있다. 실패 validate도 BatchStatus 전체 안에 result를 넣는다. 기존 fabric-contract.md의 짧은 `{"passed":false,...}` 예시는 검증 결과 fragment이지 실제 전체 HTTP 응답이 아니라는 점을 보완한다.

**구현 확인:** 오류 body는 `{"error":{"code":"…","request_id":"…"}}`이며 raw validation 입력을 반사하지 않는다. 예시는 [samples](samples/README.md)에 receive/validate/publish 상태, 실패,409,unpublished KPI를 구분해 뒀다. API가 실제 실행된 증거가 아닌 타입 검증된 합성 예시다.

| HTTP | 실제 코드/의미 |
|---|---|
| 401 | SERVICE_AUTHENTICATION_REQUIRED, INVALID_SERVICE_CREDENTIALS |
| 403 | SERVICE_PERMISSION_REQUIRED, ADMIN_ROLE_REQUIRED, ANALYTICS_TEAM_SCOPE_DENIED |
| 404 | BATCH_NOT_FOUND, MANAGED_BATCH_NOT_FOUND, PUBLISHED_BATCH_NOT_FOUND, ANALYTICS_PRODUCT_NOT_FOUND |
| 409 | BATCH_CONTENT_CONFLICT, BATCH_NOT_VALIDATED, VALIDATED_PAYLOAD_CHANGED, BATCH_NOT_NEWER |
| 413 | ANALYTICS_ROW_LIMIT, ANALYTICS_UPLOAD_TOO_LARGE. production 공통 body 경계가 먼저 거부하면 REQUEST_TOO_LARGE |
| 422 | VALIDATION_ERROR(형식/미허용필드), DUPLICATE_TEAM_FILTER |
| 503 | ANALYTICS_SERVICE_AUTH_NOT_CONFIGURED, DATABASE_UNAVAILABLE |

검증 결과 codes(HTTP200/FAILED)는 SCHEMA_VERSION/RULE_VERSION/TIME_WINDOW/RULE_WINDOWS/DAY_BOUNDARY/FUTURE_WATERMARK, TEAM_FK/PRODUCT_FK/ROW_PRODUCT_FK/ROW_SCOPE_FK, MANIFEST_DUPLICATE/SCOPE_DUPLICATE/SCOPE_SET_DUPLICATE/SCOPE_TEAMS, PAYLOAD_CHECKSUM/ROW_COUNT/DUPLICATE_PK, DAILY_TEAM/DAILY_WINDOW/DAILY_COUNTER/DURATION_DENOMINATOR/PRODUCT_DAILY_WINDOW/PRODUCT_COUNTER/TREND_WINDOW/TREND_COUNTER/RISK_COVERAGE, EXPLANATION_WEIGHT/EXPLANATION_COMPONENT/RISK_WATERMARK/METRIC_COUNTER/DATA_STATUS/TREND_TOTAL/GLOBAL_SALES_DENOMINATOR/NONELIGIBLE_NULLS/ELIGIBLE_VALUES/RISK_BAND/EXPLANATION_TOTAL/RANK_ORDER다. 코드 목록은 app/analytics_validation.py의 검사와 대조한다.

## VOC·KPI 정의와 한계

**구현 확인:** C/P=scope 최근/직전7일 불만 episode 수, S=팀 공통 상품 유효 paid cohort28일, N=최근 episode의 주문 중 판매cohort에 포함되는 distinct 주문 수, M=최대 primary_issue episode 수, U=미해결 episode 수, K=distinct 고객 수라는 **upstream 계약**을 검증한다. A가 원장으로 이를 재계산하거나 normalized/점수를 대체하지 않는다. A의 산술 검사는 제공된5요소 근거의 가중치(0.10/0.35/0.25/0.20/0.10)·contribution·score합 일관성뿐이다. 원천의 episode/paid 정당성은 Fabric/B와 별도 검증해야 한다.

**구현 확인:** sales_complete=false→DATA_MISSING, quality_ok/complaints_complete/episode_state_complete 중 false→QUALITY_BLOCKED, S<30 또는 C<5 또는 K<3→LOW_SAMPLE, 나머지 ELIGIBLE. 비eligible score/rank/risk_band는 모두 NULL이며0으로 바꾸지 않는다. eligible은 score0–100, band <40 NORMAL/<60 WATCH/이상 HIGH. 순서는 score DESC,C DESC,product UUID ASC로 검증하고 rank1..n 연속 고유값을 요구하므로 공동순위가 아니다. 추세는 Fabric이 제공한 날짜/primary_issue episode/unresolved만 조회한다. 점수는 관리 우선순위이며 불량률/결함 확정이 아니다.

**구현 확인:** operational KPI는 제공 analytics_daily를 합산한다. grain은 ticket_creation_cohort/day/team/category이며 메시지·처리회차·VOC episode가 아니다. 자동완료/이관 비율의 분모는 ticket_count 합, 처리 평균은 Σduration_sum_seconds / Σduration_n이다. 전체 manifest 팀을 선택할 때만 team_key=AUTO를 포함하고 subset은 해당 귀속 팀 행만 쓴다. AUTO는 UUID FK가 아니라 미귀속 자동 경로 label이다.

**구현 확인:** fixture-ticket-v1은 SYNTHETIC_APPROXIMATION이고 재문의0·승인/검토 proxy·SLA를 UNAVAILABLE/FIXTURE_PLACEHOLDER_OR_PROXY로 반환한다. ticket-cohort-v1도 네 미합의 지표는 DEFINITION_NOT_AGREED다. 응답 raw rows의 해당 필드를 UI가 정확한 운영 성과로 올려 표시하면 안 된다. 제공 처리시간은 회차별 활성 업무시간 측정이 아니다.

**구현 확인:** analytics_product_daily에는 팀 차원이 없다. 전체 manifest 팀 scope에서만 tag-grain 원본 행을 제공하고 subset은 PRODUCT_KPI_HAS_NO_TEAM_SCOPE로 unavailable이다. issue_tag가 겹칠 수 있어 unique_ticket_totals=UNAVAILABLE_TAG_ROWS_MAY_OVERLAP다. paid/inquiry/prior NULL을0으로 대체하지 않는다. 분석 응답에 후속 메모·상담 원문은 없다.

**팀 합의 필요:** 운영 cohort/팀 귀속/회차별 처리시간·재문의/SLA/승인·검토/paid와 episode 완전성·정정 재게시 및 product KPI 팀 차원을 확정해야 한다. 실제 원장 추출·Fabric Notebook·서비스 인증/해시 emitter의 통합은 미검증이다.
