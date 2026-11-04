# Backend A Azure 팀 개발 환경 배포

2026-11-03 KST 사용자 승인으로 실제 생성·배포했다. 이전 단계의 로컬 전용 제한은 이번 A 전용 배포에만 해제됐다. 실제 B·AI/RAG·Fabric·외부 발송은 실행하지 않았다. 원본 개발 폴더/DB/.env는 보존하고 팀 clone의 feature/backend-a에서 작업했다.

최신 이름 이전·기존 리소스 정리·복구 백업은 [실제 이전 보고](azure-migration.md)를 기준으로 한다. 아래 최초 배포 실행 결과는 당시 기록이며 최신 이전 검증과 합산하지 않는다.

## 실제 구성과 소유 범위

구독 27db5ec6-d206-4028-b5e1-6004dca5eeef, tenant 5fb256f0-fbf2-40d2-81d5-bac1b32c419d. 두 로그인 구독에서 그룹을 읽어 이 구독에만 5dt-final-team1이 있음을 확인했다. 구독 이름으로 선택하지 않았다.

| A 전용 대상 | 실제 구성 |
|---|---|
| 리소스 그룹 | 기존 5dt-final-team1, Korea Central |
| csflow-backend-a-plan | Linux B1, 1 instance, Korea Central |
| csflow-backend-a | Linux Python 3.13, HTTPS Only, API worker 1 |
| csflow-backend-a-pg | PostgreSQL 16 Flexible Server, Burstable Standard_B1ms, 32GiB, HA 없음, 백업7일, 지역 중복 백업 없음 |
| DB / 사용자 | backend_a / 별도 owner와 csflow_a_api runtime 역할 |
| 태그 | project=cs-flow-ai, owner=backend-a, component=backend-a, environment=team-dev |

기존 그룹에는 API plan/DB/network가 없어 전용 plan·앱·DB 서버를 생성했다. 기존 Storage·OpenAI·Foundry·Search·Fabric은 리소스 이름/타입/리전 목록만 읽었으며 설정·키·데이터는 변경하지 않았다. VNet/NAT/Key Vault/Application Insights/HA/슬롯/별도 로그 리소스를 추가하지 않았다.

## 접속과 합성 체험

- API: https://csflow-backend-a.azurewebsites.net
- live: https://csflow-backend-a.azurewebsites.net/health/live
- ready: https://csflow-backend-a.azurewebsites.net/health/ready
- Swagger: https://csflow-backend-a.azurewebsites.net/docs

Swagger/OpenAPI는 팀 개발용으로 공개한다. 데이터 endpoint는 기존 Bearer 인증/RBAC/scope/purpose를 그대로 검사한다. Swagger에서 로그인 응답의 access_token을 자신의 브라우저 Authorize에 사용하며 키나 비밀번호를 URL에 넣지 않는다. 실제 Frontend origin 미확정으로 CORS_ORIGINS=[]이다. wildcard나 추측 origin을 등록하지 않았다. Frontend 주소가 확정되면 정확한 HTTPS origin만 A 앱 설정에 추가해야 하며 React 화면은 이번 범위가 아니다.

합성 체험 계정은 demo-customer1@csflow.example.test, demo-customer2@csflow.example.test, demo-agent@csflow.example.test, demo-admin@csflow.example.test이다. 최초 배포 때 생성하고 이전에서도 보존한 각 계정의 비밀번호는 담당 폴더 안 ignored `.cache/azure-backend-a/demo-accounts.json`을 로컬 편집기로 확인한다. 콘솔 cat/로그/대화/스크린샷/커밋으로 공유하지 않는다. 비밀 state 디렉터리는 Windows 현재 사용자 SID에만 파일 권한을 부여했다. 배포 패키지에 이 파일은 없다.

고객은 로그인→orders→본인 티켓 접수/멱등 재시도→reopen/request-agent를 체험한다. 상담사 배정은 B가 없어 자동 생성되지 않는다. 검증 과정의 명시적 고정 배정/응답 데이터와 관리자 조회를 실제 B/AI 처리라고 표시하지 않는다. 기본 seed의 dev-* 계정은 production에서 여전히 인증 불가이며 원본821개 계정을 업로드·활성화하지 않았다. 전체 외부 fixture 대신 검증된 작은 SYNTHETIC seed·별도 검증 티켓만 적재했다. 자동 처리는 DB의 PAUSED 상태를 유지하며 체험 관리자에게 AUTOMATION_RESUME/UNROUTED_QUEUE_READ/RETENTION_GLOBAL_REVIEW를 부여하지 않았다.

## 배포 코드와 패키지

