# P1 정책 변경 영향 분석·버전 비교 — 구현/검증 (2026-11-04 KST)

작업 기준/HEAD `0f0e0d46377b8de805aab932614d39131738deed`, feature/backend-plus. 미커밋 작업 트리이며 push/PR/다른 브랜치 수정/배포는 하지 않았다. [API·상태별 스키마·React 계약](p1-policy-api.md), [검증 요약](evidence/p1-policy-20261104/summary.json).

## 조사와 재사용

기존 knowledge_documents는 policy_key/version/본문/hash·topic·active/approval/effective 필드를 갖고, ai_suggestions.evidence_refs에는 문서 ID/version/hash가 기록된다. suggestion→automation_rules의 FK와 rule_version이 있다. 기존 직원 상세의 staff_detail.evidence는 참조의 정확한 버전/hash/topic을 확인하므로 재사용했다. 기존 repository.ticket_scope와 tickets.team_id로 허용팀의 과거 응답만 조회한다.

독립 FAQ master/정책 매핑이나 rules.conditions 내 정책 의존 스키마는 확인되지 않았다. Backend B 계약은 답변/worker 경계이며 실제 RAG/Search 정책 활성화 계약은 아니다. 문자열·제목 유사성으로 의존을 만들지 않는다. 기존 P0 문서/규칙을 버전 저장소로 덮어쓰지 않고 P1 검토용 작업 공간을 분리했다.

P1 authorize·현재 활성 SQL 팀/ADMIN capability, 기존 cursor/감사/오류 봉투와 p1_idempotency를 재사용했다. VOC의 remember helper에 response_status 선택 인수만 추가했고 기본 VOC 동작은 유지했다. 실제 VOC 생성/검토·운영 모니터링 로직과 P0 business service는 변경하지 않았다.

## 구현과 운영 분리

신규 policy_models/schemas/analysis/service/router.py로 분리했다. 정책 key와 고정 팀 집합, append-only 제목/본문 버전을 보관한다. 이전 최신 version_no 기대값으로 변경 충돌을 막고 동일 key/body는 replay한다. LF 정규화, 본문20000자·500줄과 닫힌 입력 스키마를 적용했다.

비교는 같은 정책의 이전→이후 버전에 대해 INITIAL_VERSION/NO_CHANGE/METADATA_ONLY/CONTENT_CHANGED와 0 기반/끝 제외 줄 범위의 insert/delete/replace를 제공한다. diff/impact를 출력 스키마 기본값까지 고정하고 analysis_hash로 저장한다. 기존 비교를 새 참조 결과로 덮어쓰지 않는다.

기존 source_document_id 연결은 요청한 policy_key와 전체 body가 로컬 문서에 일치할 때만 저장한다. version/선언 hash/실제 body hash를 별도로 보존한다. 다음 버전에 source를 자동 상속하지 않으며, 비교 baseline의 현재 로컬 문서 version/hash/body가 캡처와 다르면 영향은 미확인이다. source에는 분석 중 공유 잠금을 사용한다.

확인된 인용만 허용팀의 auto_replies/FAQ category 기록으로 보고한다. 정확한 rule_id/version의 동시 사용 관계는 보고하지만 규칙 conditions의 직접 의존으로 승격하지 않는다. 링크에 합성/애플리케이션 출처와 규칙 active를 구분하며 raw draft/prompt/conditions/blob/customer 원문을 영향 출력에 넣지 않는다. 최대1000건의 scoped suggestion 스캔과 truncated를 표시한다. actual_affected_count는 항상 null이고 미래/runtime 효과는 UNCONFIRMED다. FAQ 카탈로그, B runtime, RAG index, Azure AI Search는 미확인 상태다.

관리자 검토는 최신 미검토 후보에 한해 APPROVED/REJECTED로 1회 확정한다. comparison revision, policy lock, 후보 상태 조건부 UPDATE 및 UNIQUE로 중복/동시 검토를 막는다. 다른 비교에서 확정된 후보나 최신에서 밀린 후보는409다. 검토 이유/actor/시각은 이력으로 남는다. **모든 응답의 activation=NOT_SUPPORTED**이며 승인만으로 기존 문서/규칙/인덱스/메시지/worker를 변경하지 않는다.

## API와 DB

