# CS Flow AI Backend A

**2026-11-04 실제 Azure 배포 확인: 0.11.0 / DB0011**, 고정 source6460230. [배포·권한 미설정·외부 연동 제한](docs/evidence/monitor-effects-local/README.md), [Frontend 연결](docs/frontend-handoff.md). 직원 신규 grant0·CORS=[]·서비스 subject0·PAUSED 유지입니다.

0.11.0 / migration0011: [AUTO 회차 진단과 VOC 효과 수신/검증/게시/조회](docs/monitoring-effects.md)를 추가했습니다. 기존 업무량/추천은 조회 전용으로 유지합니다. 새 회차는 전향적 부분 기록이며 운영 안전 완료율은 UNAVAILABLE, 실제 B/Fabric 연동·운영 효과는 별도 검증 대상입니다. 이번 배포 결과는 담당 증거 문서에 기록합니다.

**0.10.0 / migration0010 (공유 대상, Azure 이번 미확인·미변경)**: [읽기 전용 배정 우선순위 추천](docs/assignment-recommendations.md)을 추가했습니다. 먼저 품질0.9.0은30fbfff로 공유했습니다. 추천은 현재 업무량 힌트이며 실제 배정·예약·B 실행 변경은 없습니다.


**이전 공유 기준 0.9.0 / migration0009**: [수동 품질 평가](docs/quality-review.md)를 추가했습니다. 실제 자동 확정 응답의 선택 근거 기록, 제한된 표본 자료, append-only 평가, 현재 snapshot 지표를 제공합니다. 실제 AI 품질·외부 연동의 성공을 뜻하지 않습니다. 기존 VOC/업무량/analytics-v1 및 B 실행 책임은 유지합니다.


**이전 로컬 단계 0.8.0 / migration0008**: [VOC 상품 개선 조치·계획 이력](docs/voc-improvements.md)을 구현했습니다. 기존 상품 후속의 담당/상태/기한을 재사용하며 효과 분석은 미구현/null입니다. ADMIN+VOC_IMPROVEMENT_MANAGE와 현재 팀 scope가 필요합니다. 실제 권한 부여·Azure·commit/push는 수행하지 않았습니다.


**이전 공유 기준 0.7.1 / migration0007**. 기존 Backend A 기능에 [현재 상담사 업무량 조회](docs/workload.md)를 추가했다. 0.7.1에서는 ‘유효 상담사 배정 없음’을 자동 경로/사람 배정 대기/판별 불가로 나눠 표시한다. AGENT 본인/명시 권한 ADMIN의 업무량·미배정·기한·후속 집계를 제공한다. 자동 배정/추천·새 SLA 엔진은 없다. Azure 배포는 이번에 변경하지 않았으며 기존 0.6.1/0006 기록과 구분한다. Backend B의 worker·배정/사람 응답 엔진이나 AI/RAG/Fabric 계산·외부 발송기는 포함하지 않는다.

이 구현은 `backend/backend-a/` 안에 독립적으로 둔다. 기존 `backend/README.md`, 팀 루트/공유 설정과 Backend B·Frontend·AI·Fabric 코드는 변경하지 않는다. 실제 비밀값/개발 DB/검토 ZIP/다운로드 원천·전체 fixture/배포 workflow는 올리지 않는다.

## 검증 기록의 구분

- **원본0.6.1의 기존 최종 검증:** Windows/Python3.13.15/PostgreSQL16.15 전체368 passed(실패/skip0), 실제 Uvicorn HTTP33개 흐름. 이번 Git 통합에서 다시 실행한 수치가 아니다.
- `docs/evidence/local-0.6.1/`는 그 기존 JUnit·HTTP·요약을 복사한 것이다. JUnit의 PC hostname만 제거했다. 원시 로그/실행 비밀값은 없다.
- 반입 시 개인 PC 경로와 테스트 전용 고정 자격값을 portable 문서/`REVIEW_*` placeholder로 바꾸고 Alembic 경로를 ini 기준으로 지정했다. 새로 실행한 부분 검증은 [저장소 통합 기록](docs/repository-integration.md)에 별도로 기록한다. 기존368개와 합산하거나 업로드본의 새 전체 통과로 표현하지 않는다.
- 실제 Linux/Python3.12 전체 재검증·실제 B/AI/RAG/Fabric/Frontend/발송·클라우드 배포·운영 부하/법적 준수는 미검증이다. HTTP413/422 문구 차이는 명시 고정했고 실제 schema/security 전체 비교는 유지한다.

## 작업 위치와 의존성

아래 Python module 명령은 **Backend A 폴더 안**에서 실행한다. `app`/`scripts` namespace와 환경파일을 다른 담당자의 환경과 섞지 않는다. Python3.11+ 지원 선언, 기존 검증 환경은3.13.15이며 고정 requirements를 사용한다.

저장소 루트에서 시작하는 PowerShell:

```powershell
Push-Location backend/backend-a
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
# 아래 모든 module 명령을 이 위치에서 실행
Pop-Location
```

