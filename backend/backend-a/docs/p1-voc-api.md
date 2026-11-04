# P1 VOC 제안 API 및 실행 안내

기준: `77cba3a4892160eb2f8a1afc8f51b28a0f1282bb`. 신규 기능은 동기 생성이며 worker/정책 비교/프론트엔드는 포함하지 않는다.

## 실행 설정

Backend A 디렉터리에서 기존 고정 requirements-dev.txt와 Python 3.11+ 환경을 사용한다. 의존성이나 잠금 파일은 변경하지 않았다. 별도 로컬 테스트 DB와 기존 ignored 환경파일을 사용한다. 실제 비밀값은 Git에 넣지 않는다.

1. `python -m alembic upgrade head` → head `0009`, `python -m alembic check`로 metadata drift 없음 확인. 기존 0008 이후에 연결하며 기존 revision을 수정하지 않는다. VOC/P1 flag가 꺼져도 readiness는 0009를 요구한다.
2. `P1_ENABLED=true`, `P1_VOC_ENABLED=true`, `P1_VOC_PROVIDER=MOCK`으로 로컬 Mock 사용. 게시된 합성 analytics가 있어야 한다. 기존 최소 seed만으로는 analytics를 만들어내지 않으며 생성 결과가 INSUFFICIENT_DATA일 수 있다.
3. 활성 ADMIN에게 현재 SQL 팀 grant와 P1_VOC_READ/GENERATE/REVIEW를 역할별로 명시 부여한다. 자동 부여나 신규 권한 관리 API는 없다. 기존 monitoring grant 도구는 VOC 권한을 부여하지 않는다.
4. `python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`로 시작하고 기존 로그인 토큰을 Bearer로 사용한다.

| 환경변수 | 기본값/역할 |
|---|---|
| P1_VOC_ENABLED | false; VOC API 별도 opt-in |
| P1_VOC_PROVIDER | MOCK 또는 AZURE_OPENAI; 요청 body에서 바꿀 수 없음 |
| P1_VOC_AZURE_ENABLED | false; 실제 Azure 전송에 추가로 true 필요 |
| P1_VOC_AZURE_ENDPOINT | HTTPS Azure 리소스 origin; 경로/query/userinfo/port 금지 |
| P1_VOC_AZURE_API_KEY | 서버 측 비밀 환경변수; 응답/증거/로그에 저장하지 않음 |
| P1_VOC_AZURE_DEPLOYMENT | 모델 배포명; 서버 측 환경변수 |
| P1_VOC_AZURE_API_VERSION | 2024-10-21; JSON mode 지원 Chat Completions REST 배포 필요 |
| P1_VOC_TIMEOUT_SECONDS | 10초, 최대 30초; 자동 재시도 없음 |

Azure 실제 전송은 두 P1 flag, provider=AZURE_OPENAI, azure_enabled=true, 유효한 endpoint/key/deployment를 모두 설정한 뒤에만 가능하다. 허용 suffix는 `.openai.azure.com` 또는 `.cognitiveservices.azure.com`이고 리디렉션을 따르지 않는다. 플랫폼 HTTPS proxy/CA 신뢰와 TLS 검증을 유지한다. 이 작업에서는 실제 Azure 전송을 하지 않았다. 배포별 JSON mode/API 호환성과 실제 인증/네트워크 허용은 별도 연결 검증이 필요하다. 키를 채팅이나 프론트 VITE_ 변수에 넣지 않는다.

## API 계약

기본 경로 `/api/v1/admin/p1/voc-proposals`, 기존 Bearer·오류 봉투·X-Request-ID·no-store 사용. ADMIN 역할만으로 허용하지 않는다. 모든 제안은 생성 당시의 **전체 팀 집합**이 현재 활성 SQL grant에 포함될 때만 접근할 수 있다. 일부 팀을 잃어도 다른 팀의 제안 근거를 보여주지 않는다.

| 메서드/경로 | 권한 | 입력/결과 |
|---|---|---|
| POST 기본 경로 | P1_VOC_GENERATE | product_id UUID, team_ids UUID 배열(1–8, 중복 금지), Idempotency-Key(8–128). 최초 201, 동일 key/body 200 replay |
| GET 기본 경로 | P1_VOC_READ | product_id 선택, limit 1–100(기본20), cursor. created_at/request_id 내림차순 과거 요청 목록 |
| GET /{request_id} | P1_VOC_READ | 고정 근거·제안·생성 출처·상태·revision·검토 이력 |
| POST /{request_id}/reviews | P1_VOC_REVIEW | expected_revision>=1, decision APPROVED/REJECTED, 비공백 reason(최대500), Idempotency-Key. 200 |

생성 body 예시(해당 DB에 존재하고 범위가 허용된 UUID로 치환):

```json
{"product_id":"00000000-0000-0000-0000-000000000001","team_ids":["00000000-0000-0000-0000-000000000002"]}
```

검토 body:

```json
{"expected_revision":1,"decision":"APPROVED","reason":"근거를 확인했고 담당자 점검 실험 후보로 승인"}
```

`status`는 PENDING_REVIEW, APPROVED, REJECTED, INSUFFICIENT_DATA, FAILED 중 하나다. POST의 201은 **요청 이력 생성**이며 AI 성공을 의미하지 않는다. 반드시 status/proposal/reason_code를 확인한다. 부족한 근거는 INSUFFICIENT_DATA+proposal=null, 공급자 실패는 FAILED+proposal=null이다. 실패를 숨겨 Mock 결과로 대체하지 않는다. 실패/부족 상태는 검토할 수 없다. 재시도는 새 Idempotency-Key로 새 요청을 생성한다.

