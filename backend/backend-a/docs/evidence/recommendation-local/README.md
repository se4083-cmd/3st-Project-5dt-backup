# 읽기 전용 배정 추천 로컬 검증 — 0.10.0 / 0010

2026-11-04 KST. 아래 구현/실행 기록은 로컬 검증 종료 시점 기준이며, 후속 commit·push 전 검토는 마지막 절에 따로 기록한다. 적용 경로의 AGENTS.md는 발견되지 않았다. 실제 계약은 [추천 API](../../assignment-recommendations.md), 완전한 응답은 [합성 예시](../../examples/assignment-recommendations.json)를 따른다. 소스 byte hash는 [verified-source-sha256.json](verified-source-sha256.json), 현재 변경 경계는 [changes.json](changes.json), 실행별 수치는 [summary.json](summary.json)에 기록했다.

## 두 작업의 경계

1. 시작은 feature/backend-a / 968dfe9bd6325e562aa5d31a15aa02b84ddb433a, 로컬 품질 평가0.9.0/0009 미커밋45파일이었다. 기존 품질 검증 source hash15개와 JUnit5개 기록을 대조했고, Ruff·실제 OpenAPI/예시 checker·Alembic file head·diff·명시 stage 경로·민감정보를 확인했다. 기존33/222/6/5/2는 재실행/합산하지 않았다. 구현 완료 범위와 이전 검증임을 명시한 커밋 **30fbfff047f1d316b73cb33b6cc2b0fb4fe167db**를 일반 push하고 원격 feature/backend-a의 HEAD 일치를 재조회했다. 기존 저장소 전용 인증을 사용했으며 전역 인증 설정을 변경하지 않았다.
2. 그 커밋 뒤 추천0.10.0/0010을 로컬 구현했다. **추천 코드·문서·migration·증빙은 미커밋/미push**다. 기존 품질 증빙은 당시 기록으로 유지하고 새 결과를 덮어쓰지 않는다. 작업 트리 정리/브랜치 전환/커밋 재작성은 하지 않았다.

## 이번 실제 PostgreSQL 실행

전용 PostgreSQL16.15를127.0.0.1에 바인딩하고 테스트마다 임의 test_csflow schema를 생성/제거했다. local_runtime 소유 표식과 loopback URL을 확인했다. fixture·계정·티켓·FAILED Job·직원 부하 모두 합성이며 B 엔진/운영 이력을 재현했다고 주장하지 않는다. SQLite fallback은 없다. 실제 계정에는 권한을 부여하지 않았다. 자격 증명은 ignored local.env에만 있다.

| 실행 | 결과 | 범위 |
|---|---|---|
| [initial.xml](initial.xml) |20 passed, 실패0, skip0|초기 신규 추천/migration|
| [focused.xml](focused.xml) |2 passed, 실패0, skip0|부하/추가 query-bound 및 권한 회수|
| [recommendation-final.xml](recommendation-final.xml) |21 passed, 실패0, skip0|신규 추천 전체|
| [recommendation-reviewed.xml](recommendation-reviewed.xml) |20 passed, **1 failed**, skip0|FAILED Job의 이전 revision 보존/유효 배정 제외 강화 후 점검|
| [migration-reviewed.xml](migration-reviewed.xml) |2 passed, 실패0, skip0|실패 보완 migration 및 기존 phase3 데이터 보존|
| [recommendation-complete.xml](recommendation-complete.xml) |**21 passed, 실패0, skip0**|보완 후 신규 추천 전체|
| [regression.xml](regression.xml) |**350 passed, 실패0, skip0**|이번에 실제 재실행한 영향 범위 기존 회귀|
| [cursor-reviewed.xml](cursor-reviewed.xml) |**2 passed, 실패0, skip0**|마지막 cursor 타입 거부 보완 후 페이지/경계/제한 재검증|

