# VOC 개선 조치·계획 이력 로컬 검증

2026-11-04 KST, source0.8.0 / migration0008. 시작 브랜치 feature/backend-a, HEAD25e4aad720198ea2a3a0287ccf6f58f69c92d228. 기존 미커밋 B 실패/이관 검토 문서를 보존하고 구현했다. AGENTS.md는 적용 경로에서 발견되지 않았다. 이번 결과만 기록하며 과거164/368 등의 PASS를 재사용하지 않는다.

## 실행 환경

PostgreSQL16.15 전용 임시 클러스터를 생성하고127.0.0.1에만 바인딩했다. 모든 테스트는 별도 `test_csflow_<random>` schema를 생성·제거했다. 환경 allowlist 및 local DB guard를 사용하며 공유/Azure DB에는 연결하지 않았다. API 검증은 실제 DB와 FastAPI TestClient를 사용하는 로컬 HTTP 계약 검증이다. 실제 브라우저 UI·AI·B Worker·Fabric 전송 검증은 아니다.

처음 샌드박스의 로컬 TCP 제한과 중지된 임시 서버의 PID 상태를 확인한 뒤, 동일한 로컬 실행 환경에서 소유 클러스터만 시작했다. 테스트 기본 환경에서 분석 서비스 키를 제거하고 외부 합성 fixture 경로를 명시했다. 인증값은 ignored local.env에만 저장하며 문서에 복사하지 않았다. 과거 작업의 기존 클러스터는 사용/변경하지 않았다.

## 실행 결과 — 겹치는 실행을 합산하지 않음

| 실행 | 실제 결과 | 근거 |
|---|---|---|
| 관련 PG 회귀 최초 실행 | **248 passed / 1 failed / 4 skipped**, 335.17초 | [related-initial.xml](related-initial.xml) |
| 최종 VOC 신규 범위 | **31 passed / 0 failed / 0 skipped**, 44.52초 | [voc-final.xml](voc-final.xml) |
| 환경·seed 호환 보완 후 분석/fixture 관련 회귀 | **54 passed / 0 failed / 0 skipped**, 87.69초 | [fixture-final.xml](fixture-final.xml) |
| 정적 검사 | 변경 Python Ruff PASS, Alembic heads=0008, 실제 OpenAPI 재생성·handoff checker PASS, git diff --check PASS | 아래 설명·summary.json |

최초 회귀의1실패는 기본 분석 서비스 키가 설정된 테스트 환경 때문에 disabled-auth 테스트가 기대한503 대신401을 반환한 것이다. 앱 인증을 약화하지 않고 테스트 환경 키를 제거했으며 해당 전체 analytics 파일을 재검증했다.4skip은 fixture 경로 누락이었으며 후속 실행에서 경로를 지정했다. 추가 실행에서 새5테이블이 기존22개 공식 fixture 테이블 집합 비교에 포함되는 실제 호환 결함을 발견해 `app/seed.py`의 보조 테이블 제외 목록을 보완했다. 원본 fixture는 변경하지 않았다. 최종54개에는 위 실패와4개 fixture 사례 및 기존 전체 적재/재적재·rollback·접수가 포함되어 모두 통과했다. 남은 미해결 실패/skip은 없다. 전체 suite를 새로 통과했다고 표현하지 않는다.

개발 중에는 상세 PlanView의 내부 action_id 포함, 합성 게시 자료의 최신성/watermark, 보관 테스트의 미래 시각, 신규 테스트 import 누락도 발견했다. DTO를 수정하고 합성 자료/테스트 시각·import를 바로잡았다. 해당 사례는 최종31/54개 또는 관련 회귀에서 재검증했다. 개발 실패를 PASS 수에 합산하지 않았다. 공통 TestClient 라이브러리 deprecation warning1개는 각 실행에 표시되며 의존성을 변경하지 않았다.

## 검증 범위

