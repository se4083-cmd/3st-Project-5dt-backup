# 업무량 조회 로컬 검증 — 2026-11-04 KST

로컬 소스 **0.7.0 / Alembic head0007**, 브랜치 feature/backend-a, 출발 HEAD `447c31890c243e1175b805596a84a19720058edf` 위 미커밋 변경이다. commit/push/브랜치 전환은 하지 않았다. [실제 API 계약](../../workload.md), [설계 진행 상태](../../quality-voc-workload-design.md), [요약 JSON](summary.json)을 함께 본다.

## 실제 실행 결과

| 실행 | 결과 | 해석 |
|---|---|---|
| SQLite 관련 검증 | **59 passed / 2 skipped / 0 failed** | 신규 업무량 + 기존 후속/인수·큐. skip2는 PG 전용 사례이며 PG 증거의 대체가 아님. [JUnit](sqlite-related.xml) |
| 초기 PG 신규 검증 | 19 passed / skip0 | 업무량·snapshot·migration의 중간 실행. 최종 수치에 더하지 않음 |
| 확장 PG 선택 회귀 | 163 passed / 1 failed / skip0 | 164개 사례 중 생성 OpenAPI가 아직 갱신되기 전 계약 비교1개 실패. [최초 기록](postgres-regression-initial.xml) |
| OpenAPI 재생성 후 관련 PG 재검증 | **60 passed / 0 failed / skip0** | 업무량22개 + 직접 관련 review-fixes38개. 최초 실패 사례 포함. [최종 기록](postgres-final.xml) |
| PG 사례별 최종 상태 | **164개 고유 사례 모두 PASS** | 위 선택 회귀와 재검증의 `(classname,name)`별 마지막 결과. 164+60을 합산한 건수가 아님. summary.json에 중복 제거 결과 보존 |
| 로컬 정적·계약 | Ruff check PASS, format91파일 PASS, git diff --check PASS, 실제 OpenAPI 동일성/공개 DTO/폐쇄된 업무량 DTO/JSON 예시/기존 canonical 검사 PASS | 앱/실서비스 기동이나 AI/Fabric 통합 증거가 아님 |

공통 경고1개는 기존 Starlette/httpx deprecation이다. 의존성은 변경하지 않았다. JUnit의 PC hostname 속성을 제거했고, 후속 팀 공유 검토에서 SQLite 경고의 개인 PC 경로 prefix도 치환했다. 공유 전 whitespace 검사에 맞춰 최초 실패 진단 메시지의 후행 공백도 정리했고 testcase 결과는 유지했다. 원래 bytes는 비공개 로컬 baseline에 보존했고 최초 실패 기록은 삭제하지 않았다.

초기 환경 문제: 기본 pytest temp 디렉터리 생성 실패 후 프로젝트 안의 새 전용 basetemp를 지정했다. 샌드박스의 loopback 차단으로 최초 PG 접근/일부 TestClient 실행이 진행되지 않아, 같은 PC의 별도 실행 환경에서 새 loopback 전용 빈 클러스터를 만들고 테스트별 disposable schema를 사용했다. 테스트 helper의 필수 blocks_resolution 누락은 합성 fixture를 수정한 뒤 관련 사례를 다시 실행해 통과했다. 이후 OpenAPI 파일을 생성하고 실패했던 비교 및 관련 계약 검증60개를 다시 통과했다. 환경 실패·중간 실패를 성공에 합산하지 않는다.

## 환경과 격리

- 기존 `.venv-phase5` 및 이미 설치된 PostgreSQL **16.15** 바이너리만 사용. 설치/의존성 변경 없음.
- 새 DB `workload_test`, 127.0.0.1만 listen, 동적으로 선택한 전용 포트. `CSFLOW_LOCAL_ONLY=1`, 매 테스트 `test_csflow_<uuid>` schema 생성·해제.
- 공유·Azure·기존 demo DB URL은 사용하지 않음. 실제 계정 grant 없음. 권한은 합성 테스트 fixture에만 부여.
- 테스트 완료 후 `test_csflow_%` 잔존 schema **0개**, 전용 PG 클러스터 **정상 종료** 확인. 기존 데이터 폴더/복구 백업 삭제 없음.
- API 검증은 FastAPI TestClient + 실제 격리 PostgreSQL이다. 별도 Uvicorn 네트워크 HTTP·Frontend 브라우저·B worker·AI/RAG·Fabric·Azure 배포/부하 검증은 하지 않음.

재현은 **새 격리 로컬 PG URL만** 사용하며 아래 파일 목록으로 선택 실행했다. 출력/로그에 실제 비밀번호·JWT·DB 접속 문자열을 넣지 않는다.

