# P1 로컬 실행 및 검증

Azure 생성·배포 명령은 없다. 팀 서버나 운영 DB에 이 패키지를 자동 적용하지 않는다. 아래 명령은 Python/Node가 PATH에 있는 PowerShell, 패키지 루트 기준이다. Python >=3.11, Node >=22.12, PostgreSQL이 필요하다. 이번 통합은 Linux/Python 3.12 및 PostgreSQL 17.11에서 검증하며, ZIP의 PostgreSQL 16 과거 결과와 구분한다.

## Backend A

```powershell
cd backend/backend-a
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
# 기존 .env.example을 참고해 .env에 로컬 PostgreSQL DATABASE_URL과
# 무작위 JWT_SECRET, APP_ENV=development, P1_ENABLED=true를 설정한다.
# 실제 비밀값이나 운영 connection string을 공유 파일에 저장하지 않는다.
python -m alembic heads
python -m alembic upgrade head
python -m alembic check
```

head는 0008이다. 신규 권한과 p1_idempotency/p1_tasks/p1_ai_call_attempts를 만든다. P0 테이블 변경은 staff_permissions CHECK 확장뿐이며 자동 grant는 없다. 기존 automation_jobs 스키마·처리 로직은 그대로다. readiness는 P1 비활성 여부와 관계없이 0008을 정확히 요구한다.

기존 로컬 계정을 사용한다. 새 빈 DB에 합성 계정이 필요할 때만 기존 seed 절차(`README.md`, `app.seed`)를 따른다. 계정을 임의 활성화하지 않는다. 활성 ADMIN에 SQL 팀 grant가 이미 있어야 한다.

새 로컬 빈 DB용 선택 절차: .env의 `ENABLE_DEV_SEED=true`와 development 환경을 명시한 뒤 `$env:DEV_SEED_PASSWORD = Read-Host '합성 계정용 비밀번호'`, `python -m app.seed minimal`을 실행한다. 이 비밀번호는 기존 seed가 만드는 `dev-admin@example.test` 등 합성 계정용이다. 실제 운영 계정/비밀번호를 넣지 않는다. seed가 기존 비활성 계정을 활성화하거나 비밀번호를 덮어쓰지 않는다는 원래 규칙을 유지한다.

```powershell
python -m scripts.grant_p1_monitor --login-name dev-admin@example.test
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

grant 도구는 development/test에서만 명시 실행하며 P1_MONITOR_READ 하나만 부여한다. AUTOMATION_READ/STOP/RESUME는 팀의 기존 권한 관리 절차를 사용한다. 권한 없는 제어 블록은 확인 불가로 표시된다. 생산환경 권한 부여 기능을 새로 만든 것이 아니다.

## 프론트엔드 연동

현재 브랜치에는 React 프로젝트를 반입하지 않았다. ZIP의 `frontend/ops-review`를 통째로 복사하지 않는다. 실제 `feature/frontend`의 `frontend/`에 개별 변경을 이식하는 계획은 [통합 보고서](p1-integration-20261104.md)를 따른다. 프론트엔드 빌드/브라우저 검증은 이번 완료 범위에 포함하지 않는다.

## 검증

```powershell
# backend/backend-a
python -m scripts.check_p0_contract
python -m scripts.check_handoff_contract
python -m pytest -q
# 소유한 빈 로컬 테스트 DB만 지정: 각 테스트는 임시 schema를 생성/제거한다.
$env:TEST_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/EMPTY_TEST_DB'
$env:CSFLOW_LOCAL_ONLY='1'
# 전체 합성 fixture가 있으면 원본 경로 지정, 없으면 관련 tests는 skip된다.
# $env:CSFLOW_FIXTURE_DIR='C:\path\to\synthetic-fixture'
python -m pytest --database=postgres -q
```

## 롤백과 후속 단계

P1 테이블에 행이 있거나 P1 권한 grant가 남아 있으면 0008 downgrade는 중단한다. offline downgrade도 금지한다. 기록·권한을 자동 삭제하지 않는다. forward migration을 우선한다. 코드만 기존 0007으로 돌리면 readiness가 새 schema를 거부할 수 있어 코드·DB 호환 절차를 같이 협의해야 한다.

기반 task target UUID에는 아직 VOC/정책 FK가 없다. 생성 API를 추가하기 전에 p1_voc_requests/p1_policy_comparisons와 FK를 추가해야 한다. 공통 worker·lease claim/retry/fencing·idempotency 처리·AI attempt writer도 후속 단계다. 현재 테이블만 준비된 상태를 실제 비동기 엔진으로 취급하지 않는다.

## Linux 명령 대응

저장소 루트에서 `cd backend/backend-a`, `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements-dev.txt`를 실행한다. 위 Python 명령은 `.venv/bin/python`을 사용한다. 기존 환경파일을 덮어쓰지 않는다. 전용 빈 로컬 DB 및 비밀값은 본인의 ignored 환경파일에 구성하고 `CSFLOW_LOCAL_ONLY=1`을 사용한다. 이 통합의 필수 마이그레이션은 기존 0007을 보존하는 **0008**이며 `WORKLOAD_READ`도 유지한다. 시작 후 `/health/live`, `/health/ready`와 인증된 P1 조회를 검사한다. 테스트는 외부 합성 fixture가 없으면 관련 항목을 건너뛴다.
