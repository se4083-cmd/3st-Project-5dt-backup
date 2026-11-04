# 수동 품질 평가 로컬 검증 (0.9.0 / 0009)

2026-11-04 KST. 시작 상태: feature/backend-a / 968dfe9bd6325e562aa5d31a15aa02b84ddb433a, clean,0.8.0/0008. 적용 경로의 AGENTS.md는 발견되지 않았다. 현재 기능은 [품질 계약](../../quality-review.md)을 따른다. 과거31/54/164/368 등의 PASS를 이번 결과에 합산하지 않는다.

## 실제 실행

| 실행 | 결과 | 파일 |
|---|---|---|
| 최신 신규 QA 기능 | **33 passed / 실패0 / skip0**, 콘솔51.40초 | [quality-latest.xml](quality-latest.xml) |
| 영향받는 기존 PG 회귀 | **222 passed / 실패0 / skip0**, 콘솔346.05초 | [regression.xml](regression.xml) |
| 마지막 QA 팀 표본 판정률 분리 후 관련 지표 재검증 | **6 passed / 실패0 / skip0**, 콘솔8.83초 | [metric-final.xml](metric-final.xml) |
| 마지막 자료 표시 제한 보완 후 관련 재검증 | **5 passed / 실패0 / skip0** | [material-final.xml](material-final.xml) |
| 기존 VOC 보관 사유 코드 호환 최종 재검증 | **2 passed / 실패0 / skip0** | [retention-compatible.xml](retention-compatible.xml) |
| Ruff / 파일 migration graph / 실제 OpenAPI·예시 checker / diff | 최종 정적 검사 PASS. head0009. 업무 테스트/DB 실행과 구분 | summary.json, source hash |

6개와 마지막 자료5개는 기존33개와 일부 겹치므로 합산하지 않는다. 자료5개에는10,000자 초과 정책의 불충분 표시/판정 차단을 추가한1개가 포함된다. 초기 개발 검증에서 새 보관 테스트에 DBAPIError import가 빠져1실패가 발생했다. import를 수정하고 해당1개 재실행 PASS 후 신규33개를 다시 실행해 전부 통과했다. 이전 개발19/31개와 재시도 결과도 합산하지 않는다. TestClient 라이브러리 deprecation warning1개가 각 실행에 있으며 의존성을 변경하지 않았다.

이번 전용 PostgreSQL16.15 클러스터를127.0.0.1에 바인딩하고, 각 테스트마다 임의 test_csflow schema를 생성/제거했다. 기존 다른 클러스터·공유/Azure DB는 사용하지 않았다. 최소 계정/전체 fixture/질문/정책/응답은 **합성**이다. 실제 worker/모델을 실행한 것이 아니다. origin=APPLICATION을 검사하는 fixture도 테스트에서 표식을 재현한 자료일 뿐 실제 운영 품질 증거가 아니다. 테스트 grant는 해당 격리 schema에만 있다. credentials는 ignored local.env에만 저장한다.

## 확인한 핵심