Backend A 폴더에서 시작하는 경우 `Push-Location backend/backend-a`/`Pop-Location`을 생략한다. Linux Python 경로는 `.venv/bin/python`이다. 전체 루트에서 직접 `python -m app...`을 실행하지 않는다. Alembic의 script_location/prepend_sys_path는 ini 위치 기준이지만 설정/fixture/private state는 이 폴더를 기준으로 사용한다.

## 원본 전체 fixture 없이 가능한 작업

app.seed.seed_minimal과 tests의 생성 fixture가 개발 고객2명/상담사/관리자·합성 주문·작은 분석 샘플을 만든다. docs/examples/analytics-batch.json은 LOCAL_SYNTHETIC 분석 계약 예시이며 고객/티켓/상담 원문이 없다. 전체 데이터는 Git에 포함하지 않는다. 기본 pytest는 전체 fixture가 필요한 테스트를 명시적으로 skip한다.

```powershell
.venv/Scripts/python.exe -m scripts.check_handoff_contract
.venv/Scripts/python.exe -m ruff check app migrations scripts tests
.venv/Scripts/python.exe -m ruff format --check app migrations scripts tests
# 기본 SQLite 보조 검증. PostgreSQL/전체 fixture 성공의 대체가 아님
.venv/Scripts/python.exe -m pytest -q
```

최소 API는 **별도로 준비한 빈 로컬 PostgreSQL**을 사용한다. scripts/configure_local은 새 ignored .env만 만들며 기존 파일을 덮어쓰지 않는다. .env에서 DATABASE_URL/POSTGRES_PASSWORD를 자신의127.0.0.1·명시 포트·전용 DB에 맞춰 로컬 편집하고 sslmode=disable을 사용한다. 비밀번호/키는 출력·공유하지 않는다. 기존 개발 DB나 원격 주소를 사용하지 않는다.

