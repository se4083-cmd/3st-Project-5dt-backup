# Fabric 담당자에게 전달할 계약 — 4단계

후속0.11.0의 [VOC 효과 별도 버전 wire/수신·검증·원자 게시](monitoring-effects.md)는 기존 analytics-v1 계약과 분리됩니다. 이 문서의 기존 Gold wire는 그대로이며 effect source 정의/판매 분모·scope·상품 식별은 별도 합의가 필요합니다.

2026-11-03 실제 DB/DDL·fixture 차이·이벤트·미구현 Export·현재 게시 경계는 [fabric-data-contract/README.md](fabric-data-contract/README.md)에 보완했다. 아래 짧은 passed/codes 예시는 BatchStatus.validation_result fragment이며 전체 HTTP 응답 예시는 새 전달 자료를 따른다.

현재 구현은 [4단계 설계](phase4-analytics.md)와 [OpenAPI](openapi.json)를 따릅니다. 아래 이전 단계 계획의 ‘게시/조회 미구현’ 설명을 대체합니다. Fabric은 계산, A는 네 mart 수신·검증·원자 게시와 권한 조회를 담당합니다. 실제 Fabric emitter/인증/파이프라인은 미검증이며 로컬 성공 출처는 LOCAL_SYNTHETIC입니다.

일반 로그인 토큰/관리자 역할은 서비스 권한이 아닙니다. 별도 ANALYTICS_SERVICE_SECRET(독립 무작위48자 이상), ANALYTICS_SERVICE_IDS allowlist를 설정해야 합니다. 미설정은503입니다. HS256 issuer=csflow-analytics-service, audience=csflow-analytics-ingest, sub=allowlist의 서비스ID, 필수 exp/iat/nbf와 permissions 배열을 검증합니다. 예: `{"sub":"fabric-publisher","iss":"csflow-analytics-service","aud":"csflow-analytics-ingest","iat":1793588400,"nbf":1793588400,"exp":1793588700,"permissions":["analytics:receive","analytics:publish"]}`. 시각은 발급 시 실제 NumericDate로 정하고 비밀을 브라우저·Git·로그로 보내지 않습니다. 실제 발급기/회전·Managed Identity 통합은 팀 제안이며 아직 구현하지 않았습니다.

POST `/api/v1/analytics/batches`에 Submission JSON, POST `/{batch_id}/validate`, POST `/{batch_id}/publish` 순서입니다. GET `/{batch_id}`로 상태를 확인합니다. Authorization: Bearer 서비스 토큰을 사용하며 수신·검증·조회는 analytics:receive, 게시만 analytics:publish입니다. [완전한 최소 합성 JSON](examples/analytics-batch.json)은 최소 seed용 team/product ID이며 운영에 그대로 쓰지 않습니다. 실제 필드/정규화·기간·NULL·scope 규칙은 위 설계/OpenAPI의 allowlist를 따릅니다. 서버는 manifest의 임의 경로나 URL을 읽지 않습니다.

수신 timeout은 동일ID·같은내용으로 재시도, 다른내용은409 BATCH_CONTENT_CONFLICT입니다. validate의200에서도 passed=true인지 확인합니다. 예: `{"passed":false,"codes":["PAYLOAD_CHECKSUM","ROW_COUNT"],"validator_version":"analytics-v1","origin_verified":false}`는 FAILED이고 수정에는 새ID가 필요합니다. 형식/금지필드422, 권한401/403, byte/행초과413, 미설정/DB장애503, 미검증게시409 BATCH_NOT_VALIDATED, 적재변경409 VALIDATED_PAYLOAD_CHANGED입니다.

게시 timeout도 같은ID 재시도하며 과거 성공은200/is_current=false로 반환될 수 있습니다. 늦은 배치409 BATCH_NOT_NEWER는 최신을 덮어쓰지 않습니다. 실패/부분 적재는 이전 성공 기준시각을 유지하며 최초는 NO_PUBLISHED_BATCH입니다. source=FABRIC은 인증 서비스 선언이며 A가 pipeline 실행 증거를 외부 확인하지 않습니다. origin_verification도 이를 표시합니다. source attestation/lineage 서명·실행ID는 후속 합의 항목입니다.

원천 source_input_hashes와 정규화 payload_checksums를 구별합니다. 기존 fixture head.checksums는 전자입니다. `python -m scripts.prepare_analytics_fixture reference/fixture .cache/analytics-payload.json`은 오프라인 파일 생성만 하며 기존 점수/순위를 복사하고 coverage/15scope/해시를 보완합니다. Python canonical 참조와 실제 Fabric emitter의 hash 일치 테스트는 별도 통합 범위입니다.

KPI 합의에는 ticket/cycle/message/episode 구분, 생성 cohort·팀 귀속·미귀속 AUTO, 자동완료/이관 분모·처리시간 합계/건수, 재문의/SLA/승인/검토 이벤트, 늦은 데이터·정정/삭제가 필요합니다. fixture의 재문의0/승인·검토 proxy는 unavailable이며 ticket-cohort-v1도 미합의 지표는 unavailable입니다. product_daily 팀차원 부재/tag 중복/NULL 분모도 보완해야 합니다. 표본 제외는 data_status/coverage/S·C·K와 outside_cohort를 제공하지만 원본 excluded_count는0이고 세부 제외 사유코드가 없습니다. 추가 제외를 지원할 때 enum별 건수 계약을 합의하고 미제공 사유를 추정하지 않아야 합니다. Gold에는 고객/티켓 ID·원문·후속 메모를 넣지 않습니다.

## B 이벤트 연계

재문의/직접 연결은 cycle/version 증가와 TICKET_REOPENED/AGENT_REQUESTED 감사를 기록하고, 자동 확정은 AUTOMATIC_REPLY_COMMITTED를 기록합니다. Fabric은 현재 snapshot만으로 과거 회차를 복원하지 않고 메시지/감사/후속 원래·책임 회차를 함께 해석해야 합니다. 실제 운영 추출기는 후속 통합 범위입니다.

## 5단계 로컬 인수

fabric-handoff.md와 examples/canonical-hashes.json에 Decimal/UTC 시각/PK 정렬/정규화 문자열·테이블별 해시·전체 content 해시의 실제 벡터를 제공합니다. scripts.check_handoff_contract로 오프라인 검사합니다. HTTP 검증은 로컬 PostgreSQL 안의 current 전환만 수행하며 source=LOCAL_SYNTHETIC입니다. 실제 Fabric 접속/파이프라인/출처 인증/운영 emitter를 실행한 결과가 아닙니다. 파일은 로컬에만 작성했고 팀원 전송/원격 push를 하지 않았습니다.

## 7단계 보관 미리보기

[보관 계약](phase7-retention-preview.md)과 fabric-handoff.md의 receipt/batch/mart 보관 단위·시계·불변성 합의 항목을 따른다. A의 DEV_RETENTION_V1은 로컬 집계 미리보기이며 원천/Blob/Fabric/백업을 검사하거나 정리하지 않는다. receipt에 제출 payload가 중복 저장되고 실패 receipt도 불변 trigger가 있으므로 미게시만으로 삭제 가능 판정을 내리지 않는다. 원천 시각과 저장 시각을 구분하고 실제 emitter·외부 추출/Gold/backup 보존·정정/재게시/hold 정책을 공동 확정한다. 삭제/예약/삭제 SQL·외부 호출은 이번 구현에 없다.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
