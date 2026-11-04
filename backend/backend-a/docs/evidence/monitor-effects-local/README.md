# 0.11.0 / 0011 검증·배포 증거

2026-11-04 KST. 시작은 feature/backend-a / bd6727af8db1357cccf3126fbddccc46cc833adb, clean,0.10.0/0010이었다. 적용 AGENTS.md는 발견되지 않았다. 실제 계약은 [monitoring-effects.md](../../monitoring-effects.md)다. 기존0001–0010 불변, 다른 팀 작업 트리/코드·main·공용 잠금·새 유료 리소스를 변경하지 않는다.

## 이번 로컬 실행

전용 PostgreSQL16.15를127.0.0.1에 바인딩했고 각 테스트에 임의 schema를 사용했다. 실제 B/Fabric/모델/발송을 실행하지 않았다. 이전0.10.0의21/350/2를 재사용하거나 합산하지 않았다. [summary.json](summary.json)과 각 JUnit은 이번 실행이다. 실패 진단 속 합성 테스트 JWT는 공유 파일에서 제거했고 원래 실패 건수/시각/진단 의미는 유지했다. 실제 자격값은 기록하지 않는다.

| 실행 | 실제 결과 | 해석/보완 |
|---|---|---|
| initial.xml |27 passed /1 failed /skip0|보관 fixture가 최근/빈 자료라 보호 사유가 안 나옴. 오래된 합성 이력으로 보완 |
| corrected.xml |1 passed /실패0 /skip0|해당 보관 사례 재검증 |
| regression.xml |404 passed /5 failed /skip0|신규 및 품질/VOC/업무량/추천/응답 확정/analytics/후속/seed/보관/migration 회귀. 4개 HUMAN 재문의·1개 downgrade 기대 불일치 |
| command-contracts.xml |72 passed /6 failed /skip0|고객 명령/claim/generation/중지/패키지. 5개 같은 HUMAN 재문의 오류·1개 Git 패키지 cwd 오류 |
| additional.xml |3 passed /2 failed /skip0|새 HUMAN 회차 미라우팅의 scope 기대값, 잘못된 fixture 컬럼을 보완 |
| fixes.xml |73 passed /실패0 /skip0|신규/고객 명령/패키지 보완 후 확인 |
| regression-corrections.xml |10 passed /실패0 /skip0|실패한 기존 재문의/후속/직원 scope 회귀, 최신 downgrade 보호 기대, 복구 앱 확인 |
| final-new.xml |37 passed /실패0 /skip0|최종 신규 회차/효과/migration/actual PG 복구 호환 앱. 동시 게시·최종 lease 만료 재검사 포함 |
| release-guards.xml |5 passed /실패0 /skip0|정확한 Git 패키지,0011 유지 recovery readiness, 필수 백업/migration 없는 deploy 차단, 같은 행 수의 데이터 변경 fingerprint 탐지 |

같은 테스트가 여러 실행에 있으므로 합산하지 않는다. 광범위409개를 전부 PASS로 재표시하지 않는다. 발견한 HUMAN_CONTINUATION 문제는 이미 사람 경로인 재문의를 새 AUTO 이관으로 기록하려다 reason CHECK에 걸린 것이었다. 실제 고객 REQUEST_AGENT 구조화 사유에만 새 TRANSFER를 추가하도록 고쳤고 관련 기존 회귀와 신규 중복 방지를 다시 통과했다.0011 회차 history가 있으면 이전 followup downgrade guard에 도달하기 전에 거부하는 것이 맞아 테스트 기대를 최신 보호 경계로 조정했다. 구형0010 권한-only migration 테스트는0010까지만 inventory를 비교하고 그 뒤 최신head/metadata를 확인하도록 범위를 유지했다.

