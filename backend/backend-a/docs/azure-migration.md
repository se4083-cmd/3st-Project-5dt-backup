# Backend A Azure 이름 이전 — 실제 완료

2026-11-03 KST에 승인된 A 전용 생성·복사·전환·검증·구 리소스 정리를 완료했다. 실제 Backend A **0.6.1 / migration0006**이다. API·DB는 실행 상태로 유지한다. 새 기능/B·AI·Fabric·발송 엔진은 추가하지 않았다.

## 현재 주소와 구성

- Swagger: https://csflow-backend-a.azurewebsites.net/docs
- API base: https://csflow-backend-a.azurewebsites.net/api/v1
- live: https://csflow-backend-a.azurewebsites.net/health/live
- readiness: https://csflow-backend-a.azurewebsites.net/health/ready
- PostgreSQL: csflow-backend-a-pg.postgres.database.azure.com / backend_a
- Plan: csflow-backend-a-plan, Linux B1·1 instance
- DB: PostgreSQL16 Flexible Server Standard_B1ms·32GiB, HA없음·백업7일
- 구독27db5ec6-d206-4028-b5e1-6004dca5eeef, 그룹5dt-final-team1, 모두Korea Central
- 태그component=backend-a, project=cs-flow-ai, owner=backend-a, environment=team-dev. 개인 이름/임의 해시 접미사 없음.

새 구성을 동등 개발용 사양으로 만들었다. TLS verify-full·OS CA·HTTPS Only/TLS최소1.2·HSTS, 제한된 앱 송신 IP 방화벽, production/seed비활성, 최소 DB 역할과 공개 요청/로그인 제한을 유지한다. 실제 Frontend origin 미확정으로 CORS_ORIGINS=[]이며 추측 origin을 추가하지 않았다. 분석 서비스 허용 ID도[]로 미연결이다.

## 배포 소스와 실제 전환

기존 성공 배포 ID93bf2e08-8a17-40c4-a36e-fad14e412d17, 버전0.6.1과 보관 ZIP55파일 hash를 읽었다. 출발 Git commit447c31890c243e1175b805596a84a19720058edf 위 기존 작업 트리 수정본이었다. 그 ZIP SHA256은 **f5003e46a1cf133e7a52b141fcfcde0f150284eaf1514175dc8ffec0242dae41**이며 새 환경에도 **바이트가 같은 ZIP**을 배포했다. 미배포 작업을 다시 패키징하지 않았다. 현재feature/backend-a의 문서·이전/배포 도구 수정은 아직 미커밋이며 main/push/Actions/자동merge/팀원 메시지는 실행하지 않았다.

1. 원본 전체 DB와 역할·App Settings·실행 구성을 별도 로컬 비공개 디렉터리에 DPAPI 암호화했다. 복호화 왕복과 pg_restore archive목록 읽기를 확인했다.
2. 정확한 새 이름3개를 재확인한 뒤 같은 지역/동등SKU로 생성했다. 원래 JWT/서비스 인증 설정과 실제 계정 데이터를 보존하고 새 DB 자격만 별도로 생성했다. 앱 설정 값은 관리형 암호화 App Settings에 주입했다.
3. 기존 ZIP의 Linux 빌드를 새 앱에서 먼저 완료하고 새 앱을 정지했다. 기존 앱은 그동안 가동했다.
4. 최종 복사에서는 구 앱 정지, runtime DB role NOLOGIN, CONNECT 회수, default_transaction_read_only=on, 해당 DB의 기존 앱 세션 종료·0세션 재확인으로 쓰기를 차단했다. AUTO PAUSED만을 쓰기 차단으로 간주하지 않았다.
5. 최신 전체 custom-format dump를 암호화·보존하고 새 전용 DB에 단일 transaction으로 restore했다. source32테이블의 건수/모든 행내용 hash, PK/FK/CHECK·인덱스·트리거·함수·소유권·권한·시퀀스를 비교했다. source와 target은 모두UTC이다. seed/alembic upgrade/stamp/reset은 실행하지 않았다.
6. 구 DB의 쓰기 차단은 유지하고 새 앱을 시작해 기존 상태와 새 합성 흐름을 HTTPS로 검사했다. 이후 원래 PK별 row hash도 전수 비교해 모든 기존 행이 변경 없이 남았음을 확인했다. 검증 후 새 데이터 포함 backup도 추가했다.
7. 모든 검증·복구 백업 확인 뒤 구3개만 정리했다. 그룹 잠금 예외는 별도 명시 승인을 받아 일시 해제→삭제→동일 설정 복원으로 처리했다. 아래 삭제/잠금 절을 따른다.

