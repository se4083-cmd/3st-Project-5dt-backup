# GitHub 저장소 통합·검증 기록

대상은 InSSOOO/cs-flow-ai의 feature/backend-a, 담당 경로는 backend/backend-a/다. main의 backend/README.md만 있는 초기 구조와 feature/backend-b를 확인해 별도 leaf를 선택했다. main/Backend B/Frontend/AI/Fabric/공유 파일을 이동·수정하지 않는다. 원본 개발 폴더의 uncommitted Git/remote를 변경하지 않고 별도 clone에서 통합했다. 검토 ZIP0.6.0은 사용하지 않았다.

## 반입 변경과 제외

앱0.6.1 및 migration0001–0006의 기능 로직을 반입했다. Alembic prepend_sys_path를 %(here)s로 바꿔 루트의 -c 호출에도 app import가 올바르게 잡히게 했고 ROOT 기반 scripts/seed/fixture 경로를 검증했다. 상대경로 명령은 README에서 저장소 루트/담당 폴더 기준을 구분했다. 개인 PC 경로와 hostname을 제거하고 테스트용 고정 자격 상수는 REVIEW_* placeholder로 치환했다(실행 비밀값 아님). 원본은 변경하지 않았다. 새 경로 회귀 tests/test_repository_layout.py를 추가했고 새 업무 기능/API는 추가하지 않았다.

가상환경/실제.env·local.env·키/토큰/DB/binary/캐시/PID/원시 로그/ZIP/원천 데이터/전체fixture/원본821명 로그인 자격정보는 반입하지 않았다. app.seed의 최소 합성 자료와 작은 LOCAL_SYNTHETIC 분석/요청·해시 예시만 제공한다. 전체 fixture는 로컬에서만 별도 준비하며 reference/README.md에 조건/skip을 명시했다. root .github/workflows는 복사하지 않았으며 원격 workflow 조회 결과0개였다. 배포·Actions·외부 엔진은 실행하지 않는다.

## 기존 최종 결과 (이번 새 실행과 구분)

0.6.1 원본의 전체 PostgreSQL368 passed/실패·skip0, 실제 HTTP33개 흐름 PASS는 기존 최종 검증 기록이다. docs/evidence/local-0.6.1에 그 복사본을 넣었고 원시 로그/PC hostname은 제외했다. 이번 소스 이동 이후 전체368개와33개 HTTP 흐름은 다시 실행하지 않았다. 테스트 placeholder/Alembic 경로/문서/레이아웃 테스트 추가가 있는 통합본에 새 전체 통과를 주장하지 않는다.

## 이번에 새로 실행한 부분 검증

| 검사 | 결과 |
|---|---|
| Python import/ROOT·CWD 독립 Alembic 경로/기존 review-fix·설정·local guard·minimal seed 관련 SQLite 부분 | **61 passed / 4 skipped**, 실패0. PG lock1개+전체 fixture 미제공3개 skip |
| 실제 로컬 PostgreSQL 경로·기존fixture적재/재적재·업그레이드/복구 관련 부분 | **4 passed**, 실패/skip0. 이미 가진 합성 자료를 로컬 읽기만 했고 데이터는 커밋하지 않음 |
| 저장소 루트 alembic -c backend/backend-a/alembic.ini current | **0006**, 명시된 검증 환경 사용 |
| 이동된 실제127.0.0.1 Uvicorn health live/ready | **200/200**, 생성 OpenAPI 전체 동일 |
| Ruff check/format --check | **PASS**, Python93개 파일 |
| 엄격 OpenAPI/인수 요청·공개 DTO/canonical hash vectors | **PASS** |

이번 부분 결과는 서로 다른 검증 범위이며 기존368개나33개에 합산하지 않는다. 증거는 evidence/repository-integration의 partial-sqlite.xml/path-postgres.xml/summary.json이다. XML에는 개인 PC hostname/절대경로를 제거했으며 결과 수치/실행 시각은 보존했다. 기존 Starlette/httpx deprecation warning1건이 있었다. Linux/Python3.12 실제 재검증은 이번에도 하지 않았다.

경로 검증용 클러스터/서버는 정상 종료해 비활성화했으며 데이터는 ignored .cache에 보존했다. 원격DB/클라우드·외부 모델/RAG/Fabric/발송은 검증에 사용하지 않았다. GitHub에는 source/작은 예시/검증 summary만 올린다. workflow 추가/활성화·PR·리뷰 요청·main 병합은 하지 않는다.