기존 TestClient/httpx deprecation warning이 있다. 추가 fixture의 UUID serializer 경고는 UUID 타입으로 수정했다. 의존성은 변경하지 않았다. Ruff(app/scripts/tests/migrations), 실제 OpenAPI/닫힌 DTO·서비스 auth·효과 예시 hash, migration 파일 graph0011, 원본0001–0010 및 기존 HTTP 경로 비교, diff·민감정보·명시 stage 검사를 수행한다. 기존 공통 response schema의 의도한 변화는 EffectAvailability reason의 additive 값뿐이며 embedded metrics=null은 유지한다.

## 배포 전 실제 Azure 확인

- 사용자 지정 구독/5dt-final-team1의 csflow-backend-a·csflow-backend-a-pg·csflow-backend-a-plan, 소유 태그·Korea Central 일치. 기존 B1/Standard_B1ms 유지. 새 리소스/요금제 변경 없음.
- HTTPS 앱 버전0.6.1/live·ready200, **실제 DB head0006·PAUSED=true** 확인. source0.10.0/0010과 차이가 있었다.
- PITR retention7일/earliestRestoreDate 제공 확인. 실제 PITR 새 서버 생성/복원은 하지 않았다.
- CORS=[]·서비스 허용 subject0·production·seed 비활성. 실제 Frontend origin/운영 Fabric subject를 추정하지 않는다.
- 다른 로그인 역할은 존재했지만 tickets/jobs UPDATE 권한이 없었고 조회 시 다른 활성 세션0이었다. 운영 writer 부재를 영구 보장한다고 표현하지 않는다. 새 DDL은 additive이며 기존 B job/ticket CHECK·lease·전이 엔진을 바꾸지 않고 lock_timeout5초로 충돌 시 실패/rollback한다.
- 기존 합성 ADMIN의 역할·활성/production 허용·scenario·단일 팀 정규화 scope를 읽기 확인했다. 실제 identity/비밀값은 공유 문서에 적지 않는다. 일반 계정/전체 팀 자동 grant는 없다.
- 운영자 IP 한 개의 독립 임시 규칙으로 읽었고 종료 시 제거했다. 초기 새 임시 규칙 이름이 구형 cleanup helper allowlist에 없어 해당 이번 소유 규칙만 직접 제거·부재 검증한 뒤, 새 release 도구의 자체 정리로 수정했다. 기존 규칙/공용 잠금은 수정하지 않았다. SCM basic read command는401이었으며 권한 설정을 풀지 않았다. 배포는 기존 Azure CLI/AAD 경로를 사용한다.

## 고정 소스 배포 준비와 복구

`scripts.azure_release`는 Git commit 바이트 allowlist로 release.zip을 만들고 SHA256/파일 manifest를 private cache에 보관한다. 운영 비밀·env·DB·cache는 패키지에 없다. 배포는 verified migration/암호화 백업 없이는 차단한다. native pg_dump custom/TOC·DPAPI decrypt roundtrip, 이전 모든 업무 테이블의 행 수+rowset hash 보존, 실제 API DB role의 신규 테이블 최소 DML을 확인한다. 계정 capability grant·seed·CORS/subject 변경은 자동으로 수행하지 않는다.

신규 이력 후 downgrade는 거부될 수 있으므로 DB downgrade를 복구로 가정하지 않는다. recovery.zip은2cb07cf의0.10 코드에서 version/readiness0011만 패치한 별도 산출물이다. **실제 격리 PG0011에 복구 앱을 기동해 ready200·미인증401**을 확인했다. Azure 장애가 발생하지 않은 상태에서 실제 복구/PITR 성공으로 주장하지 않는다.

## 실제 Azure 배포 결과 (2026-11-04)