출발 커밋은 447c31890c243e1175b805596a84a19720058edf이다. 이 커밋 위 담당 폴더의 작업 트리 변경(공개 환경 제한·시작 옵션·수동 배포/검증 도구)을 배포했다. main/다른 담당 폴더는 변경하지 않았으며 이번에 Git commit/push/Actions/PR/merge는 실행하지 않았다. 실제 ZIP의 SHA256과 개별 파일 digest는 `docs/evidence/azure-team-dev/artifact-manifest.json`으로 고정한다. manifest의 worktree_changed=true를 숨기지 않는다. 배포 이후 앱/migration/시작 파일이 manifest와 같은지 최종 검사했다.

55개 파일 약90KB의 allowlist 패키지다. app/*.py, migrations/*.py, requirements.txt, pyproject.toml, alembic.ini, startup.sh와 최소 bootstrap 모듈만 포함한다. 로컬 DB/캐시/venv/실제 env/비밀 state/원시 로그/검토 ZIP/외부 원천/전체 fixture/워크플로는 제외했다. 새 실제 비밀값과 ZIP 바이트 비교 검사도 통과했다. 로컬 guard는 변경하지 않았고 로컬 도구의 CSFLOW_LOCAL_ONLY=1 방어를 유지한다. Azure에는 APP_ENV=production과 verify-full을 명시한다.

## 보안·네트워크·운영 제한

- DB URI는 PostgreSQL+psycopg, sslmode=verify-full, Linux OS CA bundle `/etc/ssl/certs/ca-certificates.crt`를 사용한다. Windows 관리 도구는 공개 certifi CA를 ASCII 임시 경로에 복사한다. 인증서 검증을 끄지 않았다.
- DB에는 실제 앱 outbound IP25개 각각의 단일 IP 규칙만 허용했다. 인터넷 전체/0.0.0.0 Azure 전체 허용 규칙은 없다. plan/tier/송신 IP가 바뀌면 새 목록을 검토해 갱신해야 한다. 사설 endpoint 구성은 이번에 하지 않았다.
- 팀 그룹의 CanNotDelete 잠금 때문에 임시 operator 규칙 DELETE는 ScopeLocked였다. 공용 잠금은 변경하지 않고 A 전용 bootstrap/verification 임시 규칙을 각각127.0.0.1로 변경해 외부 operator 접근을 닫았다. 존재하는 비활성 규칙과 실제 외부 허용을 구분한다.
- 새 JWT/분석 서비스 키/DB owner·runtime 암호는 private state에서 생성하고 A 앱의 암호화 App Settings로 주입했다. 로컬 개발 자격값은 재사용하지 않았다. Key Vault/Managed Identity/자동 키 회전은 미구현이다. App Settings 조회 권한이 있는 운영자는 비밀값을 읽을 수 있으므로 RBAC 관리가 필요하다.
- runtime DB 역할은 SELECT/INSERT/UPDATE와 sequence 사용만 가능하고 DDL/DELETE/role·DB 생성 권한은 주지 않았다. migration은 별도 owner 단계에서만 실행한다. API startup은 migration/seed를 실행하지 않는다.
- HTTPS Only, TLS최소1.2, HSTS, FTPS/SCM 기본 인증 비활성. CLI는 기존 Entra 로그인으로 배포했다. App Service HTTP 상세·요청 추적 로그와 Uvicorn access log는 끈다. 앱은 request ID/status만 기록한다. DB log_error_verbosity=terse, log_parameter_max_length=0, log_parameter_max_length_on_error=0, log_statement=none이다.
- production에서 일반 body128KiB, 분석 업로드8MB, Uvicorn 동시16·backlog128·keepalive5초이다. 로그인은 한 프로세스에서 계정10/분, peer60/분, 전체120/분을 제한하고429/Retry-After를 반환한다. 원시 로그인명/IP 대신 digest만 메모리에 보관한다. 신뢰되지 않은 X-Forwarded-For를 식별자로 사용하지 않는다. proxy peer를 공유하면 보수적으로 함께 제한될 수 있다. 재시작 시 초기화되며 다중 worker/scale-out에는 공유 ingress limiter가 필요하다. 대규모 운영 rate-limit/부하 검증 완료로 주장하지 않는다.
- 연결 풀3+overflow2, worker1, connect5초/statement10초이다. CORS와 서비스 허용 ID는 빈 목록이다. Fabric 수신·게시 서비스 인증은503 ANALYTICS_SERVICE_AUTH_NOT_CONFIGURED 상태이며 실제 Fabric은 연결하지 않았다.

## 재배포와 DB 초기화

저장소 루트에서는 먼저 `cd backend/backend-a`로 이동한다. 이후 모든 명령은 담당 폴더 기준이다. Python 가상환경과 고정 requirements-dev를 설치하고 Azure CLI의 계정·구독·그룹 소속을 다시 확인한다. `.env.example`은 로컬 전용이며 Azure에는 복사하지 않는다. 설정 이름 목록은 `docs/examples/azure-settings.names.json`이다.

```powershell
python -m scripts.azure_deploy provision
python -m scripts.azure_deploy configure
# 별도 owner 단계: API worker보다 먼저. 새 전용 DB만 대상으로 한다.
python -m scripts.azure_deploy bootstrap
python -m scripts.azure_deploy deploy
python -m scripts.azure_verify
```

provision은 기존 전용 plan 소유 태그를 검증한다. 최초 plan 생성이 필요한 경우 `az appservice plan create -g 5dt-final-team1 -n csflow-backend-a-plan --location koreacentral --is-linux --sku B1 --number-of-workers 1 --tags project=cs-flow-ai owner=backend-a component=backend-a environment=team-dev --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef`를 별도 실행한다. 그 이후 앱/DB 생성·수정 대상은 스크립트에 고정했다. 기존 전용 리소스가 있는데 비밀 state가 없으면 임의 키 회전 대신 중단한다. state를 안전한 관리자 절차로 복구해야 한다. 새 환경에서 임의 state를 생성해 configure하지 않는다.

bootstrap은0001–0006을 순서 적용하고 seed는 insert-missing으로 기존 계정 암호/업무 데이터를 덮어쓰지 않는다. 자동중지 해제도 하지 않는다. 임시 operator IP는 자신의 A 앱 활동 로그에서 확인하며 VPN/IP가 바뀐 경우 그 값을 임의 사용하지 말고 실제 클라이언트 IP를 확인해야 한다. 보안 규칙 변경/자격정보 누출이 의심되면 자동 복구가 아닌 담당자 검토가 필요하다.

## 실제 실행 결과와 제한

- Windows/Python3.13.15의 새 로컬 격리 PostgreSQL16.15에서 최종 관련 **92 passed / 실패0 / skip0**,50.59초. 이번 새 전체 회귀 결과는 아니다. 먼저 실행한90개와 합산하지 않는다.
- 관련 SQLite 보조 **26 passed**는 초기 배포 보안/설정 실행이다. 이후 추가한 도구 회귀2개는 위 PostgreSQL92에 포함되며26과 합산하지 않는다.
- 실제 Azure Linux Oryx **Python3.13.18**, requirements 고정29개 설치 확인, 빌드 오류0. 런타임이 실제 FastAPI/psycopg/Uvicorn으로 기동했다. Linux 전체 pytest는 실행하지 않았다.
- 실제 HTTPS **18개 검증 묶음 / 기대 상태 요청61건 PASS**. health/head/TLS,4역할 로그인·오인증, 본인 주문/티켓과 타인404, 멱등/409, 재문의/직접연결, 큐와 현재 배정 권한 분리, 타팀 상세/고객360 집계 차단, 내부자료 MISSING, 공개 후속 메모 분리, 공통 blocker/명시적 합성 해결, 자동중지·재개권한 차단, dry-run 업무표 hash 불변·감사, 분석 미게시,429/413, 실제 앱 restart 후 데이터·중지 상태 보존을 확인했다.
- 초기 HTTP 검증은 개발 PC의 약1초 빠른 시각으로 미래 배정/미래 as_of가 거부됐다. DB 시각 기반 검증 fixture로 수정한 최종 실행이18/61 PASS이며 실패를 합산하지 않았다. 앱의 미래 배정/미래 as_of 방어는 그대로다.
- 기존368 PostgreSQL / 로컬HTTP33은 이전 원본0.6.1의 역사적 증거다. 이번 실행으로 재표시하지 않는다.
- 실제 B 배정·사람 응답/발송, AI/RAG, Fabric, Frontend 브라우저 연동·CORS, 성능/장애/PITR 복원·키회전은 미검증이다. 배정·고정 응답은 검증용 DB writer이며 인증 없는 HTTP endpoint를 추가하지 않았다. 분석 배치를 게시하지 않았고 미게시 응답을 확인했다. 법적 보존 정책 확정이나 실제 삭제도 하지 않았다.

새 증거는 `docs/evidence/azure-team-dev/`에 비밀값·PC 경로를 제외해 저장한다. 로컬 원시 결과/비밀 state는 `.cache/azure-team-dev`와 `.cache/azure-regression`에만 있다.

## 비용·중지·복구

2026-11-03 Microsoft Retail Prices API의 Korea Central/USD/Consumption 단가: B1 Linux0.018$/시간×730=13.14$, PostgreSQL B1MS0.026$/시간×730=18.98$, 일반 storage32×0.131$/GiB월=4.192$, 합계 약 **36.31$/월**. 계약 할인/세금/환율/전송·백업 초과분은 미포함이며 확정 청구액이 아니다. 팀 전체 예산을 A 예산으로 간주하지 않았다. [App Service 가격](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/) / [PostgreSQL 가격](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/).

현재 API/DB는 사용자가 접속하도록 실행 중으로 유지한다. 아래는 나중에 A 전용 대상만 정지할 때의 명령이며 이번에 실행하지 않았다.

```powershell
az webapp stop -g 5dt-final-team1 -n csflow-backend-a --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef
az postgres flexible-server stop -g 5dt-final-team1 -n csflow-backend-a-pg --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef
# 재시작은 DB start → Ready 확인 → webapp start → health/중지 상태 확인
```

앱만 정지해도 B1 plan 과금은 계속되고 DB도 별도 과금된다. DB compute 정지 시에도 storage/해당 backup 비용은 남으며 서버는7일 뒤 자동 시작할 수 있다. [plan 과금 구조](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans), [DB 중지](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/how-to-stop-server). 비용을0으로 만들려면 데이터를 별도 보존하고 A 전용 app→DB server→빈 plan의 삭제를 별도 검토해야 한다. 현재 공용 삭제 잠금은 삭제를 차단하므로 팀 소유자가 별도 변경 절차를 정해야 하며 일반 배포 도구는 잠금을 제거하지 않는다. 별도 이전 도구의 잠금 예외 절차는 이번 명시 승인 하에서만 실행했다. 그룹 전체나 다른 팀 리소스 삭제 명령은 제공/실행하지 않는다. 최초 배포 단계에는 실제 업무 데이터/클라우드 리소스 삭제가 없었다. 이후 지정 이름 이전에서는 별도 승인에 따라 구 A 리소스 3개를 삭제하고 공용 잠금을 복원했다. 최신 정리 결과는 이전 보고를 따른다.

최초 배포 당시 검증된 이전 Azure 배포는 없었다. 현재는 이전에 사용한 동일 ZIP과 원본·검증 후 DB 백업이 보존돼 있다. 다음 배포 전 현재 ZIP·manifest와 DB 백업 상태를 보존한다. 실패 시 같은0006과 호환되는 이전 artifact를 수동 재배포하고 health/권한/중지 상태를 다시 확인한다. B1에는 배포 슬롯이 없어 무중단 슬롯 복구를 보장하지 않는다. migration은 별도 단계이고 자동 downgrade/초기화하지 않는다.0005/0006의 권한·중지·보관 감사가 존재하므로 무조건 downgrade는 금지이며0006 호환 build를 사용한다. 실제 PITR 복원/이전 artifact 롤백 훈련은 미실행이다.

## 공식 확인 근거

- [Linux Python runtime·FastAPI 시작·Oryx](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
- [ZIP 배포/빌드](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [기본 배포 인증 비활성/Entra](https://learn.microsoft.com/en-us/azure/app-service/configure-basic-auth-disable)
- [PostgreSQL verify-full·CA](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect)

CLI의 실제 runtime 목록에서 Python3.13 Active, list-locations에서 Korea Central/B1, PostgreSQL list-skus에서 Standard_B1ms 지원을 확인한 후 같은 지역에 생성했다. 다른 리전 우회는 하지 않았다.

## 과거 기록: 2026-11-03 이름 가용성 확인 직후 상태

이 절은 실제 이전 승인 전의 기록이다. 이후 아래 지정 이름 이전으로 완료됐다. 당시 세 희망 이름의 가용성을 확인했으나 기존 리소스 직접 rename은 지원되지 않아 실제 이름과 실행 상태를 보존했다. 세 리소스에는 component=backend-a만 태그 병합했고 개인 이름 태그는 추가하지 않았다. 새 리소스 생성/이전/삭제/재시작/재배포는 실행하지 않았다. 기존 URL과 비밀 설정도 그대로다. [가용성 결과·이전 절차와 영향](azure-naming-review.md)을 따른다.


## 2026-11-03 지정 이름 이전 완료

새 이름3개로 실제 이전·검증하고 구3개 삭제 및 공용잠금 복원을 완료했다. API https://csflow-backend-a.azurewebsites.net/api/v1, Swagger /docs, PG csflow-backend-a-pg, Plan csflow-backend-a-plan이다. 현재 state는 .cache/azure-backend-a이며 기존 DB를 seed로 대체하지 않았다. 원본32테이블·모든기존행 보존, 기존상태HTTP16건/핵심HTTPS61건/도구6개검증은[실제 이전 보고](azure-migration.md)를 따른다. 기존 전체368개 재실행이 아니다.