```powershell
.venv/Scripts/python.exe -m scripts.configure_local
$env:CSFLOW_LOCAL_ONLY = '1'
$env:CSFLOW_ENV_FILE = (Resolve-Path .env).Path
.venv/Scripts/python.exe -m alembic upgrade head
$env:ENABLE_DEV_SEED = 'true'
$env:DEV_SEED_PASSWORD = Read-Host -MaskInput '개발 계정 비밀번호 12자 이상'
.venv/Scripts/python.exe -m app.seed minimal
Remove-Item Env:DEV_SEED_PASSWORD
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

foreground API는 Ctrl+C로 종료한다. 이 수동 방식의 DB 종료는 자신이 준비한 로컬 DB의 절차를 따른다. 아래 소유 클러스터 방식의 stop/clean을 임의의 수동/개발 DB에 적용하지 않는다. 새 권한/배정/자동 답변은 기본 seed에서 자동으로 생기지 않는다.

## 전체 fixture가 별도로 승인·준비된 경우

[fixture 준비와 skip 범위](reference/README.md)를 먼저 읽는다. 외부 서비스에 접속하거나 원천 데이터/계정을 다운로드·활성화하지 않는다. 승인받아 가진 **합성** 전달본을 별도 로컬 폴더에 준비하고 --fixture-dir로 지정한다. 이 저장소에 복사/커밋하지 않는다.

```powershell
$PgBin = '<자신의 로컬 PostgreSQL bin 경로>'
$FixtureDir = '<사용 권한을 확인한 합성 fixture 폴더>'
.venv/Scripts/python.exe -m scripts.local_runtime init --pg-bin $PgBin --fixture-dir $FixtureDir --state-dir .cache/demo-local --api-port 8000
.venv/Scripts/python.exe -m scripts.local_runtime start-api --state-dir .cache/demo-local
.venv/Scripts/python.exe -m scripts.local_runtime test --state-dir .cache/demo-local
.venv/Scripts/python.exe -m scripts.local_runtime verify --state-dir .cache/demo-local
```

루트 기준으로 실행할 때는 위 블록 전체를 `Push-Location backend/backend-a`/`Pop-Location`으로 감싼다. init은 새로운 state·소유 표식·별도 임시 PostgreSQL 클러스터만 생성한다. API/DB는127.0.0.1, 연결 전 guard/격리 환경을 사용한다.8000 사용 중이면 --api-port 생략으로 빈 loopback 포트를 배정한다. 전체 fixture 없이는 이 init/test/verify의 전체 원본 대조를 성공으로 보고할 수 없다.

기본 fixture 경로는 `backend/backend-a/reference/fixture`지만 커밋 대상이 아니다. pytest만 별도 경로를 쓸 때는 `$env:CSFLOW_FIXTURE_DIR=$FixtureDir`을 사용한다. local_runtime은 state 안의 지정 경로를 사용한다. 원본821개 합성 계정의 로그인 불가 표식을 유지하며 활성화하지 않는다.

## Swagger와 역할별 체험

Swagger http://127.0.0.1:8000/docs, /health/live와 /health/ready. dev-customer1@example.test/dev-customer2@example.test/dev-agent@example.test/dev-admin@example.test만 minimal seed 로그인 대상이다. 수동 seed에서는 자신이 지정한 비밀번호, local_runtime에서는 ignored .cache/demo-local/local.env의 DEV_SEED_PASSWORD를 로컬에서 확인한다. 토큰/비밀번호를 로그·메신저·Git에 넣지 않는다.

1. 고객: login→HTTPBearer Authorize→orders→티켓 접수/멱등 재시도→재문의·사람 연결. 고객2는 고객1 티켓404.
2. 직원: 현재 유효 배정·팀/category 안의 티켓/후속/고객360. 내부 상세는 별도 POST/purpose와 nested allowlist. 배정은 B가 없으면 저절로 생기지 않는다.
3. 관리자: 현재 허용 팀 후속/분석. 서비스 JWT 없는 일반 관리자 게시 거부. 미게시/LOW_SAMPLE/stale/unavailable을 그대로 표시한다.
4. 큐/중지/보관 검토는 역할만으로 열리지 않는다. 명시 capability·route/팀·purpose가 필요하며 기본 계정에 자동 grant하지 않는다. UNROUTED/GLOBAL은 별도 명시 권한이다.

verify는 별도 임시 schema의 테스트 권한/고정 답변·배정·사람 gate 뒤 writer·LOCAL_SYNTHETIC 분석으로 흐름을 검증한다. 체험 root DB에 결과를 남기지 않는다. 실제 B/AI/Fabric/발송 엔진 성공이 아니다. 분석 게시도 로컬 current 교체뿐이다. 보관은 집계/최소 감사뿐인 dry-run이며 실삭제 endpoint·SQL 생성·예약은 없다.

## 소유 클러스터 종료와 정리

```powershell
# API/DB 정지, 데이터/계정/비밀번호 보존
.venv/Scripts/python.exe -m scripts.local_runtime stop --state-dir .cache/demo-local
# 나중에 재시작
.venv/Scripts/python.exe -m scripts.local_runtime start-db --state-dir .cache/demo-local
.venv/Scripts/python.exe -m scripts.local_runtime start-api --state-dir .cache/demo-local
# 검토가 완전히 끝났을 때만 소유 임시 DB/자격파일 제거, 보고서는 보존
.venv/Scripts/python.exe -m scripts.local_runtime clean --state-dir .cache/demo-local
```

## 계약·변경 내역

- [A 완료/미검증](docs/backend-a-handoff.md), [기존 최종 검증](docs/verification.md), [이번 반입 검증](docs/repository-integration.md)
- [0.6.1 결함 수정](docs/review-fixes.md), [API](docs/api-contract.md), [OpenAPI](docs/openapi.json)
- [Frontend](docs/frontend-handoff.md), [Backend B](docs/backend-b-handoff.md), [Fabric](docs/fabric-handoff.md)
- [Fabric 실제 DB·ERD·DDL·이벤트·Export 제안·Gold 계약 자료](docs/fabric-data-contract/README.md)
- [보관 dry-run](docs/phase7-retention-preview.md), [작은 요청/해시 예시](docs/examples/)

기존 compose/startup.sh·클라우드 배포 문서는 참고 소스이며 이번 업로드에서 실행하지 않는다. startup.sh는 로컬 절차가 아니다. .github/workflows는 반입하지 않았고 저장소에 배포/CI workflow를 추가·활성화하지 않는다. 원천 이용조건을 확인하지 않은 데이터는 이 폴더에 올리지 않는다.

## 2026-11-03 Azure 팀 개발 배포

승인된 배포 절차에 따라 A 전용 Linux App Service/PostgreSQL에 실제 배포했다. 위 로컬 실행 경로·guard는 유지한다. API/Swagger는 https://csflow-backend-a.azurewebsites.net/docs 이며 live/ready200과 HTTPS18개 묶음·61건을 새로 검증했다. 실제 B/AI/Fabric/발송은 미연결이고 자동 처리는 PAUSED, 분석은 NO_PUBLISHED_BATCH이다.

[배포·비용·재배포·복구 안내](docs/azure-deployment.md), [새 검증 증거](docs/evidence/azure-team-dev/)를 읽는다. 담당 폴더의 python -m scripts.azure_deploy와 scripts.azure_verify는 명시적 Azure 운영 도구이며 local_runtime이 실행하지 않는다. 체험 비밀번호는 ignored .cache/azure-backend-a/demo-accounts.json을 로컬 편집기로 확인하고 출력/공유하지 않는다. 환경변수 이름만 [예시](docs/examples/azure-settings.names.json)에 있다.


## 2026-11-03 지정 이름 이전 완료

새 이름3개로 실제 이전·검증하고 구3개 삭제 및 공용잠금 복원을 완료했다. API https://csflow-backend-a.azurewebsites.net/api/v1, Swagger /docs, PG csflow-backend-a-pg, Plan csflow-backend-a-plan이다. 현재 state는 .cache/azure-backend-a이며 기존 DB를 seed로 대체하지 않았다. 원본32테이블·모든기존행 보존, 기존상태HTTP16건/핵심HTTPS61건/도구6개검증은[실제 이전 보고](docs/azure-migration.md)를 따른다. 기존 전체368개 재실행이 아니다.