신규 10 operation은 [OpenAPI](openapi.json)와 [API 명세](p1-policy-api.md)에 정의했다. 정책 등록/목록/상세, 버전 추가/페이지/상세, 비교 생성/페이지/상세, 검토를 제공한다. P1_POLICY_READ/WRITE/REVIEW와 현재 전체 팀 범위를 구분한다. P1_ENABLED 및 기본 false인 P1_POLICY_ENABLED로 opt-in하며 외부 키·연결이 필요 없다.

Alembic **0010 → 0009**, 단일 head. 기존 0001–0009/의존성/잠금 파일은 그대로다. 신규 테이블:

| 테이블 | 저장/제약 |
|---|---|
| p1_policies | key+팀집합 hash UNIQUE, 최신 version_no, 생성자 |
| p1_policy_teams | 정책/팀 FK 및 복합 PK, 불변 scope |
| p1_policy_versions | 정책별 version_no UNIQUE, 본문/제목/hash, 선택 source FK+snapshot, 검토 상태/revision |
| p1_policy_comparisons | 정책/버전 FK, diff/impact/hash, 상태/revision, 생성자/시각 |
| p1_policy_reviews | 비교/버전/검토자 FK, 비교·대상 버전당1회 UNIQUE, 결정/이유 길이 CHECK |

기존 p1_idempotency의 POLICY_REGISTER/COMPARE/REVIEW operation을 사용한다. task producer/lease/외부 activation engine을 만들지 않았다. 신규 테이블은 공식22테이블 seed fixture에서 제외했다. 모델 drift 없음, 빈0010→0009→0010 왕복, 기존 P0/P1 task/VOC 이력 보존을 확인했다. 정책 행/버전/팀/비교/검토가 남으면 downgrade를 거부하고 offline downgrade도 거부한다. 자동 삭제/CASCADE 정리는 없다.

## 최종 검증

Python3.12.14/Linux, 기존 고정 requirements, 실제 격리 로컬 PostgreSQL17.11/테스트별 임시 schema. Azure/Search/RAG/B 런타임은 호출하지 않았다.

| 실행 | 수집 | 통과 | 실패/오류 | 건너뜀 |
|---|---:|---:|---:|---:|
| 전체 P0/P1/VOC/정책 SQLite | 530 | 476 | 0 | 54 |
| 전체 P0/P1/VOC/정책 PostgreSQL | 530 | 520 | 0 | 10 |
| 최종 정책 집중 SQLite | 29 | 27 | 0 | 2 |
| 최종 정책 집중 PostgreSQL | 29 | 29 | 0 | 0 |

집중 검사는 전체에 포함되는 사례를 재실행한 것으로 합산하지 않는다. 전체 회귀 중 기존 VOC migration 테스트가 과거0008 DB에 미래 policy metadata 테이블까지 조회하는 가정을 발견해, 0008의 기존 테이블을 명시한 뒤 전체 재실행했다. 이 테스트는 기존 데이터 보존 assertion을 그대로 유지한다. 최종 비교 조회를 팀 범위와 단일 SQL로 묶어 존재/비권한404를 같게 한 후 정책 모듈 전체를 양쪽 DB에서 재검증했다.

SQLite skip은 PG전용44+외부 전체 합성 fixture9+Windows DPAPI1이다. PG skip은 fixture9+Windows1이며 정책 동시 append·같은 키 중복 생성·동시 approve/reject 검증은 실행했다. 각 실행에 기존 Starlette/httpx deprecation warning1건이 있다. fixture 원본 Gold 전체 검증 완료를 주장하지 않는다.

정책 생성/부분·제목·무변경/최초 비교, 같은 키 충돌/이전버전 충돌/잘못된 버전쌍, FAQ·응답·규칙 co-use, source drift·잘못된 refs·범위 밖 행 배제, 권한/역할/전체·일부 팀 회수/비활성 계정, 승인·반려·오래된 후보·중복 검토, P0와 기존 P1 행 불변성, schema drift/왕복/손실 방지를 검증했다.

기존 P0 **37경로·41 operation 및 components/security 동일**, 기존 P1 monitoring/VOC **8 operation과 참조 스키마/security 동일** 확인. 최신 handoff/OpenAPI, Ruff check/format(137 files), git diff --check 통과. 처음 신규 검토 모델 이름이 기존 보관 정책 모델과 충돌한 것은 새 PolicyDecision 이름으로 분리했으며 기존 스키마를 바꾸지 않았다.

