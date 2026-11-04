# 구현 근거와 설계 결정

2026-11-02 KST 기준입니다. 빈 Git 저장소(기존 커밋·코드 없음)와 작업 폴더/상위 폴더의 AGENTS.md 유무를 확인했습니다. 발견된 AGENTS.md는 없습니다. 프로젝트 기획서·합성 데이터 계약·검증 자료를 설계 근거로 사용했습니다. 원천 자료 검토와 운영 환경 실행 검증을 구분합니다.

## 확인한 자료

공식 기획서 v4.1은 Backend A에 인증/RBAC·티켓·고객360·후속·KPI와 VOC 조회/권한/게시를 배정합니다. Backend B는 Mock·AI·상담 처리 엔진을 맡습니다. 자동 안내 경로에 사람 승인 단계를 일률적으로 표시하지 않으며, 관리자도 허용 팀 안에서 조회해야 합니다.

기획서는 별도 v4.0 상세본과 상세 구현 기획서 v4.1을 참조하지만 이번 첨부에는 없습니다. 따라서 아래 상태 사전, SLA, 종료 배정과 재배정 정책은 **이번 구현 제안**입니다. 팀 확정 사항으로 간주하지 않습니다.

ZIP의 README, config, schema_contract, PostgreSQL DDL/적재 SQL, 생성기/검증기, Fabric Python/Notebook 초안과 validation 산출물을 확인했습니다. 원본 fixture SQL은 독립 `csflow_fixture` 스키마용이며 앱 migration이 아닙니다. 기존 검증 기록의 PASS는 제공자의 기록이며 이번 API 검증 결과와 구분합니다. 데이터 스크립트와 VOC 점수 계산 코드는 앱에 편입하지 않았습니다.

`config.json`: scenario `CSFLOW_DEMO_20261031`, generator `synthetic_v2.0`, seed `20261031`, 분석 기준 `2026-10-31T03:00:00Z`, window_end `2026-10-30T15:00:00Z`, history_start `2026-10-02T15:00:00Z`. 신규 티켓·메시지·작업에는 실제 현재 UTC를 사용하고 분석 기준시각으로 대체하지 않습니다.

## DB 매핑

22개 공식 테이블 이름과 원본 필드를 SQLAlchemy 모델에 보존했습니다. 이번 핵심 흐름 이외의 테이블은 이력 적재와 후속 확장을 위한 구조이며 관련 API를 제공하지 않습니다. Silver/Gold 보조 파일(coverage, contacts, episodes, metrics, TOP N)은 원본 디렉터리에 보존하며 운영 앱 테이블로 중복 적재하지 않습니다.

원본 대비 추가한 필드/테이블은 다음과 같습니다.

| 대상 | 추가 내용과 이유 |
|---|---|
| users.is_dev_account | 개발 자격정보를 운영 로그인·토큰 인증에서 차단 |
| user_team_scopes | 실제 권한의 원장. 원본 allowed_team_ids JSON은 이력 호환용이며 런타임 권한 판단에 사용하지 않음 |
| team_categories | 팀별 업무 분류. 상담사 배정과 별개로 업무 범위 확인 |
| tickets.team_id | 현재 업무 팀. 과거 임의의 배정이 관리자 권한을 확대하지 않도록 명시 |
| messages.visibility | 기본 INTERNAL, 명시적인 PUBLIC만 고객에게 반환 |
| automation_jobs.expected_ticket_version | 작업 생성 시점의 낙관적 동시성 기준 |
| automation_jobs.lease_owner | B worker lease 식별자, 토큰과 만료시각을 함께 사용 |
| audit_events.result / reason_code | 원문 없는 결과·사유 기록 |
| idempotency_keys | user_id+key 복합 PK, 정규화 요청 해시, 고정 접수 결과 |

필수 ticket_id/cycle_no는 메시지·작업·배정에서 NOT NULL로 강화했습니다. 주문 소유자·상품의 복합 FK, 양수 회차/버전, 작업 상태/lease 정합성, 최종 응답과 작업 중복 방지, 공개 메시지 형태, VOC의 ELIGIBLE 필수 점수·순위·밴드와 비대상 NULL을 검사합니다. PostgreSQL CHECK의 NULL 통과를 피하도록 IS NOT NULL과 NOT NULL을 함께 사용했습니다. 미래 migration은 새 revision으로 추가하며 초기 revision을 실행 중 모델에 연결하지 않습니다.

고객 FAQ는 주문/상품을 NULL로 저장합니다. 분류를 A가 추측하지 않고 초기 `UNCLASSIFIED`로 둡니다. `sla_due_at=접수+24시간`은 스키마 필수값을 채우는 임시 정책이며 실제 SLA 정의는 팀 합의가 필요합니다. VOC 라벨도 `UNLABELED`, human_verified=false로 시작합니다. 실시간 새 데이터는 APPLICATION/LIVE, 최소 개발 seed와 원본 이력은 SYNTHETIC으로 구별합니다.

## fixture 적재와 이력 보존

전체 적재는 22개 테이블을 FK 의존 순서로 한 트랜잭션에 넣습니다. rules → suggestions → approvals → messages 순서가 성립합니다. 오류면 전체 rollback하며, 재실행은 기존 PK를 변경·삭제하지 않습니다. 동시에 seed를 실행하는 운영 도구는 이번 범위가 아닙니다. 충돌/오류 시 기존 자료를 삭제해 해결하지 않습니다.

