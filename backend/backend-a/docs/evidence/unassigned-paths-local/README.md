# 미배정 의미 보완·공유 전 검증 — 2026-11-04 KST

출발 로컬 HEAD `447c31890c243e1175b805596a84a19720058edf`, feature/backend-a. 작업 시작 시 소스0.7.0/head0007과 기존 Azure/Fabric/업무량 미커밋 변경을 확인했다. 부모·담당 하위 경로에서 AGENTS.md는 발견되지 않았다. 이번 소스는 **0.7.1/head0007**이며 새 migration은 없다.

## 확인한 의미

`unassigned`는 활성 문의에서 현재 유효 상담사 배정이 없는 집합이다. 자동 접수·처리 경로, 실패/재시도/PAUSED인 자동 경로, 명시적인 사람 배정 대기, 이전 회차/무효 배정만 남은 문의를 포함할 수 있다. 유효 배정된 FAILED 문의는 포함하지 않는다. route가 없으면 별도 전역 미라우팅 권한이 있어야 집계된다.

기존 필드·합계를 유지하고 `by_handling_path`만 추가했다. 현재 ticket의 mode·status·resolution_mode로 automatic_path / human_assignment_waiting / unknown을 상호 배타적으로 분류한다. 합계는 total과 같고 invalid_assignment_count는 별도 부분집합이다. job 실패·PAUSED·재시도·reason 문구로 사람 대기를 추측하지 않는다. 자동 경로는 실제 AI 실행 중이라는 뜻이 아니다. B의 작업 생성·상태 전이·배정 코드는 변경하지 않았다. [정확한 조건과 화면 표시명](../../workload.md)을 따른다.

## 이번에 실행한 결과

| 실행 | 결과 | 범위 |
|---|---|---|
| 격리 PostgreSQL 선택 검증 | **113 passed, 실패/skip0** | workload, workload_paths, workload_postgres, staff_queues, ticket_commands, postgres_jobs, azure_deployment, azure_migration. Azure 테스트는 mock/로컬 seed·DPAPI만 사용하고 Azure CLI/네트워크를 호출하지 않음 |
| 추가 혼합 분류·계약 검증 | **7 passed, 실패/skip0** | 혼합 경로 합계·실제 claim/PAUSED·Python HTTP 문구 호환 OpenAPI 비교·엄격 계약 차이 거부. 앞 실행과 중복 사례가 있으므로 합산하지 않음 |
| 정적·계약 | Ruff check/format, git diff --check, 실제 OpenAPI/공개 DTO/엄격 workload schema·응답 예시·분류 합계 검사 PASS | 앱 버전0.7.1, migration graph의 단일 head0007. 전체 업무 suite 실행 아님 |
| Fabric 자료 검토 | 보관0.6.1 소스+문서의 별도 임시 사본에서 offline verifier PASS; 현재 analytics path/schema와 동일 확인 | 실제PG 재추출·Fabric 파이프라인·운영 Export가 아님. 보관 DDL 기준은0006 그대로 |

공통 기존 Starlette/httpx deprecation warning1개. 이번 테스트 결과는 [postgres-results.xml](postgres-results.xml), [contract-results.xml](contract-results.xml), [summary.json](summary.json)에 보존했다. JUnit의 hostname·개인 PC 경로만 치환하고 testcase 결과는 유지했다. **이전0.7.0의164개 PASS는 이번 실행 수치로 사용하지 않았다.**

새 loopback 전용 PostgreSQL16.15와 disposable test schema를 사용했다. 공유·Azure DB에는 연결하지 않았다. 테스트 종료 후 임시 schema가0개임을 확인하고 클러스터를 종료한다. 실제 계정 grant·자동 처리 재개·Azure migration·배포·외부 AI/B/Fabric 연결은 하지 않았다. HTTP 검증은 FastAPI TestClient이며 외부 Uvicorn/Frontend 브라우저 검증이 아니다.

종료 확인: 임시 schema0개와 테스트 전용 클러스터 정상 종료를 실제 확인했다. 전체 공유 diff의 유일한 스타일 예외는 기존 보관 Fabric schema.sql의 EOF 빈 줄1건이다. 추출 bytes/hash를 보존했고 해당 파일을 제외한 staged whitespace 검사는 통과했다. 이 예외를 전체 diff 검사 무경고 PASS로 표현하지 않는다.

## 공유 대상 검토와 보존

기존 Azure 배포·이전 도구는 명시 실행형이며0.6.1/0006 기록을 유지한다. 이번에는 import/단위 테스트만 했고 배포/이전 entrypoint를 실행하지 않았다. 새0.7.1 배포 경로로 검증하지 않았다. Fabric 자료는 과거 snapshot 및 Export 제안으로 구분한다. 업무량의 인증·scope·원문 비노출·snapshot·페이지·카운트는 이번 PG 회귀에서 확인했다.

공유 후보의 알려진 실제 private secret10종, JWT/PAT/private key/credential URI/실제 이메일·개인 PC 경로를 민감값 출력 없이 검사한다. 합성 테스트의 `x:x` 예제 URI와 공개 synthetic HMAC vector는 실제 자격이 아님을 별도로 검토했다. 실제 비밀/DB/환경/cache는 stage 대상에서 제외한다. 설계 문서와 과거 SQLite JUnit의 개인 PC 경로는 공유본에서 치환했고, 원래 bytes는 ignored 로컬 baseline에 보존했다. 값 자체는 보고하지 않는다.

목적별 커밋은 ①기존 Azure 도구·제한·배포 기록 ②Fabric 계약 snapshot ③기존 Git text/eol 규칙 복원과 해시 자료 보존 설정 ④업무량0.7.1·공유 인수/검증 문서로 구분한다. main/OpenAPI의 Azure 부분은 보존해 둔0.6.1 snapshot bytes를 index에만 올려 분리했다. 작업 트리는 되돌리지 않았다. 공유 문서의 Azure/Fabric/업무량 설명이 섞인 부분은 마지막 통합 문서 변경에 실제 포함 범위를 명시한다. 모든 stage 경로는 Backend A 안에서 명시하고 staged diff·secret 검사를 수행한다.

공유 속성 추가 중 기존 .gitattributes 규칙을 덮어쓴 오류는 별도 수정 커밋에서 복원했다. 최종 규칙은 원래6개 규칙 + schema.sql/샘플 JSONL의 -text 예외2개다. Git index에서 실제 체크아웃한 별도 사본에서도0.6.1 Fabric offline verifier가 통과했고 해시 대상 DDL/JSONL bytes가 원본과 일치했다. 앱 동작·migration 변경이 아니다.

원격 조회는 저장소 접근 오류(Repository not found)로 실패했다. 이는 저장소 부재와 현재 인증의 접근권한 부족을 구분할 수 없는 응답이다. 원격이 최신/동일/앞섰다고 단정하지 않는다. 최종 commit hash·push 결과는 Git 기록과 완료 보고를 따른다. 자동 merge/rebase/force push는 하지 않는다. Azure 현재 상태는 재조회하지 않았다.