- 기존 AutomaticReply 인자/반환값 호환, MISSING 자료의 실제 final/job/cycle/input/result revision 기록. 명시 질문·suggestion/approval·정책 id/version/hash/model 불일치 거부, policy body hash를 복원할 수 없는 REFERENCES_ONLY 구분.
- 기존 cycle/revision/lease/owner/generation/PAUSED/필수 후속/최종 OUT 유일성 gate 및 성공 원자 확정. provenance 저장 실패를 caller가 잡아도 final/ticket/job/record/evidence가 부분 저장되지 않음. 추가 검증 후 lease/approval 만료 재검사.
- CUSTOMER/AGENT/grant 없는 ADMIN 차단, REVIEW 본인 지정/현재 scope/권한 회수, 다른 reviewer·팀 접근 거부. 종료 티켓의 표본 자료는 가능하고 일반 티켓/직원 상세 접근은 확대되지 않음.
- 미귀속의 별도 명시 권한·QA 책임 팀 지정, 원 ticket 처리 팀 유지, 처리 실적/QA 업무·표본 판정률/전역 미귀속 분리. legacy AUTO 불명은 확정 분모로 backfill하지 않음.
- 같은 key 동일 결과/다른 본문 충돌·중복 표본·경쟁 revision, 선택/REVIEW/REASSIGN/VOID의 receipt 실패 전체 rollback, PG append-only 이력 및 확정 후 evidence 추가 지연 제약 거부.
- 담당 변경 후 기존 REVIEW 유지, 수정은 새 revision, VOID 제외·이력/제외수 유지, rubric별 분리, 빈 분모null, 정책 비적용/미평가/판단 불가 각각 카운트.
- 응답100/평가20(정확15/오류3/불가2)→정확성15/18·coverage20/100·미평가 응답80. 합성 origin 분리, half-open 기간 및 UTC/KST 같은 경계, 현재 snapshot 인증·population·평가·QA 업무 집계 일치, 과거 as_of 요청422.
- 자료 요청 목적 성공/거부 최소 감사, no-store, 알려진 주문번호·이메일·연락처 마스킹, 로그/receipt/집계에 원문·고객 정보 없음. 패턴 마스킹을 완전한 PII 탐지로 주장하지 않는다. 평가 사유는 제한 코드다.
- 0008→0009 기존 메시지·권한 보존과 grant0·legacy reply record0, PG Alembic check 및 CHECK 이름 대조, 빈 downgrade/reapply, 이력 있으면 downgrade 거부. 신규6 QA 보조 테이블을 seed의 공식22개와 구분.
- 보관의 reply/질문/정책/표본·평가·receipt 참조 보호. 보관 테스트만 합성 snapshot 시각을 주입했으며 앱 시각/과거 업무를 만들거나 공유 DB 시간을 변경하지 않음.

관련 회귀는 test_finalization_contract, test_postgres_jobs, test_phase6_postgres, test_voc_improvements, test_voc_postgres, test_workload, test_workload_paths, test_workload_postgres, test_analytics, test_analytics_database, test_retention, test_retention_postgres, test_seed_and_migration, test_repository_layout의222개다. 전체 suite 실행이라고 표현하지 않는다. 마지막6개는 미귀속/100건/VOID/동일 snapshot/기간 경계/rubric·0분모다.

## 보존과 미검증

원래0001–0008 및 B 실행/일반 ticket_scope/고객360/VOC/analytics-v1 주요 소스19개를 공유 HEAD와 대조해 변경 없음을 확인했다. 기존 HTTP path의 OpenAPI 내용도 동일하며 기존 공통 schema 변경은 StaffCapabilities의 additive 권한뿐이다. 최종 응답 writer는 선택 provenance와 같은 transaction의 저장만 확장했다. 이번 소스 hash는 [verified-source-sha256.json](verified-source-sha256.json)에 기록한다.

실제 B·AI/RAG가 선택 자료를 전달하는지, 실제 AI 품질/운영 rubric 합의, Frontend UI, Fabric 품질 mart/전송, Azure/배포/실제 DB·계정, 이 기능 SQLite runtime은 미검증이다. 새 회차 이력·이관/자동 처리율·안전한 자동 완료율·추천·Export는 미구현이다. commit/push/팀 메시지는 하지 않았다. 로컬 합성 데이터 통과를 실제 AI 품질이나 외부 전체 연동 성공으로 표현하지 않는다.

최종 보관 호환 점검에서 기존 VOC 사유 코드 이름을 유지하도록 분리했다. 새 assert는 처음 빈 VOC 테이블에서 사유를 기대해 실패했으므로 합성 VOC 조치를 준비하도록 테스트를 고쳤고 해당 QA/VOC2개를 재실행해 통과했다. 이는 앞 실행과 중복이며 합산하지 않는다.

완료: 임시 schema 잔여0개 확인 후 이번 소유 PostgreSQL 정지. [변경 목록](changes.json), [실행 요약](summary.json), [검증 소스 hash](verified-source-sha256.json)를 보관했다. 변경은 미커밋이며 기존 HEAD/브랜치는 그대로다.

공유 전 후속 검토: 검증 소스 hash15개/현재 파일 및 JUnit/요약 일치를 확인했다. Ruff·실제 OpenAPI/예시·migration 파일 head0009·diff 검사를 재실행했다. 업무 PG 테스트를 다시 실행하거나 과거 결과를 새 실행으로 합산하지 않았다. 이 문서와 summary.commit_push=false는 구현·로컬 검증 당시 기록이며 후속 공유 성공은 Git 원격 HEAD와 완료 보고를 따른다.
