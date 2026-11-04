# AUTO 회차 진단·VOC 전후 효과 계약 — 0.11.0 / 0011

전향적 기록과 별도 효과 게시를 추가한다. 기존 analytics-v1/티켓 생성 cohort KPI, 수동 품질 평가, VOC 계획, 업무량·읽기 전용 추천을 유지한다. 실제 B/AI/Fabric 통합과 운영 효과를 입증한 것은 아니다. Fabric 담당의 별도 Bronze 스키마 검토와 DB→Blob Export는 이 변경에 포함하지 않는다. 배포 결과는 [이번 증거](evidence/monitor-effects-local/README.md)에 로컬/Azure를 구분해 기록한다.

## 1. AUTO 회차 기록과 B 경계

- `automation_monitor_epoch`: migration0011 적용 시각(recording_since). 과거 ticket/audit 문구로 회차를 backfill하지 않는다.
- `automation_cycle_records`: `(ticket_id,cycle_no)` PK, 진입 mode/시각/revision/origin, 확인 가능한 원본 AUTO 회차 연결. A 신규 접수·재문의에 같은 transaction으로 추가한다. HUMAN 새 요청은 새 AUTO 분모가 아니다.
- `automation_cycle_events`: 원문 없는 append-only 사실. A 명시 route(처음 기록된 비NULL 팀을 성과 귀속으로 사용), 자동 응답 확정(message/job 참조), 고객 재문의/직접 이관을 같은 transaction으로 기록한다. 이미 이관된 원본 AUTO는 다시 이관으로 세지 않는다. 기존 HUMAN 경로의 재문의(HUMAN_CONTINUATION)는 새 이관으로 해석하지 않는다.
- B가 아직 호출하지 않는 경계는 추정 채우지 않는다. 기존 회차는 PRE_RECORDING_CYCLE_UNKNOWN이고, 현재 FAILED/HUMAN snapshot만 보이면 미보고 상태로 별도 표시한다. 그 상태를 과거 이관 시각·사유로 바꾸지 않는다. 재시도는 같은 회차 안의 사실이며 상담 분모를 늘리지 않는다.

실제 확인한 B는 `feature/backend-b@48283f31862d3e1791eb1976c47a6525e6e9212d`의 `backend/app/automation/postgres/job_retry.py`다. 최대3회/force_handoff·backoff, FAILED 보존 및 같은 회차 HUMAN/HANDOFF_PENDING/version+1은 **B 구현**이다. A는 이 엔진을 수정/복제하지 않는다. B의 성공 경로는 A 공통 `commit_automatic_reply`를 호출하므로 신규 A 전향적 응답 사실은 그 저장 경계에서 연결된다. 실제 배포 B 프로세스와의 통합은 미검증이다.

내부 Python 계약(HTTP 아님):

```python
from app.automation_monitor import WorkerOutcome, record_worker_outcome

# B: 기존 ticket→job 잠금을 잡은 동일 factory.begin() transaction.
# lease를 지우거나 job/ticket을 바꾸기 전에 호출한다.
fact = record_worker_outcome(session, WorkerOutcome(
    job_id=job_id, cycle_no=cycle_no, expected_revision=ticket_revision,
    lease_token=lease_token, worker_id=worker_id,
    automation_generation=generation,
    outcome="FAILED_HANDOFF", reason_code="RETRY_EXHAUSTED",
), service_id="backend-b")
# replayed=True이면 기존 사실 응답일 뿐 재실행 허가가 아니다. B 변경을 반복하지 않는다.
# 새 사실이면 B가 자신의 기존 FAILED/lease 해제/HUMAN 전환을 이 transaction에서 저장.
# caller가 commit한다. 분리 commit/먼저 lease 해제 후 호출은 지원하지 않는다.
```

RETRY/FAILED/FAILED_HANDOFF/HANDOFF를 지원한다. 사유는 RETRY_EXHAUSTED/POLICY/LOW_CONFIDENCE/OTHER/UNKNOWN의 구조화 코드뿐이다. error_code 문자열을 분석해 매핑하지 않는다. UNKNOWN을 허용하며 OTHER에 임의 원문을 붙이지 않는다. ticket/cycle/version/job expected version, RUNNING AUTO, lease token/owner/최종 wall-clock 만료, generation/PAUSED를 확인한다. PG 지연 제약은 commit 때 RETRY→job RETRY, 실패/이관→job FAILED·lease 해제, 이관→같은 cycle HUMAN/HANDOFF_PENDING/version+1을 요구한다. 기록만 commit하거나 다른 회차에 적용하면 전체 rollback한다. 상한3회는 B 정책이며 A가 강제하지 않는다.