실제 Uvicorn HTTP + 별도 PG schema에서 health200, 등록201/replay200/버전추가201/비교201/승인200/오래된 검토409/이력200/비인증401/기존 monitoring200 및 P0 원장 불변을 검증했다. [HTTP 증거](evidence/p1-policy-20261104/http-smoke.json). 임시 서버는 종료했고 테스트/smoke schema 잔존0/public table0을 확인했다. [정리 증거](evidence/p1-policy-20261104/cleanup.json).

전체 [SQLite](evidence/p1-policy-20261104/sqlite.xml)·[PostgreSQL](evidence/p1-policy-20261104/postgres.xml), 최종 [정책 SQLite](evidence/p1-policy-20261104/focused-sqlite.xml)·[정책 PostgreSQL](evidence/p1-policy-20261104/focused-postgres.xml). 최종 성공 실행만 저장했고 XML hostname만 제거했다. 중단/초기 실패는 통과 수치에 포함하지 않는다.

## 미연동과 프론트 요구사항

독립 FAQ master 매핑, 규칙 조건의 의미적 의존, Backend B 미래 응답/실제 RAG/Search index, 의미적/법적 정책 판단·운영 부하는 미검증이다. 기존 계약 확인 없이 연결/활성화 완료로 표시하지 않았다. Azure 생성/배포와 프론트 구현은 하지 않았다.

React는 P1 session의 capabilities에서 POLICY_READ/WRITE/REVIEW를 별도 검사하고 현재 allowedTeamIds를 사용한다. 버전 추가에는 GET의 latest_version, 검토에는 GET의 revision/reviewable/candidate_status를 사용한다.409에서는 자동 overwrite하지 말고 최신 상태를 조회한다. 미확인/합성 출처/스캔 제한을 표시하고 승인 배지를 운영 활성화로 표현하지 않는다. diff/정책/이유는 일반 텍스트로 렌더링한다. 계정·팀 변경 시 캐시/진행 요청을 폐기하고 목록·버전·비교 페이지의 cursor를 독립 관리한다. 상세 계약/예시는 [API 문서](p1-policy-api.md)에 있다.

## 실제 변경 파일/Git

기준 HEAD 그대로이며 미커밋/unstaged **14개 수정 + 18개 신규 = 32개 파일**. main/feature/backend-a/feature/backend-b/feature/frontend와 원격 저장소는 수정하지 않았다. [전체 JSON 목록](evidence/p1-policy-20261104/changed-files.json).

| 구분 | 경로 |
|---|---|
| M | `backend/backend-a/.env.example` |
| M | `backend/backend-a/README.md` |
| A | `backend/backend-a/app/extensions/p1/policy_analysis.py` |
| A | `backend/backend-a/app/extensions/p1/policy_models.py` |
| A | `backend/backend-a/app/extensions/p1/policy_router.py` |
| A | `backend/backend-a/app/extensions/p1/policy_schemas.py` |
| A | `backend/backend-a/app/extensions/p1/policy_service.py` |
| M | `backend/backend-a/app/extensions/p1/voc_service.py` |
| M | `backend/backend-a/app/main.py` |
| M | `backend/backend-a/app/schema.py` |
| M | `backend/backend-a/app/seed.py` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/changed-files.json` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/cleanup.json` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/focused-postgres.xml` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/focused-sqlite.xml` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/http-smoke.json` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/postgres.xml` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/sqlite.xml` |
| A | `backend/backend-a/docs/evidence/p1-policy-20261104/summary.json` |
| M | `backend/backend-a/docs/openapi.json` |
| A | `backend/backend-a/docs/p1-before-policy-contract.json` |
| A | `backend/backend-a/docs/p1-policy-api.md` |
| A | `backend/backend-a/docs/p1-policy-implementation-20261104.md` |
| A | `backend/backend-a/migrations/versions/0010_policy_workspace.py` |
| M | `backend/backend-a/tests/p1/test_migrations.py` |
| A | `backend/backend-a/tests/p1/test_policy.py` |
| M | `backend/backend-a/tests/p1/test_voc.py` |
| M | `backend/backend-a/tests/test_analytics_database.py` |
| M | `backend/backend-a/tests/test_phase3_database.py` |
| M | `backend/backend-a/tests/test_repository_layout.py` |
| M | `backend/backend-a/tests/test_workload_postgres.py` |
| M | `docs/P1_TEAM_AND_NEXT_STEP.md` |
