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

## 배포 결과

이 문단은 소스 공유 커밋 시점에는 **배포 전**이다. 실제 적용 후 배포 source SHA·암호화 backup hash·DB head·HTTPS/OpenAPI·PAUSED·설정 보존·권한/조회 검증을 추가 evidence commit으로 기록한다. 실제 Fabric emitter/운영 원천·B Worker·AI/RAG·Frontend/CORS 양성 연동·운영 효과는 미검증으로 남는다.