멱등은 회차/사실 종류(RETRY는 attempt 포함)와 검증 command hash로 보장한다. 동일 기록 replay는 원래 사실만 반환하고 다른 command는 MONITOR_FACT_CONFLICT다. caller는 인증된 B 서비스/DB identity를 확정해야 한다. service_id 문법 검사 자체는 인증이 아니며 브라우저/임의 직원에 이 Python 함수를 노출하지 않는다. B가 현재 함수에 한 줄 연결하는 작업은 B 담당이다. 외부 API/실패·배정 실행기는 추가하지 않았다.

## 2. 회차 진단 API·지표

`GET /api/v1/staff/quality/automation-metrics`

ADMIN+QUALITY_METRICS_READ+현재 허용 활성 팀. `response_start/end` aware UTC(반열린 진입 기간), `team_ids` 반복, `origin=APPLICATION|SYNTHETIC|UNKNOWN`(기본APPLICATION), `include_unattributed=false`. 전역 미귀속/legacy 건수는 추가 QUALITY_UNATTRIBUTED_MANAGE가 필요하다. 범위 밖403, CUSTOMER/AGENT 차단. 한 REPEATABLE READ/as_of, 과거 as_of 요청422. 기간 최대93일·cohort 최대10,000건이며 초과는422(좁혀 재조회), 조용히 잘라 합계를 내지 않는다. 미귀속 제외 건수는 권한 밖 집계 없이null로 숨긴다.

| 항목 | 분자/분모·단위·기준 |
|---|---|
| auto_cycle_count | 기간에 **전향적으로 AUTO 진입이 기록된** ticket/cycle 수. origin·처음 명시된 귀속 팀의 현재 scope 적용. HUMAN 진입/legacy는 분모 제외 |
| automatic_reply_committed_count | 해당 AUTO 회차의 실제 확정 응답 사실 수. 정확성/안전 완료가 아님 |
| automatic_completed_count/rate | 확정 응답이 있고 현재까지 기록된 이관/실패 사실이 없는 AUTO 회차 / auto_cycle_count |
| transferred_count/rate | TRANSFER 사실이 있는 원본 AUTO 회차 / 같은 AUTO 분모. 고객의 새 HUMAN 회차/재시도를 다시 세지 않음 |
| transfer_reasons | 회차당 하나의 TRANSFER 구조화 reason. UNKNOWN도 별도 건수 |
| failed_fact_count | FAILED 사실을 가진 회차. 이관과 겹칠 수 있어 합산하지 않음 |
| statuses | TRANSFERRED→FAILED→AUTO_COMPLETED→RETRY_RECORDED→INCOMPLETE_OR_UNREPORTED 순 상호배타 집계. 합계=AUTO 분모 |
| unreported_current_terminal/human_state_count | 현재 같은 회차 snapshot은 종료 Job/HUMAN인데 대응 사실은 없는 건수. 과거 이관/실패 사실 집계와 합치지 않음 |
| legacy_current_auto_mode_untracked_count | 권한이 있을 때만 현재 AUTO mode·현재 회차 기록 부재 snapshot 수. 기간 cohort/당시 AUTO였다는 증거가 아니며 분모에 합치지 않음 |
| human_entry_count_excluded | 선택 가능한 기록 범위의 HUMAN 진입 수(미라우팅/미귀속은 별도 권한 없으면 포함하지 않음) |

모든 rate는 분모0→null. **관측된 사실의 부분 집계**이며 `recording_completeness=PARTIAL_OBSERVED_FACTS_B_REPORTING_NOT_ATTESTED`다. B 미연결/과거 부재로 완전 수집을 보장하지 않는다. 기존 `/admin/analytics/kpi`의 티켓 생성 cohort 비율과 한 그래프의 같은 분모로 합치지 않는다. API는 ID·원문·고객/주문을 반환하지 않는다.