proposal은 최대5개 recommendations(title, action, evidence_ids)다. 허용 evidence ID는 risk/repeat/rate/trend이고 각 추천은 유효한 ID를 인용하며 응답 전체에 네 근거 종류가 있어야 한다. 서버가 실제 통계를 evidence에 저장하고 evidence_hash로 고정한다. AI 문구는 검토용 가설이며 확정 결함·원인·개선 효과나 데이터 사실로 취급하지 않는다. 참조 ID 검증은 문구의 의미적 진실성을 보증하지 않으므로 관리자 판단이 필요하다.

검토는 PENDING_REVIEW+일치 revision에 한해 1회 terminal 전이한다. 검토 이유·actor·시각을 남기며 원래 근거/제안은 수정하지 않는다. 승인 자체는 정책·지식·고객 발송·자동화 제어에 영향을 주지 않는다. 새 분석이나 재검토 후보는 새 요청으로 남긴다. 이력의 meta/is_current/stale은 **생성 당시**의 고정 값이며 현재 게시 상태의 보증이 아니다.

멱등 키는 기존 p1_idempotency의 (user, operation, key)를 재사용한다. 같은 body의 replay만 가능하고 key를 다른 body에 재사용하면 409다. replay에서도 현재 권한/팀 범위를 재확인한다. 생성과 검토 응답은 당시 snapshot으로 replay하며 최신 상태는 GET 상세로 조회한다. PostgreSQL actor row lock과 요청 revision 조건부 UPDATE로 중복 생성/검토를 제어한다. 동기 호출·DB commit이 한 요청에 묶이므로 공급자 호출 후 DB 장애가 발생하면 공급자 비용까지 정확히 1회임을 보장하지 않는다. 자동 외부 재시도나 background task/lease 엔진은 없다.

## 근거와 부족 데이터 처리

기존 analytics_views.resolve_snapshot/product_detail과 게시된 mart만 읽는다. 요청자가 기간·점수·원문·팀 범위를 임의 주입할 수 없다. 기간은 manifest의 recent/prior/sales/history windows 및 source_as_of/generated_at/published_at으로 표시한다. product 전체 KPI의 issue-tag 중복 행을 단순 합산하지 않는다.

- risk: 기존 위험도·band·data_status·rule_version. 관리 우선순위이며 결함률 아님.
- repeat: C(최근 VOC episode), M(가장 큰 primary-issue episode 수), K(고유 고객), top_issue와 M/C 집중도. 동일 고객 반복 접촉 횟수라고 주장하지 않음.
- rate: N(판매 cohort 내 불만 주문), S(전역 상품 유료 주문 28일), N/S, upstream raw_rate/smoothed_rate를 구분. 팀 주문 분모로 바꾸거나 문의 전체 ticket 비율로 표시하지 않음.
- trend: 기존 C/P/growth와 두 날짜 이상의 scoped VOC daily, 분석 windows. 없는 날짜를 임의로 0으로 채우지 않음.

미게시/정확한 scope 부재/설정 기준 stale/ELIGIBLE 아님/불완전 품질/표본(S<30 또는 C<5 또는 K<3)/raw_rate·상위 이슈 부재/서로 다른 일자 2개 미만이면 provider를 호출하지 않는다. 최소 표본 기준은 기존 analytics 검증과 같고 추세 가드는 추가로 보수적으로 적용한다. 부족한 값으로 개선 제안을 만들지 않는다.

근거 source LOCAL_SYNTHETIC/FABRIC와 provider MOCK/AZURE_OPENAI는 별개다. FABRIC은 upstream 선언이며 origin_verification=SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED, fabric_connection=UNVERIFIED를 유지한다. 실제 Fabric 연결 probe나 원천 재검증은 없다. Azure에는 aggregate facts와 기간/출처만 전송하며 팀·사용자 ID, cache fingerprint, 고객 원문, 검토 메모를 보내지 않는다.

## 오류와 관측 범위

401 인증/비활성 계정, 403 역할·권한·팀 거부, 404 접근 불가 또는 없는 리소스, 409 멱등 충돌·review revision/status 충돌, 422 잘못된 UUID/키/배열/검토 이유/추가 입력, 503 flag/config 비활성 오류를 기존 오류 봉투로 반환한다.

저장된 FAILED.reason_code는 AZURE_CALLS_DISABLED, AZURE_CONFIGURATION_REQUIRED, AI_RATE_LIMITED, AI_AUTHENTICATION_FAILED, AI_TIMEOUT, AI_UNAVAILABLE, AI_INPUT_TOO_LARGE, AI_INVALID_OUTPUT, AI_INCOMPLETE_OUTPUT, AI_EVIDENCE_REFERENCES_REQUIRED 등이다. 원시 공급자 오류/body/키는 저장·반환하지 않는다. 응답 최대64KiB, 요청 최대100KB, 추천 최대5개를 검증한다.

현재 VOC 이력은 동기 요청 테이블을 사용한다. 기존 p1_tasks/AI attempt writer를 만들지 않았으므로 **모니터링의 task/AI 계측 coverage는 기존처럼 미관측**이다. legacy task reason VOC_AND_POLICY_NOT_IMPLEMENTED는 task-backed producer/workflow 블록에만 해당하며 이번 동기 VOC API의 가용성 신호가 아니다. VOC 실행 결과는 이 API의 status/provider/reason_code로 확인한다. 기존 모니터링 응답 계약을 바꾸거나 수치를 실제 provider 집계처럼 채우지 않았다.
