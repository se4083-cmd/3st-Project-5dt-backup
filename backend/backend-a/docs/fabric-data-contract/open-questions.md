# 데이터 계약 협의 사항

## 먼저 필요한 파일 — 팀 합의 필요

1. 2026-11-04 첨부로 **합성5개 JSONL·12,008행과 schema_contract.json, 작은4개 A 제안 파일의 validation**은 받았다. [검토](audit-export-review.md). **원본 Manifest와 실제 Bronze/Silver printSchema·적재/승인 증거는 여전히 필요**하다. validation은 원본 Manifest나 전체12,008행 검증 결과가 아니다. A 실제 DB 건수로 간주하지 않는다.
2. 지금 필요한 입력은 합성 fixture 재사용인가, 운영 A DB full snapshot인가? 운영 DB→Blob Export는 **미구현**이다. 첫 범위를 원문 없는 full snapshot으로 정하고 추출 주체(A/B/별도 운영 담당), 주기·소유권·네트워크·읽기 identity를 누가 맡을지 정해야 한다.
3. 실제 Fabric Notebook/emitter가 사용할 Gold schema/rule_version, 팀/product registry와 subject/발급기를 공유할 수 있는가? A의 실제 API는 `/api/v1/analytics/batches`→`/{batch_id}/validate`→`/{batch_id}/publish`이고 `/internal/analytics/publish`는 없다. 현재 Azure 서비스 ID allowlist는 배포 증거상 비어 있다. 키는 별도 안전한 경로로 합의하며 문서/메신저에 넣지 않는다.

## 데이터 의미 — 팀 합의 필요

| 우선순위 | 질문 | 미확정 시 안전한 처리 |
|---|---|---|
| P0 | 합성 CUSTOMER_CONTACT와 같은 실제 접촉 producer/occurred_at/채널/중복 기준을 누가 제공하는가? | A record는 해당 action을 만들지 않음. 감사 created_at을 접촉 시각으로 쓰거나 접촉을 추정 생성하지 않음 |
| P0 | audit 7필드 allowlist·새 projection 버전과 customers 참조 보조 파일 유지/별도 registry에 동의하는가? | 기존4파일 보존 + customers 유지. payload 문자열/전체 JSONB와 원본 식별자 제외 |
| P0 | ticket creation cohort/재문의/회차/메시지/VOC episode의 각 집계 단위와 관찰 기간은? | 현재 미합의 재문의/SLA/승인·검토 KPI는 unavailable 유지 |
| P0 | 재문의·팀 재배정·지연 라벨 시 최초 팀/발생 팀/해결 팀 중 어디에 귀속하는가? | 현재 team_id/마지막 배정으로 과거 모든 이벤트를 재분류하지 않음 |
| P0 | 불만 primary_issue를 누가 언제 확정하고 당시 product/order/team/cycle 상태를 어떻게 보존하는가? | snapshot만으로 customer_contacts/과거 episode를 생성할 수 있다고 보장하지 않음 |
| P0 | sales_complete 등 true의 근거는 무엇이며 제품/28일/7일/이전기간별 unknown을 어떻게 표현하는가? | source_as_of나 파일 존재만으로 true를 주지 않음. 현 Gold bool 버전의 unknown 대응 합의 |
| P0 | 판매 S는 팀 공통 GLOBAL_PRODUCT_PAID_28D라는 fixture 전제를 실제 운영에도 유지하는가? | 같은 상품 scope별 S 동일성 검증 유지. 팀별 분모로 조용히 바꾸지 않음 |
| P0 | customer HMAC join_domain/키 관리·회전·팀 간 join 목적/접근 주체는? | 익명화 표현 금지. 실제 키/연결정보 전송 금지. 공통 K를 팀 K 합계로 대체하지 않음 |
| P0 | Gold의 현 analytics-v1/voc_rule_v1·가중치·threshold·동점 순서에 동의하는가? | 미합의 변경은 새 버전 후 반영. A에서 점수 새 계산/대체하지 않음 |
| P1 | product KPI에 team 차원을 추가할 것인가? tag 중복·distinct ticket/paid denominator는? | 부분 팀은 PRODUCT_KPI_HAS_NO_TEAM_SCOPE, 고유 티켓 합 unavailable |
| P1 | 늦은 commit·수정·삭제·지연 episode의 재계산 horizon, Export snapshot/CDC watermark는? | audit_events를 CDC라고 부르지 않음. 증분/tombstone 미지원 표시 |
| P1 | 제출 source_input_hashes 5항목을 분할 원천 파일/다중 테이블 lineage와 어떻게 연결하는가? | 임의 extra field는422. 별도 sidecar/새 schema 합의 |
| P1 | snapshot reader 장기 transaction 제한·최대part/row수·완전 업로드 marker/재시도 정책은? | 문서 개발 기본값은 제안. 실제 클라우드 쓰기 없음 |
| P1 | Bronze/Silver/Gold/receipt/Blob/backup의 보존·hold·정정 정책과 소수집단 노출 기준은? | DEV_RETENTION_V1은 제안이며 법적 준수/실삭제/Blob검사로 주장하지 않음 |

## 문서와 코드의 차이·보완

| 관찰 | 구현 확인 / 판단 |
|---|---|
| 기존 Fabric handoff의 구 API URL과 새 이름 절이 함께 존재 | 이전 기록은 구 URL. 현재 전달 주소는 새 csflow-backend-a. 기존 절을 역사로 표시하고 새 자료 링크를 추가함 |
| 기존 handoff의 '게시=로컬 PostgreSQL' 문구 | 해당 단계의 로컬 검증 설명. 현재 기능은 배포 가능하지만 실제 Fabric 연결/게시 실적은 아님 |
| fabric-contract의 passed/codes 단독 실패 예시 | 실제 HTTP 응답은 BatchStatus.validation_result 안에 해당 객체가 들어감. 새 샘플은 전체 envelope |
| README의 과거 '클라우드 미검증'과 최신 배포 기록 | 단계별 과거 기록이다. 현재 로컬 소스/기존 배포 증거/이번 새 DDL 추출을 나눠 표기함 |
| fixture schema_contract와 모델/DDL | A 추가테이블9개+Alembic1개, 컬럼·NULL/FK/제약 차이가 있음. fixture-differences.md/json 참조 |
| fixture nested_json_encoded | 파일은 JSON 문자열을 중첩한 옛 Spark 관례. 실제 DB는 JSONB/Gold API는 typed object. Export 제안과 wire버전을 분리함 |
| 기획서 가명추출→Blob→Fabric, 일2회 | **기획/책임 흐름**이며 현재 A 운영 Export가 구현된 증거가 아님. 외부 fixture 생성기도 운영 Export 아님 |
| 기획서 최근5건 3줄/전체 자동화/KPI 목표 | 실제 B/AI/Fabric 엔진·정확한 모든 KPI 통합 완료로 해석하지 않음 |
| schema.sql 소유권/권한 | portable schema-only이며 --no-owner/--no-privileges. 실제 Azure role/ACL 재적용 스크립트 아님 |
| 과거 Azure 구조 검증 기록 | 당시 32테이블/138제약 등 대조. 이번 배포 DB 재접속·스키마 일치 확인은 하지 않음 |

**미구현:** 운영 Export·Blob 업로드·Fabric emitter·CDC/outbox·완전한 과거 팀 이벤트 ledger·서비스 발급/회전·정확한 미합의 KPI. 이번 문서 작성으로 완료 상태를 올리지 않는다.