안전 완료 DEV_SAFE_V1은 개발 제안이다. 확정 응답, 사람 평가(DEV_QUALITY_V1의 CORRECT 및 MATCH/명시 NOT_APPLICABLE), 확인 가능한 충분한 근거, 최소7일 경과, 이후 as_of까지 관측된 재문의/사후 이관 부재와 보고 완전성을 분리한다. A 신규 명령의 관측 범위 밖/B 보고 완전성은 UNKNOWN이므로 운영 `safe_completion.rate=null`, UNAVAILABLE/OPERATIONAL_RULE_AND_B_OBSERVATION_NOT_AGREED를 유지한다. UNREVIEWED·판단 불가/부정·OBSERVATION_IMMATURE·INCOMPLETE_OBSERVATION·관측된 사후 문제·가상 조건 완비 시 잠정 상태를 합성 시나리오로 검증했다. 잠정 상태는 운영 안전 입증/전체 AI 정답률이 아니다. AI 자기 점수는 사용하지 않는다.

## 3. 별도 VOC 효과 배치 계약

기존 analytics-v1 batch/4개 mart/현재 pointer는 변경하지 않는다. 효과는 `voc_effect_batches`(plan FK·불변 payload/hash·검증 상태)와 `(action_id,plan_revision,origin)`별 `voc_effect_publication` pointer를 사용한다. 한 배치=한 상품 개선 계획·고정 scope 결과다. [완전한 합성 요청](examples/voc-effect-batch.json), [OpenAPI](openapi.json).

| 실제 HTTP | 인증·행위 |
|---|---|
| POST `/api/v1/analytics/voc-effects/batches` | 기존 별도 서비스 issuer/audience/key+허용 subject+`voc-effects:receive`. batch_id/payload/payload_sha256 |
| GET `.../batches/{batch_id}` | receive 권한, 상태/검증 코드만 |
| POST `.../batches/{batch_id}/validate` | receive 권한, 산술·키·범위·hash/exact scope 검증 |
| POST `.../batches/{batch_id}/publish` | `voc-effects:publish`, 재검증과 원자 pointer 게시 |
| GET `/api/v1/staff/voc-improvements/{action_id}/effects` | ADMIN+VOC_IMPROVEMENT_MANAGE+현재 조치 및 해당 계획 전체 비교 scope. 선택 plan_revision, origin 기본OPERATIONAL |

브라우저 사용자 JWT로 수신/게시할 수 없다. 서비스 subject와 permissions는 별도이며 기존 analytics:receive/publish만으로 효과 게시를 허용하지 않는다. OPERATIONAL의 수신·게시에는 추가 설정 `VOC_EFFECT_OPERATIONAL_IDS`에 명시한 subject만 허용한다. 기본빈값/실제 자동 설정·grant 없음. SYNTHETIC은 별도 pointer이며 기본 운영 조회에 나오지 않는다. 실제 Fabric emitter가 없는 상태에서 운영 origin으로 합성 자료를 게시하지 않는다.

payload는 voc-effect-v1, action/product/issue/plan revision, 정확한 team UUID 집합·시행일·4개 기간 경계, source_as_of/generated_at, before/after 정의 버전, overlap 선언, 문의/판매 건수·각 coverage·문의율, count/rate 절대/상대 변화를 담는다. 실제 계획과 경계·상품·문제·scope가 같아야 하고 동일 길이/비중첩/UTC를 검사한다. 미래 generated_at 허용 유예5분, source_as_of≤generated_at. 출처 URL/원문/고객·티켓 ID는 wire에 없다.

Fabric이 계산한 값을 저장하며 A는 산술을 검산한다(Decimal 오차허용1e-9). 문의 count coverage=1·판매 coverage=1·양수 판매가 확인된 기간에만 inquiries_per_sale=문의/판매를 받는다. 판매 없거나0이면 문의율은null. 양쪽 완전 문의 건수가 있고 정의가 같으면 count delta/relative를 검산하며 before0의 relative는null. 양쪽 rate가 있을 때만 rate delta/relative를 검산한다. 정의 변경·자료 부족은 비교값null, 데이터 미성숙/0분모/판매 없음/overlap POSSIBLE 또는 UNKNOWN을 상태 코드로 표시한다. source_as_of가 after_end보다 이르면 OBSERVATION_IMMATURE이며 시간이 지났다고 결과를0/성공으로 바꾸지 않는다. 새 결과를 다시 제출해야 한다. overlap=NONE_REPORTED는 upstream 선언일 뿐 다른 조치 부재의 독립 입증이 아니다.