실행끼리 같은 테스트가 겹치므로 합산하지 않는다. 이전 품질 단계33/222 등의 결과를 위 수치에 섞지 않았다. 기존 회귀350개는 이번 실행 결과다. 실패1개는 PostgreSQL 테이블 inventory 반환 순서에 의존한 테스트 비교였으며, 이름을 정렬해 비교하도록 고친 뒤 해당 보존 검증2개와 신규 전체21개를 통과했다. 마지막 소스 검토에서 cursor의 UUID 위치가 문자열이 아닌 변조 입력을422로 거부하도록 보완했다. 이후 관련2개만 다시 실행했고 전체350개를 반복하지 않았다. 각 실행에 기존 TestClient/httpx deprecation warning1개가 있으며 의존성을 변경하지 않았다.

회귀 대상19파일: test_workload.py, test_workload_paths.py, test_workload_postgres.py, test_staff_queues.py, test_staff_internal.py, test_review_fixes.py, test_followups.py, test_followup_handover.py, test_finalization_contract.py, test_quality.py, test_quality_contract.py, test_voc_improvements.py, test_voc_postgres.py, test_analytics.py, test_analytics_database.py, test_seed_and_migration.py, test_retention.py, test_retention_postgres.py, test_repository_layout.py. 별도 migration-reviewed는 test_phase3_database.py의 변경된 head/과거 데이터 보존 사례도 포함한다. 전체 저장소 테스트를 실행한 것은 아니다.

## 확인한 계약

- CUSTOMER/AGENT 차단, ADMIN 명시 capability와 현재 팀 scope, capability/scope 회수. 다른 팀 티켓/후보/건수 비노출. 잘못 grant된 AGENT의 capabilities에서도 숨김.
- HUMAN/HANDOFF_PENDING만 목록 대상. AUTO/종료/배정 후 상태를 사람 대기로 추측하지 않음. FAILED AUTO의 이전 expected version과 현재 ticket version2를 보존한 조회 및 실제 업무4테이블 불변. 유효 배정된 FAILED 문의 제외.
- 이전 회차·무효 물리 배정이 남으면 유효 배정으로 세지 않으며 CONDITIONAL/정리 필요. 읽기가 행을 종료하지 않음. 기존 부분 UNIQUE 유지.
- 활성 AGENT·활성 route 소속 팀·정규화 scope·팀 category 지원. 미분류/미지원/후보 부재/미라우팅 이유. 후보에게 아직 ticket_scope가 없다는 이유로 제외하지 않음. 미라우팅 지정 조회는 추가 UNROUTED_QUEUE_READ, 후보/임의 팀 없음.
- due_at 초과/정확한 마감/2시간 경계/이후·NULL과 페이지/동률 정렬. NULL 검증은 **격리 테스트 schema만** NOT NULL을 잠시 해제했으며 앱 DB 제약/migration은 그대로 유지. route 시각을 대기 시작으로 사용하지 않고 waiting_since=NULL.
- 현재 distinct 문의 업무량/overdue 정렬, WAITING_CUSTOMER 포함·별도 표시, 열린 후속 별도 집계. 고정 UUID 동률 정렬과 여러 문의의 동일 첫 후보 가능성.
- 실제 PostgreSQL REPEATABLE READ에서 중간의 별도 writer가 scope/assignment를 변경해도 현재 응답 목록/후보/부하는 같은 snapshot. 다음 조회에는 회수 반영. 업무3건/1건 비교의 query 수가 N+1로 늘지 않음. 운영 규모 성능 보장은 아님.
- 페이지/후보 제한, 변경된 필터/변조 cursor 거부, 응답 allowlist·원문/고객/주문 비노출·no-store. 30초 만료는 예약/lease/권한이 아님.
- 0010 additive CHECK 전후 기존 업무/grant·테이블 inventory 보존, Alembic check(모델과 차이 없음), downgrade/upgrade, 권한/감사 이력 존재 시 downgrade 거부, readiness0010.

## 정적 점검·보존·제외

