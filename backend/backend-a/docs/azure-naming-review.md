> 이 문서는 최초 이름 변경 검토 기록이다. 이후 별도로 승인된 A 전용 이전 절차로 실제 이전·검증·구3개삭제를 완료했다. 현재상태는[azure-migration.md](azure-migration.md)를 따른다.

# Azure 리소스 이름 변경 검토 — 2026-11-03 KST

이번 요청은 기존 리소스/데이터/실행 상태를 보존하면서 직접 이름 변경 가능성과 희망 이름 가용성을 확인하는 범위다. 직접 변경이 불가능하므로 새 리소스/이전/재배포/삭제/재시작은 실행하지 않았다. 희망 이름에 개인 이름이나 임의 접미사를 붙이지 않는다.

## 실제 확인

| 대상 | 현재 이름(보존) | 희망 이름 | 가용성 | 기존 리소스 직접 이름 변경 |
|---|---|---|---|---|
| API | csflow-a-dev-api-6004dca5 | csflow-backend-a | Microsoft.Web 공식 checknameavailability에서 nameAvailable=true | 지원 안 함 |
| PostgreSQL 서버 | csflow-a-dev-pg-6004dca5 | csflow-backend-a-pg | 공식 전역 checkNameAvailability에서 nameAvailable=true | 지원 안 함 |
| App Service Plan | csflow-a-dev-plan | csflow-backend-a-plan | 5dt-final-team1 안에 동명 plan 없음, 이름 문법 적합 | 지원 안 함 |

확인 구독은27db5ec6-d206-4028-b5e1-6004dca5eeef이며 다른 구독으로 우회하지 않았다. PostgreSQL의 Korea Central 지역별 이름 확인 API는403 AuthorizationFailed(Microsoft.DBforPostgreSQL/locations/checkNameAvailability/action)였지만 같은 구독의 공식 **전역** 이름 확인 API는200/true였다. 전역 이름 확인 성공과 지역별 검사 권한 제한을 모두 증거에 남겼다. 가용성은 확인 순간의 결과이며 이름 예약이나 추가 리소스의 SKU/쿼터 보장이 아니다. 리소스 생성으로 가용성을 시험하지 않았다.

기존 서버 안의 논리 DB 이름 backend_a를 바꾸는 것과 Azure PostgreSQL 서버 이름/FQDN을 바꾸는 것은 별개다. SQL ALTER DATABASE/ALTER SERVER로 Azure 리소스 이름을 바꿀 수 없다. 관리 API의 리소스 이름은 URI의 식별자이며 rename 작업은 없다. 단순히 배포 스크립트 상수를 바꾸면 별도 리소스 생성 대상이 되므로 기존 APP/PG/PLAN 상수는 실제 현재 이름으로 유지했다.

## 실제 변경과 보존 확인

A 전용 세 리소스에 Azure Tags API의 Merge로 **component=backend-a**만 추가했다. 기존 project=cs-flow-ai, owner=backend-a, environment=team-dev는 보존했으며 개인 이름 태그는 없고 새로 추가하지 않았다. owner=backend-a는 개인 식별자가 아니라 기존 구성요소 식별 태그다. 배포 도구 TAGS에도 component를 반영해 나중의 명시적 배포가 이 표기를 유지하도록 했다. 이 변경을 앱에 재배포하지는 않았다.

태그 서비스/provider 조회 사이 반영 시차가 있어 최종 반영을 재조회해 확인했다. 세 리소스의 ID/이름과 다른 태그가 유지됐다. API Running, PostgreSQL Ready, Plan Ready, 기존 URL의 live/ready200이다. DB 연결/SQL/migration/seed/권한/비밀번호/자동중지 상태/방화벽/app settings/실행 수명주기는 변경하지 않았다. 업무 데이터에 쓰기나 삭제를 하지 않았다. 전체 테스트도 반복하지 않았다.

증거: evidence/azure-team-dev/requested-name-availability.json, naming-tag-preservation-report.json. 이름은 그대로이므로 기존 접속 URL은 https://csflow-a-dev-api-6004dca5.azurewebsites.net 이다. 세 리소스 이름을 변경했다고 보고하지 않는다.

## 향후 별도 이전 절차와 영향 — 이번에 미실행