초기 복사2회는 복원 도구의 표준 public schema 가정과 Azure 기본 소유권 제한에 걸려 target public 쓰기 시작 전 구 앱으로 자동 복귀했다. 실패 기록은 성공 숫자에 포함하지 않는다. 최종 복사는 최신 원본에서 다시 수행했다. Azure의 실제 public owner는 azure_pg_admin이다. PostgreSQL deparse/reparse 과정에서 CHECK9개의 문자 배열 cast 표현이 달라졌으므로 **리터럴 unbounded-varchar→text 배열 cast만** 정규화했다. 허용 값·컬럼·타입 길이·FK·검증 상태는 엄격 비교하며 실제 값/타입 변경을 감지하는 negative test도 통과했다. 데이터 hash를 정규화하거나 실제 CHECK를 바꾸지 않았다. [Microsoft 기본 소유권 설명](https://learn.microsoft.com/en-us/azure/postgresql/security/security-access-control).

## 실제 데이터와 검증 결과

- 32테이블, **138제약**, source에 존재하는 모든 인덱스/트리거/함수/권한 동일. 시퀀스는 source/target 모두 **3개**이며 last_value와 is_called가 일치했다.
- 기존 상태 HTTP **16건 PASS**: 네 기존 계정/role, 기존 티켓·메시지·후속, 타고객 차단, 현재 유효 배정/관리자 scope와 해결된 티켓의 상담사 접근 차단.
- 새 핵심 HTTPS **18묶음/61건 PASS**: 접수/멱등409/revision/재문의·사람 연결/직원·고객 DTO/후속 blocker/고객360·큐 범위/PAUSED/보관 preview/미게시 분석/413·429/새 앱 restart 데이터·중지 보존.
- 별도 로컬 비DB operator test **6 passed**. 기존 전체 PostgreSQL368/로컬HTTP33/이전 배포 관련92는 이번에 반복하지 않았으며 합산하지 않는다. 전체 pytest를 운영 DB에 실행하지 않았다.
- 자동 중지의paused=true, revision2/generation2를 보존했다. 마지막 후속 완료만으로 자동 해결하지 않으며 explicit 고정 writer는 새 검증 티켓에만 적용했다. 실제 B 응답/배정 엔진 검증이 아니다.

| 주요 테이블 | 복사된 기존 행 | 이번 합성 HTTP 검증 후 추가 행 |
|---|---:|---:|
| users | 8 | +0 |
| customers | 4 | +0 |
| orders | 12 | +0 |
| tickets | 5 | +2 |
| messages | 11 | +4 |
| followup_actions | 2 | +1 |
| audit_events | 114 | +68 |
| automation_jobs | 9 | +3 |
| idempotency_keys | 11 | +4 |

추가 검증 ticket2/message4/followup1 등은 source의 원래 행을 덮어쓰지 않고 보존했다. 해당 전수 PK/hash 검사는모든32테이블에 적용했고 감사114개도 전부 남아 있다. 검증 후 감사/새 업무 데이터가 추가된 상태의 backup은 아래별도 파일이다. 원본821개 합성 계정을 활성화하거나 외부 fixture를 새로 올리지 않았다.

## 구 리소스 정리와 잠금

다음 세 리소스 모두 최종 ARM GET404와 그룹 인벤토리 부재를 확인했다.

- Microsoft.Web/sites/csflow-a-dev-api-6004dca5
- Microsoft.DBforPostgreSQL/flexibleServers/csflow-a-dev-pg-6004dca5
- Microsoft.Web/serverfarms/csflow-a-dev-plan

구 Plan에 다른 앱이 없고 구 서버에 다른 업무 DB가 없는 것을 삭제 직전에 확인했다. Azure Web Apps DELETE의 기본 동작으로 마지막 앱과 빈 plan이 함께 제거됐다. 그래서 뒤의 plan 조회가404였고, 재실행 가능한 정리 검증에서 이미 삭제된 상태를 확인해 완료 처리했다. [공식 빈 plan 삭제 동작](https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/delete?view=rest-appservice-2024-11-01).

처음 직접 DELETE는 ScopeLocked로 거부됐다. 별도로 승인된 잠금 예외 절차는 **공용 DO_NOT_DELETE 일시 해제→구A3개 삭제→즉시 동일 잠금 복원**이었다. 잠금 창은UTC03:02:49–03:04:32(약103초)였고, 동일 이름·CanNotDelete수준·notes/owners로 복원했다. 이 승인된 보안 잠금 예외 외에 그룹 설정·공용 Storage/Foundry/OpenAI/Search/Fabric을 변경/삭제하지 않았다. 실패 경로에서도finally로 보호를 복원했다. 새 API/DB는 삭제 후에도 live/ready200이며 연결은 새 PG이다.

## 백업 위치와 복구

담당 폴더 기준 **.cache/azure-migration/backups/** 이다. 실제 비밀값/백업 파일은 Git·패키지·공유 증거에 없다. Windows 현재 사용자 전용 ACL + DPAPI를 사용하며 해당 Windows 사용자 프로필로 복호화해야 한다. 다른 PC로 암호화 파일만 옮기는 휴대용 백업은 아니므로 이 프로필과 비공개 복구 자료도 안전하게 보존한다.

- 최종 원본: backups/final-frozen-20261103T025255.dump.dpapi (137254bytes, encrypted SHA256 cfc1d7e4fe7dc7b71f7eb9474c61ba914b02293f0c4c7beae525ee650298bf7e)
- 검증 후 새 DB: backups/target-post-verification.dump.dpapi (142598bytes, encrypted SHA256 ee0dd96ec0625ef228c346b579c30fd6d28e3ace8def097f1454a7c76795ea43)
- initial dump·이전 시도별 frozen dump·source/target App Settings·역할 정보도 같은 비공개 폴더에 암호화해 보존했다.

복구 때는 먼저 운영 쓰기를 막고 **최신 새 DB 내용**을 별도 백업한다. 원본 frozen dump로 단순 복귀하면 전환 이후 새 데이터를 잃으므로 자동 주소 복귀를 하지 않는다. 현재Windows 사용자 환경에서 scripts.azure_migrate.crypt(decrypt=True)로 private ASCII 임시 경로에 복호화하고 metadata에 기록한 plaintext SHA256/pg_restore목록을 확인한다. 같은16버전의 별도로 승인된 빈 A 전용 DB에 표준 public schema와 올바른소유자/DB 역할을 준비한 뒤 pg_restore --single-transaction --exit-on-error --no-owner를 사용한다. 운영 DB에 바로 --clean/무조건 schema삭제/stamp/downgrade를 실행하지 않는다. 복원 뒤 전체 hash/PK·FK·권한/sequence/head0006/PAUSED를 검증하고 새 HTTPS에서 확인한 후 연결을 전환한다. 원문·PW·URI를 콘솔에 출력하지 말고 비공개 PG credential 파일과verify-full을 사용한다. 검증용 plaintext 임시 dump/pgpass는 이번 실행에서 제거했다.

이번에는 실제 dump→restore→전체 대조를 완료했지만 장기 재해 복구/PITR 복원 훈련이나 별도 기기 DPAPI복구는 미검증이다. 새 관리형 DB의7일 backup을 유지한다. 구 서버는 이미 삭제됐으므로 그 서버로의 단순 원복은 불가능하다.

## 현재 실행/중지/인수

현재 private state는 **.cache/azure-backend-a**이며 기존 계정의 비밀번호는 이 안 demo-accounts.json을 로컬 편집기로 확인한다. 출력/메신저/Git공유하지 않는다. 정상 재배포 도구의 APP/PG/PLAN과 기본state는 새이름으로 갱신했다. 이 환경에는 seed가 이미 있으므로 bootstrap을 재실행할 필요가 없다. 실 배포는 scripts.azure_deploy, 재검증은 scripts.azure_verify이며이번 이전 도구는완료된 단계/공개쓰기 이후 무조건 재복사를 거부한다. 로컬README/local_runtime/CSFLOW_LOCAL_ONLY guard는 그대로고 기존 로컬 DB/.env를 변경하지 않았다.

```powershell
# Backend A 폴더 안, 향후 필요할 때만 실행. 이번 완료 시에는 정지하지 않는다.
az webapp stop -g 5dt-final-team1 -n csflow-backend-a --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef
az postgres flexible-server stop -g 5dt-final-team1 -n csflow-backend-a-pg --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef
# 재시작: DB start→Ready→API start→health·PAUSED 확인
```

Backend A 과금 대상은 새 API/B1 Plan/PG서버3개만 남았다. 같은 최소구성730시간 가정 월약 **US$36.31**(B1 13.14 + DBcompute18.98 + 32GiB storage4.19)이며 세금/환율/전송·backup초과 등은 별도다. 그룹 공용 리소스 비용은 이 산정에 포함하지 않는다. 이전 중 일시 병행 비용은 있었으나 구3개는 삭제돼 지속 병행 자원은 없다. 앱만 정지하면 Plan과DB비용은 계속되고 DB compute정지 후에도 storage/관련 backup이 남으며7일 자동 시작 가능성도 있다. [App Service가격](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/), [PG가격](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/).

Frontend는 새 API base와 Bearer/동일 RBAC·revision·멱등/DTO 계약을 사용한다. CORS는 실제 HTTPS origin이 확정돼야 별도로 반영한다. B는 새 DB FQDN/TLS/head0006/lease·generation·잠금순서·중지게이트 계약을 따르되 전용 최소 DB identity/네트워크를 별도합의해야 한다. 지금 B접속을 새로 열지 않았다. Fabric은 서비스 ID허용목록이 비어있어 미연결이며 분석은NO_PUBLISHED_BATCH이다. 실제 B/AI/RAG/Fabric/Frontend/발송/부하·DR 통합은 여전히 미검증이다.

최종 정적 검사: Ruff check/format(101개 파일), 엄격 OpenAPI·인수 계약 검사와 git diff --check를 통과했다. 최종 로컬 도구 회귀는 6 passed(Starlette/httpx 기존 경고 1개)다. 포함 소스·문서에서 실제 이전/새 자격값과 JWT 패턴 검사는 발견 0건이었다. 패키지 55개 파일은 manifest와 바이트 hash가 모두 같고, 로컬 app/models.py의 CRLF/LF checkout 차이만 확인했으며 코드 내용 차이는 없다. 최종 인벤토리는 A 전용 새 3개만 남음, 새 DB TLS1.3/head0006/PAUSED, 공용 잠금 복원과 live/ready/docs200을 확인했다. 증거는 docs/evidence/azure-migration에 있다.