같은 batch ID/같은 canonical payload hash는 원래 상태, 다른 내용409. 수신/검증/게시 모두200이며 `validation.passed/status`를 확인한다. 잘못된 scope·상품·산술은 FAILED이며 수정본은 새 batch ID다. validate 후 계획이 바뀌면 게시409이고 현재 pointer는 유지한다. source_as_of/generated_at은 각각 비감소+한쪽 증가만 허용, 늦은 배치409, 과거 성공 replay는 재승격하지 않는다. 한 profile 잠금→batch 잠금 순서와 게시 savepoint/감사로 부분 저장을 막는다. PostgreSQL은 payload·실패/성공 receipt 불변 및 pointer의 성공 배치/계획/origin 일치를 추가 검증한다.

조회는 게시 결과 없으면 UNAVAILABLE/NO_PUBLISHED_EFFECT_BATCH, payload=null이다. 명시 과거 plan 조회는 현재 그 계획 권한이 있어야 하며 plan_is_current=false다. 현재 담당 팀이 바뀌고 계획 재확인이 없으면 UNAVAILABLE/PLAN_RECONFIRM_REQUIRED다. 기존 VOC 상세의 embedded analysis.metrics=null은 유지하고 reason에 VERSIONED_EFFECT_ENDPOINT_REQUIRED를 추가했다(기존 reason도 schema상 허용). 새 수치는 반드시 `/effects`에서 읽는다. `causal_effect=NOT_ESTABLISHED`, `validation_scope=STRUCTURE_HASH_ARITHMETIC_NOT_SOURCE_TRUTH`를 표시한다.

## 4. 배포/연동·보관

0011은 새5테이블/인덱스/FK/CHECK/불변·지연 검증 trigger만 추가하고 기존0001–0010은 불변이다. 기존 업무/grant를 보존하며 회차 backfill/실제 계정 자동 grant는 없다. 새 history가 있으면 downgrade 거부; DB downgrade를 복구 수단으로 쓰지 않는다. seed의 공식22테이블 제외 allowlist와 retention dry-run에 새 history/참조 보호를 추가했다. TEAM은 새 전역 history inventory의 숨긴 건수를null로 유지한다. 실삭제 없음.

`scripts.azure_release`는 기존 A 리소스 소유/구독/region·설정/PAUSED·writer 상태 확인, 현재 operator IP 한 개의 독립 임시 규칙, 암호화 pg_dump/TOC/DPAPI roundtrip, lock_timeout5초의 누적 additive migration, 실제 앱 DB identity의 **새 테이블 DML만**, 정확한 Git SHA 패키지·일반 deploy·HTTPS/실제 head 검증을 제공한다. 구형 provision/configure/bootstrap/seed를 호출하지 않는다. 설정/CORS/서비스 subject와 공용 잠금은 보존한다. 별도 승인 없는 계정 capability grant는 이 스크립트에 없다. 역할이 존재해도 writer가 없다고 단정하지 않고 현재 세션·새 schema의 이전 writer 호환성을 함께 검토한다.

백업은 private `.cache/azure-release-0110/pre-release.dump.dpapi`이며 공유하지 않는다. PITR은 별도 새 리소스 복원/유료 작업 승인이 필요하므로 이번에 실행하지 않는다. 코드 복구는 검토된0.10 소스의 readiness0011/version만 패치한 recovery.zip을 사전 검증해 새 schema를 유지한 채 사용한다. 복구 중 전향적 기록 공백이 생기면 완전 수집이라고 표현하지 않는다. 운영 DB 실복구 훈련은 별도이며 로컬 호환 검증과 구분한다.

Frontend 담당은 신규 지표의 부분 수집·분모·null/UNAVAILABLE와 효과 origin/경고/plan revision을 표시한다. Backend B 담당은 같은 transaction의 사실 기록 호출과 구조화 reason을 연결한다. AI/RAG는 실제 provenance·당시 근거를 제공하고 운영 rubric/관찰 규칙은 운영 책임자와 합의한다. Fabric 담당은 별도 voc-effect-v1 emitter/단위·상품 매핑·동일 기간·scope·판매 분모·coverage·겹침 선언을 연결한다. 실제 연동/효과 확인 전에는 통합 완료라고 보고하지 않는다.