1. **진입 전 확인:** 같은 그룹·Korea Central에서 이름을 재확인하고 병행 리소스 쿼터/예산·최신 artifact·백업/복구 가능성을 확인한다. 새 리소스에도 component=backend-a를 사용한다. 현재 그룹의 공유 CanNotDelete 잠금을 보존하며 잠금 때문에 향후 구 리소스 정리가 차단될 수 있다.
2. **Plan:** 새 csflow-backend-a-plan을 동일 그룹/리전/Linux/적합한 webspace에 별도 구성해야 한다. 기존 앱의 plan 연결을 바꾸는 방법은 있지만 이름 변경 기능은 아니다. 앱 재기동/연결 끊김·송신 IP 변경 가능성을 고려해 DB 단일-IP 방화벽과 health를 확인해야 한다. 현재 앱의 plan을 바꾸지는 않았다.
3. **API:** 새 csflow-backend-a 앱에 검증된 artifact와 비밀 설정을 별도로 주입하고 새 ALLOWED_HOSTS·HTTPS·CORS·body/rate limit·최소 DB 권한을 검증한다. 기존 앱을 유지한 병행 검증 후 Frontend/API 문서·클라이언트 base URL을 전환한다. 기본 azurewebsites.net 주소는 바뀌며 기존 기본 호스트를 새 앱에 이름만 바꿔 넘길 수 없다. 인증 키를 유지할지 회전할지에 따라 기존 JWT의 유효성이 달라지므로 전환 계획을 명시해야 한다.
4. **DB:** 새 csflow-backend-a-pg로의 백업/PITR 복원 또는 일관된 dump/restore 등 별도 데이터 이전이 필요하다. 복원 시점 이후 쓰기를 놓치지 않도록 최종 동기화와 짧은 유지보수 쓰기 차단을 계획해야 한다. AUTO PAUSED만으로는 고객 접수/사람 후속/서비스 쓰기가 차단되지 않는다. 두 개로 갈라진 DB에 동시 쓰기하지 않는다. 데이터·idempotency·감사·후속·회차·automation_control revision/generation을 보존하고 행/내용·head0006을 검증한다. 기존 DB를 초기화하거나 seed를 덮어쓰지 않는다. 관리 계정/역할·최소 runtime grant·CA/TLS·방화벽·로그 보호가 자동 복원된다고 가정하지 않는다.
5. **연결 전환:** 새 서버 FQDN으로 비밀 DATABASE_URL을 갱신하고 verify-full·인증서 호스트 검증을 유지한다. 앱 설정 변경은 API 재시작/짧은 중단을 유발할 수 있다. 서버 이름을 임의 DNS 별칭으로 가리는 방식으로 TLS 검증을 완화하지 않는다. 향후 B의 DB 연결·Fabric/Frontend 계약에도 승인된 새 주소를 반영해야 하며 실제 연결은 이번에 실행하지 않았다.
6. **검증·복구:** 새 HTTPS의 인증/범위/멱등/후속/중지/미게시 분석·보관 preview 및 재시작 보존을 검증한 후 전환한다. 원본 앱/DB/plan은 유지하고 복귀할 주소·데이터 기준을 고정한다. 새 DB에 쓰기가 발생한 뒤 옛 DB로 무조건 돌아가면 데이터가 갈라질 수 있어 역동기화 판단이 필요하다. 구 리소스 정리는 별도 승인과 공유 잠금 소유자 절차가 필요하며 이번 요청으로 실행하지 않는다.

이전 기간에는 기존·신규 구성의 병행 비용이 생긴다. 이전 배포의 동일 최소 구성 단가(월730시간 가정)를 그대로 적용하면 완전 병행 시 약36.31달러/월의 추가분이 가능하지만 실제 기간/구성/할인/추가 backup에 따라 달라진다. 이번에는 새 리소스가 없으므로 병행 구성 비용을 발생시키지 않았다. 현재 기존 리소스 비용은 계속 발생한다.

## Microsoft 공식 근거

- [이름의 영속성·유일성 범위](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming)
- [Web Apps 업데이트 API](https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/update?view=rest-appservice-2024-11-01)
- [Plan 업데이트 API](https://learn.microsoft.com/en-us/rest/api/appservice/app-service-plans/update?view=rest-appservice-2024-11-01)
- [PostgreSQL 서버 업데이트 API](https://learn.microsoft.com/en-us/rest/api/postgresql/servers/update?view=rest-postgresql-2024-08-01)
- [기존 앱의 Plan 이동 조건](https://learn.microsoft.com/en-us/azure/app-service/app-service-plan-manage)
- [API 이름 확인](https://learn.microsoft.com/en-us/rest/api/appservice/check-name-availability/check-name-availability?view=rest-appservice-2024-11-01)
- [PostgreSQL 전역 이름 확인](https://learn.microsoft.com/en-us/rest/api/postgresql/name-availability/execute?view=rest-postgresql-2024-08-01)