원본 티켓의 team_id는 가장 최근 합성 배정의 team_id에서 채웁니다. 원본 job은 모두 종료 상태이므로 expected_ticket_version을 현재 합성 ticket.version으로 채워 이력으로만 보존합니다. 이 값으로 과거 처리 시점의 버전을 복원했다는 뜻은 아닙니다. 원본 메시지 중 고객 IN, 승인 ID가 있는 AGENT/ASSISTANT OUT만 공개 이력으로 매핑하며 이 승인을 실제 정책 활성화 근거로 사용하지 않습니다.

`!DISABLED_SYNTHETIC_LOGIN`은 어떤 입력으로도 인증되지 않도록 처리합니다. 최소 seed는 원본 계정과 별도 UUID 영역에 4개 개발 계정·2개 고객·1개 팀·1개 상품·6개 주문을 만듭니다. 비밀번호는 실행자 입력을 Argon2id로 해시합니다. 재실행으로 비밀번호를 재설정하거나 비활성 계정을 살리지 않습니다. 비밀번호 재설정 기능은 별도 작업입니다.

## 권한과 전이 제안

고객은 DB의 user_id→customer_id 관계로 결정합니다. 요청의 customer_id/role/product_id는 extra=forbid로 거부합니다. 타인 주문/티켓과 존재하지 않는 ID는 모두 404로 응답합니다. 고객은 공개 메시지만 봅니다. 초기 staff API도 공개 응답 스키마만 반환하며 내부 데이터 열람 API는 없습니다.

상담사는 사용자 활성, 소속 팀=티켓 현재 팀, 명시적인 팀 scope, 팀 활성, 업무 category, 자신의 시작된 활성 배정, 현재 cycle 일치와 처리 중 상태를 모두 만족해야 합니다. 단순 ended_at=NULL만으로는 허용하지 않습니다. RESOLVED/CANCELLED와 이전 회차 배정은 거부합니다. 관리자는 user_team_scopes 안의 현재 활성 팀 티켓만 조회합니다. 전체 열람 fallback은 없습니다. 새 미배정 티켓은 현재 고객 외 staff가 볼 수 없으며 B가 라우팅/배정을 확정한 뒤 업무 범위에 들어옵니다. 관리자 접수 큐가 필요하면 별도 제한된 권한을 합의해야 합니다.

2단계에서는 ticket 잠금과 expected_revision 검증, cycle_no/version 증가, 이전 미완료 작업 무효화와 활성 배정 종료를 실제 구현했습니다. 과거 배정을 삭제하지 않고 ended_at을 설정하며, 새 배정 생성은 B 엔진의 후속 작업입니다. 사람 경로는 재문의 후에도 유지합니다. 원본 resolved 배정은 새 고객 명령이 없을 때 수정하지 않고 조회 정책으로 차단합니다. 상세 전이·멱등·공통 확정 경계는 [2단계 설계](phase2-cycles.md)를 따릅니다. 관리자 고객360의 목적 입력·필드별 마스킹·이력 범위는 다음 단계입니다.

## 자료의 한계

3단계에서 후속 CRUD·관리자 책임 큐·원래/책임 회차·공통 해결 차단과 고객360을 구현했습니다. 0003의 제약·scope 교집합·후속 인수·반복 정의·snapshot·AI 최소 입력 정책은 [3단계 설계](phase3-followups-customer360.md)에 명시했습니다. 이 문서의 이전 단계 미정 사항 중 해당 범위는 그 설명을 따르며 고객360 전체 이력을 무조건 허용하지 않습니다.

3,000개 문의는 1,000개 티켓의 3회 접촉이며 고유 문장은 36개입니다. 자연어 분류/RAG 성능평가에 사용하지 않습니다. 모든 fixture는 cycle=1이고 followup은 OPEN/IN_PROGRESS뿐입니다. 동시 접수·실패·다른 회차 사례는 이번 테스트가 별도로 생성합니다. 정책30·규칙6은 비활성, 배치는 VALIDATED/미게시입니다. 기존 KPI 계산과 Fabric 점수 검증 초안은 서비스 집계 정의·운영 파이프라인 완료로 간주하지 않습니다.

## 4단계에서 구체화한 제안

수신·검증·게시/조회는 phase4-analytics.md와 OpenAPI가 현재 계약입니다. legacy fixture는 미게시로 보존하고 별도 managed ID를 사용합니다. source입력 해시와 payload해시를 구분하며 생성된 LOCAL_SYNTHETIC 결과를 실제 Fabric 실행으로 표시하지 않습니다. A는 운영 점수를 계산하지 않고 제공 rank/설명/NULL/scope를 검증합니다.

서비스 JWT 발급·키회전/Managed Identity·출처 attestation, stale24h/미래유예5분, bytes/행 상한, 실제 팀 귀속·AUTO·집계 cohort, 재문의/승인/검토/SLA·회차별 처리시간, 제품 KPI 팀차원/중복 없는 분모는 팀 확정이 필요합니다. 이번 기본값은 구현 제안입니다. 팀차원 없는 지표와 fixture 고정0/proxy는 unavailable이며 합산/전체팀 fallback으로 채우지 않습니다. B·AI·Fabric 실제 통합은 검증한 것으로 간주하지 않습니다.