- CUSTOMER/AGENT/grant 없는 ADMIN 차단, AGENT에게 테스트 grant가 있어도 상품 권한 확대 안 됨, ADMIN 현재 scope·capability 회수 및 재요청 재검사.
- 신규 후속+profile+첫 계획/팀+감사+VOC receipt 원자성, 기존 일반 상품 후속 등록·중복 거부·티켓 후속 거부, 기존 FOLLOWUP_CREATE receipt 중복 생성 없음.
- 같은 key 동일 결과/다른 내용409, action/plan revision 충돌, 서로 다른 ADMIN 동시 계획 수정201/409, 동일 사용자 동시 생성201/200.
- 시행일 NULL/미래 거부, 누락·불일치·역전·겹침 창과 naive 시각 거부, UTC/KST 동일 경계, 양쪽14일 예시, after_end 미래여도 metrics=null.
- 불변 계획·비교 팀·receipt의 PG UPDATE/DELETE 거부, 계획 receipt 저장 뒤 비교 팀 추가 INSERT도 거부. 종료 후 사유 없는 정정 거부·시행 사실 정정은 새 plan만 추가하며 기존 후속 revision/상태 보존.
- 담당 ADMIN 제한·미인수의 DONE 거부, 기존 후속 담당/상태/필수 후속/인수 회귀.
- 양쪽 권한·동일 상품 연결, NULL/다른 상품/범위 밖 티켓 거부, 이후 권한 밖 연결 ID/개수 미노출, source 미게시/잘못된 exact scope 거부·과거 게시 고정 유지, 담당 팀 변경 후 과거 계획 숨김과 refresh.
- 목록/이력 안정 페이지·크기 제한, 원문·고객/주문 정보 미반환, 효과 availability=UNAVAILABLE/EFFECT_INTEGRATION_NOT_IMPLEMENTED 및 null.
- 보관 dry-run의 새 문의·상품 후속·배치 참조 보호, VOC workflow history 보호 및 TEAM 전체 이력 null/unsupported. 보관의 오래된 데이터 사례는 테스트에만 합성 snapshot 시각을 주입했고 앱의 미래 시각 거부 규칙은 유지했다.
- 0007→0008 기존 업무/권한 데이터 보존·grant 자동 생성0, 빈0008 downgrade/reapply, history가 있으면 downgrade 거부, 실제 PG Alembic check로 테이블/컬럼/타입/FK/인덱스 대조, readiness0008.
- 업무량 snapshot/페이지/합계·경로 분류, 성공 응답 확정 fencing/동시성, 기존 분석 게시·권한·Gold 불변 계약 회귀.

관련 최초 회귀 파일: test_voc_improvements, test_voc_postgres, test_followups, test_followup_handover, test_phase3_database, test_analytics, test_analytics_database, test_retention, test_retention_postgres, test_workload, test_workload_paths, test_workload_postgres, test_finalization_contract, test_repository_layout. 최종54개는 test_analytics 전체 + test_analytics_database의 populated fixture upgrade + test_retention의 global fixture inventory + test_seed_and_migration 전체다.

OpenAPI와 Frontend 예시는 실제 모델/경로·bearer·닫힌 allowlist·null 효과 schema를 checker로 확인했다. 원래0001–0007 migration과 기존 B 검토 문서는 SHA256으로 변경 없음, 담당 폴더 밖 변경 없음 확인. 앱의 B 재시도·실패·HUMAN 전환·배정 로직은 변경하지 않았다.

## 미검증·남은 연동

실제 Azure 상태·배포/migration 적용·실제 계정 grant·Fabric 효과 결과·Export·B Worker·Frontend 화면/브라우저 연결·새 기능 SQLite runtime은 미검증이다. 문의 cohort/분모·기간·일별 집계 경계·상품 식별·고정 scope는 주현님과 합의해야 한다. 로컬 계약 통과를 분석 효과나 외부 전체 연동 성공으로 표현하지 않는다. commit/push/팀 메시지 발송도 하지 않았다.

완료 시 임시 test schema 잔여0개를 확인하고 소유 VOC PostgreSQL을 정지했다. [기존/이번 변경 구분](changes-from-baseline.json)과 [요약](summary.json)을 함께 보관한다.


## 공유 전 검토 — 별도 실행 기록

후속 commit/push 요청에서 브랜치/HEAD/dirty와0.8.0/0008, 모델·API·권한·멱등/원자 경계·이력/보관·seed 변경, manifest 및 JUnit/summary 일치를 재검토했다. Ruff, Alembic heads(파일 graph), 실제 OpenAPI/예시 checker, git diff --check를 다시 실행해 통과했다. 기존0001–0007 및 B 실행/analytics-v1 소스15개가 공유 HEAD와 같은지 대조했다. 이 단계는 DB를 열거나 업무 테스트31/54개를 다시 실행한 결과가 아니다. 위 테스트 수를 새 실행/전체 통과로 재사용하지 않는다.

공유 파일의 민감정보 패턴과 파일 경로를 검사했다. 과거 verification.md의 DB URL 탐지는 기존 HEAD에도 있던 loopback 설명용 placeholder로 확인했다. 실제 접속 값은 포함하지 않는다. JUnit의 개인 PC 경로 prefix는 PROJECT_ROOT 표식으로 치환했으며 시험 이름·판정·수량·시간과 실패 설명은 보존했다. 기존 B 검토 문서는0.7.1 당시 검토/미구현 제안의 원문을 유지하며 VOC와 별도 문서 커밋 대상으로 구분한다. 이 문서의 앞 절과 summary.commit_push=false는 **구현·로컬 검증 단계 당시** 기록이고, 후속 공유의 성공 여부는 실제 Git 원격 HEAD 확인 및 완료 보고를 따른다. Azure/실계정/실제 Fabric·Frontend 연동은 이번에도 미확인·미변경이다.
