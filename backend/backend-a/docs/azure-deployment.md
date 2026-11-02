# Azure App Service Linux 배포 준비

이번 작업에서는 유료 리소스 생성, Azure 로그인/설정 변경, 실제 배포를 실행하지 않았습니다. 아래는 기존 팀 배포 방식이 없는 상태에서 선택한 수동 패키지 배포 제안입니다. 초기에는 CI에서 검증한 동일 소스를 App Service 기본 Python 런타임에 배포하고, migration은 한 명의 release 담당자가 별도 단계로 실행합니다. worker마다 migration을 실행하지 않아 동시 DDL과 자동 개발 seed를 피합니다.

## 준비할 설정

Python 3.11 이상(로컬 검증 환경은 보고서 참조), Linux App Service, PostgreSQL Flexible Server를 사용합니다. 저장소 루트의 `requirements.txt`, `app/`, `migrations/`, `alembic.ini`, `startup.sh`를 포함합니다. `.env`, `.cache`, `.venv`, reference, tests의 민감한 실행 산출물은 패키지에서 제외합니다. 빌드 서비스가 `pip install -r requirements.txt`를 수행하도록 SCM_DO_BUILD_DURING_DEPLOYMENT=true를 설정하는 방식을 제안합니다.

App Service Startup Command는 `sh startup.sh`입니다. [Microsoft의 Python App Service 구성 문서](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)에 따라 명시적인 시작 명령을 사용합니다. 실행 내용은 다음과 같습니다.

```sh
python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-access-log --log-level info
```

기본 바인딩은 8000이며 이 문서는 App Service **기본 Python 런타임**을 기준으로 합니다. 사용자 컨테이너의 WEBSITES_PORT 설정과 혼용하지 않습니다. 실제 runtime/ingress에서 바인딩 포트가 다르면 PORT를 맞추고 readiness를 검증합니다. `debug=False`는 앱에 고정되어 있습니다. `--reload`는 운영에서 사용하지 않습니다.

| 환경변수 | 운영 값/의미 |
|---|---|
| APP_ENV | production |
| DATABASE_URL | postgresql+psycopg URI, 비밀 저장소 참조 권장, sslmode=verify-full |
| JWT_SECRET | 환경별 무작위48자 이상, Key Vault/App Settings 비밀 참조, 개발 키 재사용 금지 |
| JWT_ISSUER / JWT_AUDIENCE | 기본 cs-flow-ai / cs-flow-api, 환경별 필요 시 분리 |
| TOKEN_MINUTES | 기본30, 최대120 |
| ENABLE_DEV_SEED | false, production에서 true이면 시작 거부 |
| CORS_ORIGINS | `["https://<frontend-domain>"]`, wildcard 금지 |
| ALLOWED_HOSTS | `["<app>.azurewebsites.net","<custom-domain>"]`, wildcard 금지 |
| POOL_SIZE / MAX_OVERFLOW | 기본5 / 5, worker 하나당 풀 |
| POOL_TIMEOUT | 기본10초, 최대60 |
| DB_CONNECT_TIMEOUT | 기본5초, 최대30 |
| DB_STATEMENT_TIMEOUT_MS | 기본10000ms, 최소500/최대60000 |
| WEB_CONCURRENCY | 기본2, DB 연결한도와 App Service 메모리 기준 조정 |
| PORT | 기본8000, 런타임 요구 포트와 일치 |
| FORWARDED_ALLOW_IPS | 실제 신뢰하는 ingress proxy IP/CIDR 목록. 기본127.0.0.1 |

2 workers × (5+5)=최대20 연결이 인스턴스별로 발생합니다. 슬롯·스케일아웃·B worker·migration 연결까지 서버 한도에 포함합니다. pool_pre_ping=true, recycle=1800초, SQL parameter 숨김, timezone=UTC, statement_timeout을 적용했습니다. 연결 오류·timeout에는 원문 없는 503이 반환됩니다.

## PostgreSQL TLS와 네트워크

URI 형식은 `postgresql+psycopg://<user>:<url-encoded-password>@<server>.postgres.database.azure.com:5432/<db>?sslmode=verify-full&sslrootcert=%2Fhome%2Fsite%2Fcerts%2Fpostgres-roots.pem`입니다. password/경로는 올바르게 URL 인코딩하고 URI를 로그/배포 출력에 쓰지 않습니다. 로컬 compose의 TLS 없는 접속 설정을 운영에 복사하지 않습니다.

production 설정 검증은 PostgreSQL+psycopg와 verify-full을 강제합니다. 신뢰 root CA bundle을 별도 배포하거나 libpq가 사용하는 신뢰 저장소를 준비하고 서버 FQDN과 인증서를 검증해야 합니다. 단순 sslmode=require는 암호화만 하므로 이번 운영 설정에서 거부합니다. [Microsoft TLS 연결 안내](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect)를 기준으로 현재 권장 root chain을 배포 시 재확인합니다. 인증서 내용·회전 일정을 코드에 고정하지 않았으며 Azure 실제 TLS handshake는 배포 전 별도 검증 대상입니다.