- 고정 배포 소스: **646023067495f3a286a51585e60d758071a8404c**. 79개 Git 바이트 패키지 SHA256=`5c2bfd68dc19726ad6b0add69b39458395a7ea4ac3ef3ca00aa91135b77dc335`. Kudu 배포600f9130-a3ce-447b-93fe-84b4402bf029 complete/status4. 배포 후 OpenAPI는 고정 소스의 기록본과 전체 일치했다. 개별 remote main.py 경로는 압축 배포라404였으므로 원격 파일별 hash 검증 성공이라고 표현하지 않는다.
- 실제 DB **0006→0011**. 기존30여 업무 테이블의 행 수와 rowset hash가 전부 같고 PAUSED=true를 유지했다. 정확한 테이블/검산 결과와 암호화 backup hash/TOC·decrypt roundtrip은 [azure-summary.json](azure-summary.json)에 있다. 원본 backup은 operator 전용 private cache에만 있으며 공유하지 않는다.
- 새 테이블에 대한 기존 앱 DB identity의 SELECT/INSERT/UPDATE만 적용했다. seed/DB 초기화/기존 행 변경·다른 역할 grant·PAUSED 재개·다른 Worker 중지는 하지 않았다.
- 실제 HTTPS live/ready/docs/openapi 모두200, 버전0.11.0/DB0011 확인. 신규 직원 API 미인증5경로401. 기존 합성 ADMIN/AGENT/CUSTOMER 로그인200, 기존 고객 읽기200, **AGENT 본인 workload200**, capabilities200, 기존 analytics-v1은200 UNAVAILABLE/metrics=null이었다.
- 신규 ADMIN capability가 없으므로 업무량 팀/추천/VOC/품질/새 회차 진단·효과 조회403을 확인했다. CUSTOMER 차단/AGENT 추천403도 확인했다. 권한 있는 신규 ADMIN의 자료/지표 조회는 **Azure 미검증**이며 로컬 격리 증거와 구분한다. 허용 subject가 없어 효과 수신은503 ANALYTICS_SERVICE_AUTH_NOT_CONFIGURED였다(임의 서비스 JWT 발급/운영 게시 없음).
- 특정 기존 합성 ADMIN의 신규6 capability 영구 추가 요청은 **자동 승인 검토가 특정 identity grant의 명시 승인 근거 부족·읽기 대안 존재를 이유로 거부**했다. 해당 exec는 시작 전에 거부됐고 실제 staff grant0이다. 우회하지 않고 기존 권한의 HTTPS 읽기/차단만 검증했다. 실제 직원/테스트 identity의 추가 권한은 대상·허용 팀·capability를 명시한 별도 승인 후 필요하다.
- CORS=[]·서비스 subject0 및 기존 비밀/환경 설정 일치, PAUSED 유지. 실제 Frontend origin 불명으로 기존 설정을 보존했고 CORS 양성 연결은 미검증이다. 새 유료 리소스·요금제·공용 잠금/다른 팀 코드 변경 없음. 모든 이번 임시 DB 접근 규칙은 제거했다.
- 배포 실패가 없었으므로 실제 recovery/PITR는 실행하지 않았다.0.10+readiness0011 recovery 앱의 실제 격리 PG 호환 통과를 Azure 복구 성공으로 표현하지 않는다. 운영 통계에 섞일 자료 쓰기·공유 DB suite는 생략했다. 정상 로그인/조회/거부 감사만 추가됐다.

API base: https://csflow-backend-a.azurewebsites.net/api/v1
Swagger: https://csflow-backend-a.azurewebsites.net/docs
Readiness: https://csflow-backend-a.azurewebsites.net/health/ready

실제 Fabric emitter/운영 원천·B Worker·AI/RAG·Frontend/CORS 양성 연동·운영 품질/개선/부하 균형 효과는 미검증이다. 전향적 이력의 부분 수집과 안전 완료 운영 UNAVAILABLE를 유지한다. 수신/게시 코드와 합성 end-to-end만으로 외부 통합 완료라고 하지 않는다.

이번 소유 로컬 PostgreSQL은 테스트 schema0을 확인한 후 종료했다. 기존 다른 로컬 DB/cache/백업은 보존했다.