```text
tests/test_workload.py
tests/test_workload_postgres.py
tests/test_followups.py
tests/test_followup_handover.py
tests/test_staff_queues.py
tests/test_staff_internal.py
tests/test_review_fixes.py
tests/test_phase3_database.py
tests/test_repository_layout.py
tests/test_automation_control.py
tests/test_finalization_contract.py
tests/test_postgres_jobs.py
tests/test_analytics_database.py::test_readiness_requires_new_revision
```

최종 재검증은 위 중 workload 두 파일과 test_review_fixes.py만 실행했다. 같은 범위 전체164개를 다시 실행한 것으로 표현하지 않는다. 전체 업무 pytest suite는 실행하지 않았다.

## 검증한 핵심

- CUSTOMER403, AGENT 본인만(grant 불필요)/타인403/팀 대기 비공개, ADMIN WORKLOAD_READ 필수 및 현재 팀 scope. 직원 범위 밖/없음 모두404, 팀 범위 밖/없음 모두403.
- 현재 cycle·활성 직원/팀·scope/category·stage·assigned_at의 유효 배정. 과거/종료/중복 이력 제외, FAILED 유효 배정의 미배정 제외, WAITING_CUSTOMER 분리.
- 실제 저장 기한의 초과/정확한 마감/2시간 경계/정상과 후속NULL. SQL 공통 분류기의 문의NULL 지원도 확인. 문의 NOT NULL 제약 유지, 조회 전후 기한/version 불변.
- route별 허용 팀 미배정, 무효 미종료 배정은 부분집합, 기존 전용 권한의 전역 미라우팅 별도 집계.
- 후속 유효 담당/인수 cycle, 비활성·scope 회수·category 불일치, ADMIN 상품 후속, 팀 대기 및 별도 기한.
- 단일 snapshot 중 다른 connection에서 배정 종료·조회자 scope 회수 commit 후에도 같은 응답의 인증·문의·후속·카운트는 이전 일관 상태, 다음 요청은 회수 반영.
- UUID ASC keyset 페이지, scope/page 합계 분리·빈 집합, cursor 타입·필터/권한 변경 검증, 페이지 크기와 무관한 SQL query 수, raw/customer/order 필드 미노출, 감사 실패 시 부분 응답 없음.
- 0006→0007의 업무 행/기존 grant 보존·새 grant0, 모델/Alembic check, 무이력 downgrade/re-upgrade, grant 또는 READ_WORKLOAD 이력 시 downgrade 거부, readiness0007.

## 이번 변경과 기존 미커밋 변경 구분

검토 시작 시 기존 tracked 수정13개, untracked status 항목15개(설계 문서 포함)가 있었다. 담당 폴더의 tracked/비ignored untracked **227개 파일**을 별도 로컬 baseline으로 확보했다. 기존 파일 삭제0개. 기존 migration0001–0006과 Fabric 자료, Azure 도구·증거·startup 변경은 원래 bytes 그대로 보존했다. 전체 원격 최신 여부를 새로 확인하거나 Azure에 접속하지 않았다.

새 파일:

- `app/workload.py`, `app/workload_schemas.py`
- `migrations/versions/0007_workload_read_permission.py`
- `tests/test_workload.py`, `tests/test_workload_postgres.py`
- `docs/workload.md`, `docs/examples/workload-response.json`, 이 evidence 디렉터리

이번에 기존 파일을 추가 수정:

- 런타임/권한: `app/repository.py`(호환 as_of 주입), `app/followups.py`(기존 소유권의 공유 SQL 술어), `app/staff_models.py`, `app/staff_router.py`.
- 버전/readiness: `app/main.py`, `pyproject.toml`.
- 계약/문서: `README.md`, `docs/api-contract.md`, `docs/frontend-handoff.md`, `docs/openapi.json`, `docs/examples/frontend-requests.json`, `docs/quality-voc-workload-design.md`, `docs/verification.md`, `scripts/check_handoff_contract.py`.
- 기존 테스트의 현재 head 기대값: `tests/test_repository_layout.py`, `tests/test_phase3_database.py`, `tests/test_analytics_database.py`.

이 중 README/main/API/Frontend/OpenAPI/verification/설계 문서는 **기존 미커밋 내용 위에 추가 수정**했다. 기존 PublicLimits/HSTS/429와 Azure/Fabric 인수 내용은 유지했다. Git HEAD에 대한 diff 전체를 이번 변경이라고 오해하지 않는다. [baseline 대비 변경 목록](changes-from-baseline.json)은 이번 수정 파일만 구분한다.

## 남은 연동

Frontend는 업무량 API만 연결할 수 있고 기존 배정/고객 DTO는 그대로다. 실제 배포/0007 migration 적용·ADMIN WORKLOAD_READ 부여·Frontend origin 설정은 이번에 하지 않았다. B 배정 실행·추천·새 SLA 엔진·AI 품질·VOC 개선·analytics-v2·Export는 미구현이다. 특히 기존 Azure 배포/이전 도구는 고정0.6.1/0006용 기록을 유지하므로 새 버전에 바로 실행하는 배포 경로로 검증되지 않았다.