App Service에서 DB로의 VNet/private DNS 또는 명시적 firewall 경로를 팀 네트워크 정책에 맞게 준비합니다. API 런타임 DB 계정은 DML에 필요한 최소 권한만 주고 DDL migration 계정과 분리합니다. 이번 코드가 DB 계정/네트워크를 생성하지는 않습니다.

DB 서버 로그도 원문을 남기지 않도록 관리자가 `log_error_verbosity=terse`, `log_parameter_max_length=0`, `log_parameter_max_length_on_error=0`, `log_statement=none`을 적용하고 해당 Flexible Server 버전의 설정 지원 여부를 확인해야 합니다. 기본 PostgreSQL 오류 로그는 CHECK 실패의 Failing row DETAIL에 메시지 원문을 포함할 수 있습니다. SQLAlchemy의 hide_parameters만으로 서버 로그까지 보호되지는 않습니다. 로컬 compose에는 이 설정을 넣었고 Azure에는 실제 적용하지 않았습니다. 별도 쿼리 모니터·진단 수집기의 본문/파라미터 수집도 꺼야 합니다.

## 프록시와 HTTPS

App Service의 HTTPS Only를 켜고 TLS는 ingress에서 종료합니다. 앱이 받는 내부 HTTP와 외부 HTTPS를 구분하려면 Uvicorn의 forwarded header 신뢰 대상을 실제 ingress에 맞춥니다. 기본값은 loopback만 신뢰하므로 배포 담당자가 실제 proxy 범위를 확인해야 합니다. `*`는 public 클라이언트가 직접 worker에 도달할 수 없는 ingress 격리가 입증된 경우에만 사용합니다. 앱 내부 HTTPSRedirectMiddleware는 추가하지 않아 잘못된 proxy 신뢰로 리다이렉트 loop를 만들지 않도록 했습니다. 실제 외부 URL/헤더/사용자 도메인 동작은 배포 후 확인합니다.

CORS는 환경별 명시 origin 목록이며 쿠키 인증을 켜지 않습니다. Authorization 헤더, Content-Type, Idempotency-Key만 허용하고 X-Request-ID/Location/Idempotency-Replayed를 Frontend에 노출합니다. 앱과 별개인 App Service/ingress 진단 로그에서도 Authorization·query token·request body를 수집하지 않도록 검토합니다. 로그인 brute-force rate limit과 요청 크기 제한은 운영 ingress 또는 다음 구현에서 확정해야 합니다.

## release 순서와 담당

1. Backend A/QA가 실제 PostgreSQL 테스트·fixture 전체 적재·동시성을 확인하고 release artifact를 고정합니다. CI 파일은 준비했지만 CI 실행 성공을 로컬 검증으로 추정하지 않습니다.
2. 배포 담당자가 백업/복구 가능성, DB 연결·TLS·환경 비밀·프록시·CORS를 확인합니다. production 환경변수로 앱이 개발 키/seed를 거부하는지 확인합니다.
3. release 담당자 한 명/배포 job 하나가 동일 artifact와 migration용 DB 권한으로 `python -m alembic upgrade head`를 실행합니다. 실패하면 API 전환을 중단하고 기존 artifact를 유지합니다. migration 시작 전 운영 backup을 준비하며 자동 downgrade를 무조건 실행하지 않습니다.
4. App Service artifact를 배포하고 `sh startup.sh`로 시작합니다. 런타임은 migration/seed를 호출하지 않습니다.
5. `/health/live`와 `/health/ready`, 테스트 사용자/실제 권한으로 API를 확인하고 트래픽을 전환합니다. App Service Health Check path는 `/health/ready`를 권장합니다. readiness는 DB와 revision 0004을 검사하므로 다음 migration에서 기대 revision도 갱신해야 합니다.
6. 문제 발생 시 이전 검증 artifact/슬롯으로 복구합니다. DB schema 호환성은 별도로 평가하고 무조건 downgrade하지 않습니다. 개발 계정은 운영 로그인·기존 토큰 인증 모두 거부됩니다.

현재 head/readiness는0004입니다. 2단계 명령/HANDOFF·3단계 후속 변경·4단계 receipt가 있으면 해당 이력을 잃는 downgrade를 거부합니다. rollback은0004 호환 build를 사용하며0003만 허용하는 readiness build로 무조건 복구하지 않습니다. 기존 검증 증거 없는 current는0004에서 내려가므로 새로운 managed snapshot을 재수신/검증/게시해야 합니다. 운영 백업/복구·슬롯 전환·Managed Identity·외부 감사 sink·Azure 부하/장애 테스트는 미검증입니다. 이번에는 Azure 명령/배포를 실행하지 않았습니다.