Ruff(app/scripts/tests/migrations), 신규 DTO/서비스/테스트/checker5파일 format, 실제 OpenAPI와 DTO 합성 예시, Alembic 단일 head0010, git diff --check를 통과했다. 기존 migration0001–0009 전부 불변, 기존 HTTP50경로 불변, 기존 공통 schema의 변경은 StaffCapabilities additive permission뿐이다. 품질·VOC·analytics·보관·실행·seed 관련 보호 소스23파일은 공유 커밋과 동일하다. 기존 repository 배정 자격 SQL은 후보와 공통 조건만 추출했고 workload facts도 기존 집계 정의를 유지해 재사용했다. 추천 테이블/인덱스/업무 데이터 grant는 추가하지 않았다.

실제 B Worker·Frontend·Azure·Fabric·AI/RAG·Export 및 운영 규모 부하는 미검증이다. 사람 대기 시작/출근/휴가/온라인/숙련도/개인 용량 원천은 없고 고려했다고 표현하지 않는다. 조회는 실제 배정·중복 배정 방지·여러 티켓 동시 부하 균형·PAUSED 실행 권한을 보장하지 않는다. B의 실패/HUMAN 전환/배정 writer는 변경하지 않았다. Azure/공유 DB 접속·배포·실제 권한 부여·팀 메시지 발송은 하지 않았다.

최종 정리에서 이번 작업 소유 PostgreSQL의 임시 테스트 schema가0개임을 확인한 뒤 해당 클러스터를 종료했다. 다른 로컬/외부 DB는 건드리지 않고 ignored runtime/cache 파일은 보존했다.


## 2026-11-04 후속 공유 전 검토

시작 상태는 feature/backend-a / 30fbfff047f1d316b73cb33b6cc2b0fb4fe167db,0.10.0/0010, 이 변경 목록의41파일 미커밋과 같았다. 실제 원격 HEAD도 같은30fbfff였다. 적용 경로의 AGENTS.md는 발견되지 않았다. 검증 source byte hash21개와 JUnit8개를 summary와 대조해 모두 일치했다. 따라서 위21개·350개·마지막2개를 재실행/합산하지 않았고 DB/Worker/Frontend/Azure 통합 검증을 새로 수행하지 않았다.

이번 수정은 인수 문서의 요청3가지 상태/기존 KPI 분모/다음 담당 행동을 구체화하고, 현재 문서의 미커밋 표현을 공유 대상으로 정리한 것뿐이다. 앱·테스트·migration·OpenAPI/합성 응답은 검증 hash와 동일하다. 기존 migration0001–0009, 품질/VOC/analytics/보관/seed/jobs/finalization 보호 소스25개, 기존 HTTP50경로와 StaffCapabilities 외 기존 schema를 비교했다. 실제 읽기 전용 서비스는 assignment/ticket/job/route 쓰기가 없고 최소 조회 감사만 남긴다. 0010은 permission CHECK 추가이며 자동 grant가 없다.

공유 전 Ruff, 추천 관련5파일 format, Alembic 단일 파일 head0010, 실제 OpenAPI/합성 예시 계약 검사, git diff --check와 문서 링크·민감정보/제외 경로·명시 stage diff를 확인한다. 이는 과거 업무 테스트 결과와 구분한 정적 공유 검사다. `summary.json`의 stage_2.committed=false 및 `changes.json`의 recommendation_uncommitted=true는 구현 종료 시점 기록이며 이번 공유 결과는 실제 Git 커밋/원격 HEAD로 판단한다. [현재 인수 현황](../../backend-a-handoff.md)에 운영 rubric·실제 AI 품질, Fabric 효과, B 배정/정식 SLA/운영 효과의 미완료 범위를 정리했다.

최종 staged diff 검사에서 과거 실패 JUnit의 진단 메시지 한 줄 끝 공백을 발견해 공유 XML의 줄 끝 공백만 제거했다. 실패 기록·건수·시각·판정은 유지하며 ignored 원본 XML은 보존했다. 업무 코드/테스트 변경이나 테스트 재실행은 없다.
