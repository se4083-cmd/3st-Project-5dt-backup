# AI 품질·VOC 개선·업무량/SLA 확장 설계안

후속0.10.0/0010 로컬: **읽기 전용 업무량 기반 배정 추천**을 구현했습니다. [실제 계약](assignment-recommendations.md)을 우선합니다. B의 배정 실행/실패·HUMAN 전환, 팀 잠금·용량 엔진·Fabric/Export는 여전히 미구현/별도 담당입니다. 품질0.9.0은 먼저30fbfff로 공유했으며 이번 추천0.10.0은 후속 공유 대상입니다. Azure 배포는 포함하지 않습니다.


후속 **0.9.0/0009**에서 이번 최소 범위의 전향적 응답 기록·수동 표본/평가 이력·현재 snapshot 지표를 로컬 구현했습니다. [실제 계약](quality-review.md)이 아래 제안보다 우선합니다. ticket_cycles·과거 as_of·안전한 자동 완료·새 SLA·AI 호출/자기평가·Fabric 품질 mart는 여전히 미구현입니다.


후속 0.8.0/0008: **2단계 상품 개선 profile·append-only 계획·문의 연결을 로컬 구현**했습니다. [실제 계약](voc-improvements.md)을 우선합니다. 효과 분석 수신/계산/조회는 아직 미구현이며 UNAVAILABLE/EFFECT_INTEGRATION_NOT_IMPLEMENTED, metrics=null입니다. 아래 설계 당시/과거 검증 기록과 구분합니다.

공유본에서는 개인 PC의 절대 경로를 `<PROJECT_ROOT>`로 표시한다. 후속0.7.1은 업무량의 미배정 의미와 경로별 분류를 보완했으며 [현재 계약](workload.md)을 따른다. 나머지 기능의 제안 범위는 그대로다.

작성일: 2026-11-04 KST. 후속 갱신: **첫 단계인 현재 업무량 조회를 로컬0.7.0/head0007에 구현**했다. 실제 API·권한·응답·검증은 [업무량 계약](workload.md)을 따른다. 아래 1절·5.3절은 설계 당시0.6.1/0006 확인 기록이다. 설계 당시 품질 평가·추천은 제안이었으며 현재 구현 상태는 위0.9.0/0.10.0 계약을 따른다. 새 SLA/analytics-v2/Export는 미구현이다. VOC profile/계획은 위0.8.0 계약을 따른다. 당시 검증에서는 Azure·실제 계정 권한·commit/push를 변경하지 않았다.

## 1. 설계 당시 구현 확인 (0.6.1 / 0006)

### 1.1 기준점과 확인 한계

| 항목 | 이번에 확인한 사실 |
|---|---|
| 프로젝트 루트 | `<PROJECT_ROOT>` |
| 실제 Git 루트 | `<PROJECT_ROOT>\.cache\team-cs-flow-ai` |
| 담당 폴더 | 위 Git 루트의 `backend/backend-a/` |
| origin | `https://github.com/InSSOOO/cs-flow-ai.git` |
| 브랜치 | `feature/backend-a` |
| 로컬 최신 HEAD | `447c31890c243e1175b805596a84a19720058edf`, 2026-11-02 18:00:24 +09:00, `feat(backend-a): add backend 0.6.1 and local validation` |
| 앱 버전 | [pyproject.toml](../pyproject.toml), [app/main.py](../app/main.py)의 `0.6.1` |
| migration graph | `base → 0001 → 0002 → 0003 → 0004 → 0005 → 0006`; 로컬 `python -m alembic heads` 출력 `0006 (head)` |
| 적용 AGENTS.md | 담당 폴더와 docs를 포함한 하위 경로, Git 루트와 프로젝트 및 드라이브 루트까지의 부모 경로에서 발견되지 않음 |
| 미커밋 상태 | 검토 시작 시 tracked 수정 13개, `git status --short` 기준 untracked 항목 14개(디렉터리는 한 항목). 기존 변경은 아래와 같음 |
| 원격 최신 여부 | `git ls-remote origin refs/heads/feature/backend-a`는 `Could not resolve host: github.com`으로 실패. 원격과 같다고 보장하지 않음. fetch/pull/브랜치 전환 없이 **로컬 HEAD + 현재 미커밋 코드**를 기준으로 설계 |
| 실행 환경 확인 범위 | DB에 연결하지 않은 소스·로컬 Git·migration 파일 graph 확인. Azure의 현재 버전, DB 적용 revision/행, B·AI·Fabric 가동 상태는 이번에 확인하지 않음 |

기존 수정 13개: `README.md`, `app/main.py`, `startup.sh`, `docs/api-contract.md`, `docs/azure-deployment.md`, `docs/backend-a-handoff.md`, `docs/backend-b-contract.md`, `docs/backend-b-handoff.md`, `docs/fabric-contract.md`, `docs/fabric-handoff.md`, `docs/frontend-handoff.md`, `docs/openapi.json`, `docs/verification.md`.

기존 미추적 항목: `app/public_limits.py`, `docs/azure-migration.md`, `docs/azure-naming-review.md`, `docs/evidence/azure-migration/`, `docs/evidence/azure-team-dev/`, `docs/examples/azure-settings.names.json`, `docs/fabric-data-contract/`, `scripts/__init__.py`, `scripts/azure_bootstrap.py`, `scripts/azure_deploy.py`, `scripts/azure_migrate.py`, `scripts/azure_verify.py`, `tests/test_azure_deployment.py`, `tests/test_azure_migration.py`.

이 변경의 작성자를 추정하지 않는다. tracked diff와 미추적 코드·계약을 함께 읽었다. 특히 production의 `PublicLimits`, 429/413, HSTS, 실제 analytics 경로·범위 계약을 새 API 설계에 반영한다. 커밋 하나만의 검토 결과가 아니다. 동일 목적의 품질 평가·VOC 개선 효과·업무량 통합 설계 문서는 발견되지 않아 기존 `docs/phase*.md`와 같은 docs 계층에 이 문서를 추가했다.

### 1.2 인수 내용과 대조한 결과

버전/head 및 사용자가 제시한 인수 내용과 다른 구현은 발견하지 못했다. 다음은 새 요구사항과 대조해 확인한 중요한 세부 사항이다.

1. **상품 단위 후속은 이미 지원한다.** `followup_actions`는 ticket 또는 product 중 하나를 대상으로 한다. 상품 후속은 ADMIN이 만들고, 소유자는 해당 팀의 활성 ADMIN 또는 미지정만 가능하다. 일반 AGENT를 상품 개선 담당자로 바로 지정할 수 없다. 상품 후속은 티켓 해결을 막을 수 없다.
2. **SLA 저장값은 이미 있지만 SLA 엔진은 없다.** 접수와 재문의/사람 요청에서 `sla_due_at = now + 24시간`으로 설정한다. 새 회차에서 `first_replied_at`, `resolved_at`을 비우며 기한도 다시 설정한다. 업무시간·휴일·일시 정지·최초 응답/해결별 기한은 구현돼 있지 않다.
3. **품질 확인용 직원 상세는 평가 기능이 아니다.** `QUALITY_REVIEW` 목적은 현재 ADMIN만 허용하고 기존 ticket scope를 적용한다. draft/원문을 반환하지 않는 allowlist 조회다. 종료된 티켓은 기존 AGENT 접근 정책으로 볼 수 없으므로 상담사 표본 검토를 이 API만으로 구현할 수 없다.
4. `ai_suggestions`, `approvals`, 정책/규칙 버전 필드는 있으나, 실제 A 요청 처리에서 제안·승인을 생성하고 자동 최종 응답과 연결하는 엔진은 없다. seed/합성 자료와 실제 생성 기록을 구분한다. `confidence`, gate 통과, 승인, 자동 완료는 사람의 정답 판정이 아니다.
5. 실제 Gold 경로는 `/api/v1/analytics/batches` 계열이다. `claim_jobs`, `commit_automatic_reply`, `record_queue_route`, `lock_resolution_gate`는 **Python 함수**다. B를 위한 HTTP API가 아니다.
6. DB→Blob 운영 Export는 미구현이다. Gold 수신·검증·원자 게시 코드는 있고 실제 Fabric 연결 성공은 이번에 검증하지 않았다. `analytics-v1`은 고정 4개 mart만 수신하며 임의 필드를 추가할 수 없다.
7. 현재 `analytics_views.operational_kpi`는 재문의·승인·검토·SLA를 unavailable로 반환한다. 원시 mart 컬럼이 있다는 이유로 그 지표가 구현·합의됐다고 해석하지 않는다.
8. 현재 로컬 팀 체크아웃에 `backend/backend-b`는 없다. B의 별도 SQLite 코드나 실제 실행 상태는 검토하지 못했으며 과거 설명만으로 호환된다고 판단하지 않는다.

### 1.3 요청별 재사용 근거

아래 경로는 담당 폴더 기준이며 함수·테이블은 현재 실제 코드의 이름이다.

| 요청 | 기존 구현 | 부분 구현 / 한계 | 신규 필요 | 근거 |
|---|---|---|---|---|
| A 응답·작업 추적 | message/cycle, final OUT 회차당 1건, job 회차당 1건, lease/version/generation fence | 메시지에 ticket revision/job/suggestion 직접 연결 없음. job의 attempt·상태는 현재값이며 시도 이력 아님 | 응답 생성 근거의 불변 연결, 사람 평가·수정 이력 | [models.py](../app/models.py): `messages`, `automation_jobs`, `ai_suggestions`, `approvals`; [model_constraints.py](../app/model_constraints.py): `uq_messages_final_cycle`; [finalization.py](../app/finalization.py): `AutomaticReply`, `commit_automatic_reply` |
| A 정책 근거 확인 | 문서 policy_key/version/hash, 규칙 rule_key/version, prompt/model 버전, evidence_refs | JSON과 현재 문서 대조는 가능하나 실제 확정 답변이 그 제안인지 보장 못함. 문서 본문 불변성·검색 index/chunk 버전 보장 없음 | 생성 당시 version/hash/context 참조. 누락은 UNKNOWN | [staff_detail.py](../app/staff_detail.py): `evidence`, `proposal_fact`, `detail`; [models.py](../app/models.py): `knowledge_documents`, `automation_rules` |
| A 자동/이관 현황 | 최종 메시지, job_kind/reason_code/error_code, 회차 변경 감사 | snapshot만으로 모든 과거 전이·이관 원인을 복원 불가. audit payload는 `{}`. 고객 사람 요청과 엔진 이관 원인은 별개 | 전향적 회차 기록·정형 이관 사유. 기존 cohort KPI는 그대로 | [jobs.py](../app/jobs.py): `claim_jobs`; [ticket_commands.py](../app/ticket_commands.py): `change_cycle`; [audit.py](../app/audit.py): `record`; [analytics_views.py](../app/analytics_views.py): `operational_kpi` |
| B 개선 업무 관리 | product 후속 CRUD, owner/team/status/kind/notes/due_at/version, 감사·멱등 | 실제 시행일·문제 분류·비교 기간·분석 결과 연결·변경 내용 이력 없음. completed_at은 시행일 아님 | product 후속의 1:1 개선 profile, 계획 revision, 참조 링크 | [followups.py](../app/followups.py): `create`, `mutate`, `owner_valid`, `scope`; [followup_schemas.py](../app/followup_schemas.py); [operations_router.py](../app/operations_router.py) |
| B VOC 분석 | TOP10/상품 추세/미대상 원인, scope별 batch pin, Gold 검증·게시 | 최근7일 추세와 판매28일 분모는 임의 조치 전후 비교와 다름. product_daily에 팀 차원 없음, issue_tag 행 중복 가능 | Fabric의 조치별 비교 mart와 versioned wire | [analytics_service.py](../app/analytics_service.py): `receive`, `validate`, `publish`; [analytics_validation.py](../app/analytics_validation.py): `validate_submission`; [analytics_views.py](../app/analytics_views.py): `resolve_snapshot`, `product_detail` |
| C 배정/미배정 | 현재 유효 배정 판정, 팀 scope/category, route revision, 예외 큐 | 큐는 전체 상담사 업무량 목록이 아님. FAILED는 배정 유무와 무관하게 큐에도 나올 수 있음. queued_at은 SLA 시작시각 아님 | 상담사별 distinct 업무량, 미배정 조회, 설명 가능한 추천 | [repository.py](../app/repository.py): `agent_assignment_exists`, `ticket_scope`; [exception_queue.py](../app/exception_queue.py): `queue_query`, `view`, `record_queue_route` |
| C SLA | ticket.sla_due_at/first_replied_at/resolved_at, assignment 시각, followup.due_at | 현재 회차 snapshot 위주. 과거 회차의 시작·기한·첫 응답을 모두 보존하는 테이블 없음 | 우선 기존 기한의 상태 표시; 합의 후 회차별 SLA 기록 | [services.py](../app/services.py): `submit_ticket`; [ticket_commands.py](../app/ticket_commands.py): `change_cycle`; [finalization.py](../app/finalization.py) |
| 공통 | RBAC/고객 소유권, 정규화 scope, 최소 감사, REPEATABLE READ, 서비스 JWT | 새 capability는 기존 permission CHECK에 없음. 신기능의 보관 참조도 아직 없음 | 명시적 권한 추가·전향적 보관 보호 설계 | [dependencies.py](../app/dependencies.py): `get_snapshot_session`; [staff_models.py](../app/staff_models.py): `staff_permissions`; [analytics_auth.py](../app/analytics_auth.py); [retention.py](../app/retention.py) |

관련 기존 문서: [B 계약](backend-b-contract.md), [B 인수](backend-b-handoff.md), [후속 설계](phase3-followups-customer360.md), [분석 설계](phase4-analytics.md), [직원 큐·중지](phase6-staff-queues-control.md), [보관 preview](phase7-retention-preview.md), [Fabric 자료](fabric-data-contract/README.md), [Export 제안](fabric-data-contract/export-contract.md), [생명주기 기록 한계](fabric-data-contract/lifecycle-events.md).

## 2. 최소 구현안

### 2.1 A — AI 상담 품질 평가·모니터링

**최소 기능:** 관리자가 실제 자동 최종 응답 표본을 지정하고, 지정된 상담사/관리자가 관련 질문·응답·당시 정책 근거만 보고 정확성 및 정책 근거 일치를 평가한다. 화면에서 응답 생성 당시 자료와 현재 자료를 구분한다. 재평가 때 기존 판정을 덮어쓰지 않고 새 revision을 남긴다.

재사용: 기존 최종 응답 저장 gate, messages, 제안·정책 version/hash, 정규화 팀 scope, 목적별 열람 감사, snapshot 조회. 추가: `automatic_reply_records`, `quality_samples`, `quality_review_revisions` 및 제한된 품질 자료 조회. 운영 화면의 평가 건수 집계는 A의 정형 기록 합산이며 AI 판정을 재계산하지 않는다. 장기 Silver/Gold 집계는 이후 Fabric에 같은 정의로 연결한다.

평가 대상은 **실제 확정된 PUBLIC OUT final 메시지 한 개**다. suggestion 자체를 평가한 결과를 발송/확정 답변의 평가로 대체하지 않는다. 확정은 DB 저장 완료를 뜻하며 실제 외부 전달 성공과도 구분한다. 초안 평가가 필요하면 별도 대상 종류·지표로 추후 분리한다.

응답 식별자는 `message_id`, 업무 회차는 `ticket_id + cycle_no`, 입력 동시성 값은 확정 전 ticket.version, 결과 revision은 확정 후 ticket.version이다. `ai_suggestions.revision`은 **제안 revision**으로 별도 필드다. 응답 provenance는 job/suggestion/approval 참조와 당시 hash·정책 버전을 연결한다. 같은 최신 티켓에 있다는 이유로 과거 응답에 최신 제안을 붙이지 않는다.

기존 writer도 동작하도록 새 provenance 입력은 단계적으로 optional로 시작한다. A가 실제 job/message/cycle/revision 연결은 같은 확정 transaction에서 기록하고, B가 제공하지 않은 AI/RAG 자료는 `MISSING`으로 둔다. 링크가 전달됐는데 불일치하면 거부한다. 기존 성공 응답과 과거 평가 가능 표본을 구별하며, 자료 없는 응답도 표본 후보 수와 미평가 수에서는 숨기지 않는다. 모든 writer가 계약을 지원한 뒤에만 strict 모드를 논의한다.

**평가 권한:** 기존 `ticket_scope`를 넓히지 않는다. `QUALITY_REVIEW` capability + 배정된 표본 + 현재 활성 팀 scope로 **해당 표본 자료만** 보게 하는 별도 경계를 만든다. ADMIN의 표본 관리에는 `QUALITY_SAMPLE_MANAGE`를 추가한다. 종료 티켓을 AGENT가 일반 상세/고객360으로 탐색하게 만들지 않는다. 자동 미귀속 응답은 권한 없는 전체 큐로 풀지 않고 별도 `QUALITY_UNATTRIBUTED_MANAGE`를 가진 ADMIN이 자신의 허용 팀 중 검토 책임 팀을 명시한다. 이 권한은 기본 미부여이며 큐 권한으로 대체하지 않는다. 그 지정은 운영 ticket.team_id나 실적 귀속을 바꾸지 않는다. 팀별 품질 지표와 검토 업무별 지표도 서로 다른 집합으로 표시하며 검토 책임 팀을 자동 실적 팀으로 사용하지 않는다.

하나의 message/rubric에 공식 표본 1개, 공식 최신 평가 1개만 집계한다. 수정은 같은 표본 revision을 올리는 행 추가이며 변경 사유·평가자·시각을 남긴다. 담당 변경·무효화도 이력으로 남긴다. 집계는 as_of 이전의 마지막 유효 REVIEW를 찾고, REASSIGN만으로 그 판정을 지우지 않는다. VOID 이후에는 집계에서 제외한다. 과거 as_of 조회는 그때의 이력과 당시 상태를 사용하며 현재 담당 정보를 과거에 덮어씌우지 않는다. 여러 독립 평가자의 투표/합의 점수는 최소 범위에 넣지 않는다. 기존 approval은 평가가 아니고 독립 평가 여부는 원래 승인자 등 확인 가능한 참조로 서버가 판정하며 확인 불가하면 unknown이다.

**자동 완료 ≠ 정답 ≠ 안전한 자동 완료.** 정확성은 사람의 CORRECT/INCORRECT 판정 건만, 정책 일치는 MATCH/MISMATCH 판정 건만 각 비율 분모로 삼는다. 미평가·판단 불가·비적용을 따로 공개한다. 표본 선택 방법과 coverage도 표시해 표본 정답률을 전체 정답률로 일반화하지 않는다. AI confidence/자기평가는 참고값이며 객관적 정답률에 사용하지 않는다.

‘안전하게 자동 완료’는 최소 ① 사람 검토 결과 ② 평가 rubric ③ 응답 이후 관찰창 W ④ 재문의·사후 이관 관측 범위 ⑤ 이벤트 coverage가 확정돼야 계산할 수 있다. 임시 제안 W=7×24시간이지만 팀 승인 전 `UNAVAILABLE/DEFINITION_NOT_AGREED`를 유지한다. 별도 새 티켓으로 온 재문의나 실제 발송 장애까지 탐지하는 기능은 현재 없다. 관찰창 미성숙·관측 누락을 안전 성공으로 취급하지 않는다.

### 2.2 B — VOC 개선 조치·효과 추적

**권고: 기존 상품 followup + 1:1 개선 profile.** 이미 product 대상 업무·owner·status·due_at·revision·감사·멱등이 있어 별도의 독립 action CRUD를 만들면 같은 업무의 담당·상태가 이중 관리된다. 새 profile은 문제 분류·개선 내용·실제 시행일·비교 계획만 보유하고 업무 상태는 followup을 사용한다. 기존 티켓 followup에는 적용하지 않는다.

상태는 기존 OPEN → IN_PROGRESS → DONE/CANCELLED를 유지한다. DONE은 조치 업무 완료이며 효과 입증/관찰 완료를 뜻하지 않는다. 실제 시행일 `implemented_at`은 별도이며 `completed_at`이나 `due_at`으로 추정하지 않는다. 담당 미지정은 팀 대기이며 현재 정책상 상품 담당자는 ADMIN만 가능하다. AGENT를 상품 개선 담당자로 허용하려면 별도 권한·소유권 정책 확장이 먼저다.

최초 등록은 새 개선 wrapper가 product followup 생성 로직과 profile을 **한 transaction**으로 저장한다. 기존 followup을 개선 조치로 등록하는 경로도 제공한다. 기존 `/staff/followups`로 만든 일반 상품 업무는 자동으로 개선 조치로 분류하지 않는다. 재사용할 검증·영속화 부분은 내부 서비스로 분리하고 기존 HTTP를 내부 호출하지 않는다. 새 wrapper는 확장용 receipt를 쓰며 기존 `followups.create`의 고정 operation/receipt를 중복 기록하지 않도록 구현 경계를 분리한다. 후속 메모를 parsing해 시행일/문제 유형을 추출하지 않는다. 개선 내용은 profile의 제한된 업무 텍스트를 정본으로 두고 internal_note와 양방향 동기화하지 않는다.

관련 티켓은 참조 테이블로 연결하되 조치와 티켓을 각각 권한 검사한다. 다른 팀 티켓·고객 식별자를 노출하지 않는다. 발견 출처인 `batch_id + scope_key + product_id`를 저장하고 현재 게시가 바뀌어도 유지한다. TOP10에서 내려가도 조치는 유지한다. 등록 당시 순위는 제공된 분석의 관측치이며 결함 확정 증거가 아니다.

시행 전 `[implemented_at-L, implemented_at)`과 시행 후 `[implemented_at, implemented_at+L)`처럼 동일 길이의 창을 고정한다. 기본 제안 L=14×24시간, 시행시각은 실제 timestamp 그대로다. KST 일별 집계를 쓸 경우 시행시각을 임의 자정으로 반올림하지 않고 Fabric이 지원하는 완전 일자 경계/제외 일자 및 지연효과 간격을 별도 합의한다. 명시된 두 창의 길이는 같아야 하고 overlap은 금지한다.

판매 원천이 양 창 모두 완전하고 동일 상품·기간·정의·scope와 대응하면 판매량 대비 문의율을 비교한다. 최소 제안은 **중복 제거한 문의 주문 수 / 유효 유료 주문 수**, 즉 주문 건수 기준이며 판매 수량당 지표와 다르다. 수량을 쓸 경우 별도 분모 정의가 필요하다. 매출액/수량/주문 수를 혼용하지 않는다. 양쪽 중 하나라도 판매 자료 누락이면 **문의 건수 변화**로만 비교하고 문의율은 null이다. 판매 0은 결측과 다르며 문의율은 분모 0으로 계산 불가다. 변화율의 이전 값이 0이면 상대 변화율도 null, 절대 변화만 제시한다.

Fabric이 문의 중복 제거·분류·판매 cohort·전후 수치·변화를 계산한다. A는 입력 범위, 분모/카운터/기간/해시 등의 정합성과 현재 권한을 검증하고 게시 결과를 조회한다. 기존 TOP10 점수/7일 대 7일/28일 판매창을 개선 효과로 재해석하지 않는다. A가 새로운 VOC 계산 배치나 스케줄러를 만들지 않는다.

결과는 ‘시행 전후 관측 변화’로 표기한다. 캠페인·계절·판매량 변화·다른 조치·분류 변경 등 교란을 제거한 인과 추정은 아니다. `LOW_SAMPLE`, `OBSERVATION_IMMATURE`, `SOURCE_INCOMPLETE`, `OVERLAPPING_ACTIONS`, `SCOPE_CHANGED`, `PRODUCT_ID_MISMATCH`, `DEFINITION_CHANGED`를 정형 표시한다. 중첩 조치가 있어도 개별 효과라고 단정하지 않으며 같이 표시한다. 비교 불가능한 상품/팀/정의는 변화값을 숨기고 원래 제공 건수와 사유만 보여준다.

### 2.3 C — 상담사 업무량·SLA·규칙 추천

**최소 기능 1:** 단일 snapshot 기준으로 상담사별 현재 처리 가능한 활성 티켓 수와 유형, 기한 초과/임박 수, 열린 후속 수, 미배정·배정 무효 건수를 보여준다. **최소 기능 2:** 같은 사실을 사용해 미배정 HUMAN 업무에 후보 순서와 이유를 제안한다. A는 배정하지 않는다.

티켓 업무량은 `agent_assignment_exists`와 동일한 유효성(현재 cycle, ended_at 없음, team/category/scope/활성 역할, 처리 stage)을 통과한 **distinct(ticket_id, cycle_no)** 수다. assignment 행 수나 message/job 수를 세지 않는다. WAITING_CUSTOMER는 현재 구현상 배정 유효 상태에 포함되므로 업무량에 포함하고 별도 유형으로 분리한다. 실제 active handle time으로 부르지 않는다. 기존 helper의 시각은 utcnow이므로 새 snapshot 조회에서 동일한 `as_of`를 주입할 수 있게 하는 호환 확장을 추후 제안한다. 기본 동작은 유지한다.

후속은 OPEN/IN_PROGRESS를 세되 담당 유효성을 재검사하고 미인수·무효 담당은 팀 대기로 따로 센다. 티켓 수와 후속 수를 단순 합해 ‘문의 수’로 제시하지 않는다. 첫 추천은 티켓 업무량만 사용하고 후속은 참고 신호로 표시한다. 가중 업무량은 합의된 가중치/규칙 버전이 생기기 전까지 추가하지 않는다.

미배정은 ‘활성 티켓인데 유효한 현재 배정 없음’으로 정의하며 물리 assignment가 있어도 무효면 포함한다. 예외 큐의 FAILED 전체를 미배정으로 그대로 합산하지 않는다. route 있는 건은 해당 팀 scope에서만, route 미정은 기존 `UNROUTED_QUEUE_READ`를 가진 ADMIN에게 제한한다. 큐 capability는 원문/상세 권한을 주지 않는다. AGENT는 자기 업무량만, 팀 전체 상담사별 비교·추천은 `WORKLOAD_READ`/`ASSIGNMENT_RECOMMEND`를 가진 ADMIN의 현재 팀 scope로 제한하는 것이 최소 정책이다.

현재 표시 기준은 `LEGACY_24H_CONTINUOUS`: 열린 티켓에서 `as_of > sla_due_at`이면 초과, `0 <= sla_due_at-as_of <= 2시간`이면 임박, 그 외 정상. 기한과 정확히 같으면 임박이며 아직 초과가 아니다. 이 2시간은 제안 기본값이다. 기존에 저장된 기한을 사용하며 과거 값을 다시 계산해 덮어쓰지 않는다. 후속 due_at은 별도 업무 기한이고 null이면 `NO_DUE_DATE`다. 종료 티켓의 snapshot으로 과거 SLA 준수율을 새로 복원하지 않는다.

추천 규칙 v1은 다음 순서의 설명 가능한 정렬이다.

1. 업무: HUMAN 경로·현재 cycle·미배정·허용 상태를 우선 확인. 초과 → 임박 → 나머지, 이후 due_at → 대기 시작시각(근거가 있는 값) → ticket_id 순. priority 필드는 현재 기본 NORMAL이고 갱신 계약이 없으므로 임의의 중요도 점수로 사용하지 않는다.
2. 후보: 활성 AGENT, 소속 팀 일치, 활성 팀, 현재 user_team_scopes, team_categories가 요청 업무 category를 지원해야 함. **배정 전 후보는 현재 ticket_scope를 가질 수 없으므로 후보 적합성 검사는 별도 술어**로 만들고, 기존 유효 배정 술어와 공통 조건을 재사용한다. 추천 자체는 접근 권한을 주지 않는다.
3. 후보 정렬: 현재 처리 가능한 활성 티켓 수 오름차순 → 그중 초과 수 오름차순 → user_id 순. 이유 코드 예: `CATEGORY_SUPPORTED`, `LOWER_ACTIVE_LOAD`, `FEWER_OVERDUE`, `STABLE_TIEBREAK`. 고정 tie-break는 편향 가능성을 표시하며 최근 배정시간 기반 순환은 검증된 이력이 확보된 뒤 선택한다. 출근·휴가·숙련도·개인별 용량은 데이터가 없어 고려하지 못함을 표시한다.

추천 응답은 `as_of`, rule_version, expires_at(제안 30초), ticket revision/cycle, route revision, 후보별 근거 수치, 사용 팀 집합 fingerprint를 포함한다. 온라인 상태/처리 보장을 추정하지 않는다. 후보 없음은 빈 목록과 정형 사유다.

**B 사용 방식:** 우선 A의 같은 Python 추천 서비스 함수를 인증된 공통 DB transaction 경계에 연결한다. Frontend는 제안 HTTP 조회를 사용한다. B를 위한 별도 서비스 HTTP는 최초 범위에 추가하지 않으며 필요하면 서비스 인증부터 별도 계약한다. B는 추천을 힌트로 받아 실행 직전 재조회·재추천하고 실제 assignment/ticket/job/route/audit를 원자 저장한다. 외부 AI/네트워크는 잠금 transaction 밖에서 처리한다.

같은 티켓의 중복 배정은 기존 ticket mutex·revision/cycle/lease와 활성 assignment partial UNIQUE로 막는다. 다른 티켓들이 동시에 같은 상담사를 택하는 편중은 UNIQUE만으로 막을 수 없다. B의 배정 writer들이 같은 팀 단위 transaction advisory lock을 ticket→job 뒤, assignment 변경 전에 공통으로 얻고 최신 부하를 다시 계산하도록 제안한다. 두 팀 이동 시 guard는 팀 UUID 정렬 순서로 취득한다. 이 guard는 새 추천 시스템의 실행 계약이며 아직 구현돼 있지 않다. 모든 B 배정 writer가 따르기 전에는 부하 균형 보장을 하지 않는다. 하드 용량 제한은 최소 범위에 없다.

팀/직원 scope 변경과 엄밀히 직렬화하려면 scope/category writer도 동일 guard를 사용하고, user→guard만 취한 뒤 ticket으로 역행하지 않는 계약이 필요하다. 현재 B/권한 관리 writer 전체를 못 봤으므로 이 부분은 공동 검토 P0이다. B는 ticket/job 뒤 user를 새로 잠그지 않는다. 큐 route CAS, job expected_ticket_version, 새 ticket.version의 원자 갱신 관계를 기존 B 계약과 맞춰야 하며 단순 추천 ID만으로 배정을 승인하지 않는다.

### 2.4 담당 구분과 호환성

| 기능 | A | B | AI/RAG | Fabric | Frontend |
|---|---|---|---|---|---|
| 품질 | 응답 provenance·평가/이력·권한·운영 집계 | 실제 사용 suggestion/context를 확정 경계에 전달, 이관 이유 기록 | 정책/문서·검색 index/chunk·prompt/model 버전 제공 | 합의 후 장기 집계, 품질을 스스로 정답 판정하지 않음 | 제한된 표본 검토·coverage/unknown 표시 |
| VOC 개선 | 기존 product followup + profile·기간·참조·수신/조회 | 티켓 업무 기록/배정 계약 유지 | 문제 분류 근거 제공 시 버전 표시 | episode/주문 중복 제거, 전후 계산·완전성·중첩 경고 | 등록/시행일/기간 선택, 관측 변화와 한계 표시 |
| 업무량/SLA | scope 안의 사실 조회·규칙 추천·기한 저장 | claim/이관/실제 배정 및 충돌 재검증·writer 연동 | 최초 최소 구현에 ML 없음 | 합의 후 역사적 SLA/성과 집계 | 자기/팀 보기 분리, as_of/이유/충돌 새로고침 |

기존 고객 DTO·고객 소유권·일반 직원 상세 권한은 유지한다. 기존 KPI의 ticket 생성 cohort와 새 회차별 진단 비율을 같은 이름으로 바꾸지 않는다. 새 capability는 자동으로 모든 직원/관리자에게 부여하지 않는다. PAUSED/generation·필수 후속·고객 재문의·최종 응답 UNIQUE gate를 우회하지 않는다. 상품 개선 완료가 고객 티켓 해결을 자동 실행하지도 않는다.

## 3. DB·API 변경 제안

이 절은 대부분 **향후 구현 제안**이다. 예외로 workload 조회·WORKLOAD_READ는 후속 요청에서0.7.0/0007에 구현했다. 나머지 테이블·API는 존재하지 않으며 migration 번호를 선점하지 않는다. 기존0001–0006은 수정하지 않았다. 아래의 NN은 NOT NULL, 모든 시각은 aware UTC/timestamptz, version/revision은 양의 bigint다. 문자열 상태는 기존 프로젝트처럼 CHECK를 기본으로 하며 native ENUM 도입은 필수가 아니다.

### 3.1 A 기록과 공통 회차 기록

| 제안 테이블 | 주요 컬럼·제약 | 인덱스·쓰기 규칙 |
|---|---|---|
| `ticket_cycles` | PK(ticket_id FK, cycle_no), started_at NN, start_reason NN(CREATED/REOPEN/REQUEST_AGENT), initial_ticket_revision NN, initial_mode NN, source_message_id FK nullable(legacy 포함), category_at_start NN, attribution_team_id FK nullable, attribution_state NN(KNOWN/UNATTRIBUTED/UNKNOWN), first_replied_at/resolved_at/superseded_at nullable, resolution_mode nullable, handoff_at/reason_code/trigger nullable, origin_auto_cycle_no nullable, recording_state NN(COMPLETE/PARTIAL_LEGACY). origin_auto_cycle_no는 같은 ticket의 cycle을 참조. cycle/revision>=1, 종결/후속 시각>=started_at, handoff 시각/사유/trigger는 함께 지정 | (started_at,ticket_id,cycle_no), (attribution_team_id,started_at), (handoff_at). 접수/회차 변경/최종 확정/사람 writer가 기존 ticket mutex 안에서 원자 기록. 재시도는 새 행을 만들지 않음 |
| `automatic_reply_records` | PK 및 FK message_id, ticket_id/cycle_no 복합 FK, job_id FK NN, suggestion_id/approval_id FK nullable, input_ticket_revision/result_ticket_revision NN, suggestion_revision nullable, reply_sha256 NN, committed_at NN, provenance_state NN(COMPLETE/MISSING/PARTIAL/LEGACY_UNVERIFIED), origin NN(APPLICATION/SYNTHETIC/UNKNOWN), model_version/prompt_version/rule_id FK/rule_version/retrieval_index_version/context_ref nullable, evidence_manifest JSONB allowlist nullable. UNIQUE(ticket_id,cycle_no), UNIQUE(job_id); result_revision=input_revision+1 | (committed_at,message_id). 같은 transaction에서 message/job/cycle 일치, suggestion revision/hash, approval content link 검사. 정책별 document_id/version/content_hash/chunk_id/effective 범위와 사용시각만 기록; 본문·raw prompt·snapshot 전체 복사 금지. insert-only |
| `quality_samples` | sample_id UUID PK, message_id FK NN, rubric_version NN, review_team_id FK NN, assigned_reviewer_id FK nullable, sample_method NN(MANUAL/DETERMINISTIC_SAMPLE), selected_at NN, current_revision NN, status NN(PENDING/REVIEWED/VOID), scope_revision NN. UNIQUE(message_id,rubric_version) | (review_team_id,status,selected_at,sample_id), (assigned_reviewer_id,status). message/rubric/책임 팀을 임의 overwrite 금지, 담당/범위 변경은 version 및 이력 동반 |
| `quality_review_revisions` | PK(sample_id FK,revision), reviewer_id FK nullable(미평가 관리 이벤트), event_kind NN(REVIEW/REASSIGN/VOID), accuracy nullable(CORRECT/INCORRECT/UNDETERMINABLE), policy_alignment nullable(MATCH/MISMATCH/UNDETERMINABLE/NOT_APPLICABLE), reason_codes 제한 배열, independent_review nullable, reviewed_at NN, changed_reason NN, assigned_reviewer_id FK nullable, review_team_id FK NN. REVIEW는 두 판정과 실제 평가자 필수, 나머지는 관리 이벤트 스키마로 분리 검증 | (reviewed_at,sample_id), (reviewer_id,reviewed_at). append-only; sample row lock + expected_revision CAS + 이력/감사 원자 저장. DB FK/UNIQUE와 앱 검사 병행 |

정형 기록의 불변 연결을 위해 message의 ticket/cycle과 reply_record를 묶는 UNIQUE 및 복합 FK를 추가하는 방안을 구현 시 검증한다. cross-table 동일성은 단순 CHECK로 보장할 수 없으므로 공통 writer 검증과 제한 DB 권한을 함께 적용한다. context_ref는 제한된 내부 식별자이며 임의 URL/파일 경로를 서버가 읽게 하지 않는다. COMPLETE를 쓰려면 필수 provenance 존재·문서 hash/version 일치·보존된 원본 접근성을 확인해야 한다. model/prompt 버전만으로 생성 결과의 비트 단위 재현을 보장하지 않는다. generation 파라미터/모델 배포 버전·검색 snapshot의 보존 정책은 AI/RAG와 합의한다.

기존 데이터는 일괄 COMPLETE로 backfill하지 않는다. 확실한 message/job/cycle 연결조차 없으면 reply_record를 임의 생성하지 않고 legacy 후보로 조회한다. 직접적인 원래 메시지·정형 기록으로 입증 가능한 값만 provenance/source와 함께 제한적으로 이관한다. 현재 티켓값에서 과거 team/category/기한을 복사하거나 audit payload에 없는 revision을 추정하지 않는다. `ticket_cycles` 과거 미기록 회차는 행 부재 또는 PARTIAL_LEGACY이고 지표의 unknown/excluded로 표시한다. 새 전향적 recording 시작시각을 API meta에 노출한다.

`quality_samples`에는 raw 응답·고객 ID를 복제하지 않는다. 읽을 때 원본 message와 허용된 질문/문서 자료를 참조한다. 원문 수정/삭제 또는 hash 불일치는 `MATERIAL_CHANGED`/`MATERIAL_UNAVAILABLE`이며 과거 판정을 현재 원문으로 재해석하지 않는다. 질문 전체 히스토리·프로필·주문번호·연락처를 표본 응답에 포함하지 않는다. 검토에 주문 사실이 꼭 필요할 경우 기존 마스킹 allowlist의 최소 사실과 당시 버전 참조를 사용한다.

### 3.2 B 개선 profile·참조·Fabric 비교 mart

| 제안 테이블 | 주요 컬럼·제약 | 인덱스·원자성 |
|---|---|---|
| `voc_improvement_profiles` | action_id PK/FK followup_actions, product_id FK NN, current_plan_revision NN, created_by FK NN, created_at NN. product 대상 followup이고 같은 product이며 blocks_resolution=false여야 함 | (product_id,action_id). product 대상 일치 검사는 공통 writer/필요 시 DB trigger, 기존 target 변경 불가 정책 유지 |
| `voc_improvement_plan_revisions` | PK(action_id FK,revision), issue_code NN(기존 primary_issue allowlist와 합의한 taxonomy), improvement_text NN(예: 최대 4,000자), implemented_at nullable, before_start/end/after_start/end nullable, owner_team_id_snapshot FK NN, comparison_team_ids 정렬 UUID 집합 NN, scope_definition_version NN, metric_definition_version NN, source_batch_id FK nullable, source_scope_key nullable, created_by FK NN, created_at NN, change_reason NN. 비교창은 모두 null 또는 전부 값; start<end, 두 길이 동일, before_end<=after_start. 시행일 모르면 결과 평가 불가. source batch/scope는 함께 지정 | immutable 계획 revision; profile CAS. issue/product/기간/scope 수정 시 새 revision, 기존 Fabric 결과는 원래 revision에 고정 |
| `voc_improvement_ticket_links` | PK(action_id FK,ticket_id FK), linked_by FK NN, linked_at NN. 연결 시 양쪽 scope·product_id 일치 검사(상품 불명/다름은 거부) | (ticket_id,action_id). 원문·customer_id 없음. 링크 조회 시 현재 양쪽 권한 재검사, 권한 없는 티켓의 ID/개수도 노출 금지 |
| `analytics_voc_improvement_effects` | PK(batch_id FK,action_id,plan_revision,scope_key), (action_id,plan_revision) 복합 FK, product_id FK NN, definition_version NN, before/after 기간 NN, before/after inquiry_count·inquiry_order_count·paid_order_count nullable bigint, basis NN(ORDER_INQUIRY_RATE/INQUIRY_COUNT), before_value/after_value/absolute_change/relative_change nullable numeric, comparison_status NN(COMPARABLE/NOT_COMPARABLE/IMMATURE), warning_codes 제한 배열, completeness/overlapping_action_refs allowlist, source_as_of NN | (action_id,plan_revision,batch_id). 값은 0이상 count, NaN/Infinity 거부. 미평가/누락은 null. raw ticket/customer/order/문장 필드 없음. 게시 후 불변, 행 hash/수량 검증 대상 |

이력에는 개인정보를 적지 않도록 UI 안내와 입력 제한을 두고 원문을 감사/로그로 반사하지 않는다. 단순 길이 제한을 개인정보 탐지 성공으로 표현하지 않는다. 시행 전 계획 중에는 implemented_at과 창이 null이어도 등록 가능하다. 이후 실제 시행 확인 시 고정 비교창을 기록한다. 비교창이 있으면 implemented_at은 필수이고 `before_end <= implemented_at <= after_start`를 검증한다. 기본은 양쪽 경계가 시행일과 같고 제외/지연 간격을 두는 경우 명시한 규칙을 고정한다. 미래 시각은 실제 시행일로 허용하지 않고 예정은 별도 due_at으로 관리한다. source_batch/scope 연결은 실제 게시 성공 batch와 정확한 팀 집합을 기존 snapshot resolver로 검증한다. DONE 이후 일반 followup 수정은 기존처럼 거부한다. 계획 사실 정정은 별도 ADMIN correction 경계로 새 plan revision을 만들고 사유·영향받는 결과를 표시하며 업무를 재개하지 않는다. 기존 `owner_team_id`가 계획 scope와 달라지면 이전 결과는 보존하고 `SCOPE_CHANGED/PLAN_REFRESH_REQUIRED`를 표시한다. 현재 담당 팀이 과거 비교 팀 전체 권한을 자동 획득하지 않는다.

**Fabric 계약 확장 결정:** 기존 `/analytics/batches` 프로토콜을 재사용하는 `analytics-v2` 명시 버전을 제안한다. 별도 조치별 임의 JSON 수신 API를 만들지 않는다. v2는 기존 4개 mart + `analytics_voc_improvement_effects`를 한 완성 snapshot으로 수신한다. v1은 계속 4개만 받고 현재 wire/해시를 유지한다. v2의 row_counts/checksums/KEYS/canonical/저장·재검증/불변 trigger는 5개 전체를 포함해야 한다. 현재 validator의 `schema_version == analytics-v1`, TABLES 상수, 고정 rule/windows가 이를 지원한다고 가정하지 않는다.

처음에는 같은 singleton publication pointer를 유지한다. v2의 어느 테이블이든 실패하면 기존 current를 그대로 두고 부분 게시하지 않는다. 기존 4개 데이터도 포함하므로 v2는 기존 TOP10/KPI를 조용히 비울 수 없다. v2 전환 후 v1로 current를 전환하면 effect mart가 사라질 수 있으므로 wire 수신 호환과 별도로 **v2 이후 current의 v1 downgrade 게시 차단**을 제안한다. 운영 전 Fabric 배포 순서 합의가 필요하다. 독립 주기의 결과가 꼭 필요해지면 그때 dataset별 pointer를 별도 설계한다.

기존 전역 watermark 규칙(윈도 끝·source_as_of 비감소, 하나 증가)을 유지한다. 효과 정정만으로 같은 watermark를 재게시하지 않는다. 실제 새 source_as_of/후속 완성 snapshot을 제공하고 batch_id를 새로 만든다. 과거 published batch는 pin 조회하되 현재 권한을 적용한다. 새 current에 없는 조치 결과는 `RESULT_NOT_IN_SELECTED_BATCH`; 조용히 과거 배치 결과를 섞지 않는다. 사용자가 과거 성공 batch를 명시했을 때만 그 결과를 보여준다.

v2 manifest에 별도 `effect_definition_version`, 효과 행 coverage 목록(action/plan/scope), 제품 식별 매핑 버전, 원천별 완전성/lineage 해시를 allowlist로 추가한다. window는 행의 고정 plan과 정확히 일치해야 하며 기존 최근7일/VOC 판매28일과 분리한다. `scope_key`는 서버가 선택한 **정확한 팀 집합**과 맞아야 한다. 기존 product_daily의 전사 판매 수치를 부분 팀 효과의 분모로 가져오지 않는다. 전체 상품 판매를 사용할 때도 별도 명시된 GLOBAL 분모 정의와 문의 분자의 관계를 합의한다.

검증은 존재하는 제품·action·plan, immutable 기간·scope 일치, FK/중복/카운터/row/hash, source watermark/coverage, basis별 null/0 분모 규칙, 제공된 비율·변화값의 산술 일치를 검사한다. A는 원장 episode 구성·표본 제거·매출/문의 cohort를 재계산하지 않는다. 실제 원천/완전성 진위는 Fabric의 선언이며 검사 통과가 독립 검증은 아니다. 상품 불일치는 batch 검증 실패 또는 별도의 정형 미대상 결과로 격리하고 다른 상품에 합치지 않는다.

### 3.3 C SLA 기록과 공통 권한/멱등

**첫 단계는 DB 신규 없이 가능한 읽기 확장:** 현재 ticket.sla_due_at + 유효 배정 + route + followup.due_at을 조회한다. (새 capability를 실제 부여하려면 staff_permissions CHECK 확장은 필요하다.) 추천 저장 테이블·ML·별도 scheduler는 추가하지 않는다.

정식 SLA 정책 합의 후에만 `sla_policy_versions`와 `ticket_cycle_sla`를 추가한다. 전자는 PK(policy_key,version), category/적용팀, first_response_seconds, resolution_seconds, calendar_mode(CONTINUOUS/BUSINESS), calendar_version nullable, pause_policy_version, reopen_policy, effective_from/to를 저장하고 불변으로 한다. 기간/효력 겹침과 정책 선택 우선순위를 검증한다. 후자는 PK(ticket_id,cycle_no,kind), kind(FIRST_RESPONSE/RESOLUTION), policy_key/version 복합 FK, started_at NN, due_at/fulfilled_at nullable, status(ACTIVE/PAUSED/FULFILLED/SUPERSEDED/UNKNOWN), accumulated_pause_seconds>=0, revision>=1, recording_state를 둔다. (status,due_at,ticket_id) 인덱스를 제안한다. pause가 실제 요구되면 append-only pause/resume 사건 테이블을 추가하고 겹침·중복 pause·역순 시각을 막는다. 이 이벤트가 없는데 누적 일시 정지를 역산하지 않는다.

`ticket_cycles`는 시작·응답·종결의 사실, `ticket_cycle_sla`는 정책 적용 clock을 소유한다. first_replied_at은 어떤 PUBLIC OUT을 첫 응답으로 볼지 확정 전까지 기존 저장 사실로만 표시한다. 자동 최종 확정이 first_replied_at을 채우지만 ACK/안내·사람 최초 응답의 SLA 충족 여부는 아직 합의되지 않았다. legacy 기한은 정책 버전 미상으로 보존하며 `LEGACY_24H_CONTINUOUS`는 저장 동작의 설명 라벨이지 과거에 존재한 정책 행을 뜻하지 않는다.

필요 시 조회 계획을 확인한 뒤 부분 인덱스 `(agent_id,ticket_id,cycle_no) WHERE ended_at IS NULL`, `(sla_due_at,ticket_id) WHERE status NOT IN ('RESOLVED','CANCELLED')`, 후속 `(owner_user_id,due_at) WHERE status IN ('OPEN','IN_PROGRESS')`를 제안한다. 기존 인덱스를 먼저 대조하고 중복 생성하지 않는다. 부하 수치 물질화/캐시로 권한 정합성을 약화하지 않는다.

새 permission 후보는 `QUALITY_SAMPLE_MANAGE`, `QUALITY_UNATTRIBUTED_MANAGE`, `QUALITY_REVIEW`, `QUALITY_METRICS_READ`, `VOC_IMPROVEMENT_MANAGE`, `WORKLOAD_READ`, `ASSIGNMENT_RECOMMEND`다. role 검사와 현재 normalized scope를 함께 요구하며 role 문자열만으로 허용하지 않는다. 기존 permission CHECK와 capability allowlist를 함께 확장하고 기본 grant는 0개로 시작한다. 검토 표본 담당이거나 제품 owner라는 사실만으로 다른 팀 원문을 열 수 없다. 미귀속 응답의 평가 후보·별도 미귀속 지표는 QUALITY_UNATTRIBUTED_MANAGE도 요구하며 팀별 결과에 몰래 섞지 않는다.

새 생성/수정 명령의 안전한 재시도에는 `extension_command_receipts`를 제안한다: PK(actor_user_id FK,key), operation NN, request_hash NN, resource_kind/UUID, response_snapshot allowlist, created_at NN. **신규 확장 API들끼리만 공유하는 명시적 namespace**다. 기존 `idempotency_keys`는 operation/target CHECK가 고정돼 있어 새 ID를 억지로 ticket_id/followup_id에 넣지 않는다. 기존 API namespace는 그대로다. 전역 통합 namespace가 필요하면 별도 호환 migration과 기존 writer 변경이 필요하다.

생성 및 이력 추가 명령은 Idempotency-Key와 정규화 operation/target/body hash를 사용한다. 첫 성공 201(생성)/200(수정), 같은 key·같은 내용은 원래 receipt, 다른 내용/operation은 409. 재시도도 현재 접근 권한을 먼저 검사하고 반환한다. append 명령이 실제로 성공했는지 불확실할 때 새 key로 무작정 재전송하지 않는다. 업무 row lock + expected_revision으로 경쟁 수정은 409이며 retry key 확인은 revision 검사보다 먼저 한다. 기존 followup PATCH/status의 동작·멱등 namespace는 변경하지 않는다.

평가 원문 hash와 보관 문서 version, profile/plan/Fabric 참조가 새 보호 대상이다. 향후 구현 시 retention dry-run에 해당 참조/보존·hold 상태를 추가해야 한다. 새 테이블을 만들고 기존 보관 preview가 이 참조도 보호한다고 주장하지 않는다. 실삭제/Export/Blob 업로드는 여전히 별도 범위다.

### 3.4 이미 존재하는 API

모든 경로의 공통 prefix는 `/api/v1`이다. 아래는 **현재 구현됨**이다.

| 메서드·경로 | 현재 용도·권한 |
|---|---|
| POST `/tickets`, POST `/tickets/{ticket_id}/reopen`, POST `/tickets/{ticket_id}/request-agent` | 고객 소유권·멱등·revision/회차 명령 |
| GET/POST `/staff/followups`, GET/PATCH/DELETE `/staff/followups/{action_id}`, POST `/{action_id}/status` | 직원 후속 CRUD. DELETE는 취소. product는 ADMIN 경계 |
| GET `/staff/exception-queue`, GET `/staff/exception-queue/counts` | capability+route/scope 기반 큐, 전체 업무량이나 자동 배정 아님 |
| POST `/staff/tickets/{ticket_id}/internal` | 목적별 allowlist 조회. QUALITY_REVIEW는 ADMIN, 원문/draft 없음 |
| POST `/analytics/batches`, GET `/analytics/batches/{batch_id}`, POST `/{batch_id}/validate`, POST `/{batch_id}/publish` | 별도 서비스 JWT의 receive/publish permission. 일반 사용자/ADMIN JWT로 대체 불가 |
| GET `/admin/analytics/voc/top`, `/admin/analytics/voc/unavailable`, `/admin/analytics/products/{product_id}`, `/admin/analytics/kpi` | ADMIN + 활성 팀 scope exact-set + 게시된 batch snapshot |

### 3.5 API 진행 상태 — workload만 구현, 나머지는 제안

| 메서드·경로 | 입력·권한·응답 핵심 |
|---|---|
| GET `/staff/quality/candidates` | ADMIN+QUALITY_SAMPLE_MANAGE, 허용 팀/기간. 응답 후보 ID·기록완전성만, 원문 없음. 미귀속은 QUALITY_UNATTRIBUTED_MANAGE도 필요 |
| POST `/staff/quality/samples` | message_id, rubric_version, review_team_id, assigned_reviewer_id, sample_method, Idempotency-Key. ADMIN+SAMPLE_MANAGE 및 현재 팀 scope |
| GET `/staff/quality/samples` | REVIEW 담당자는 자기 표본만, 관리자는 허용 팀 표본. status/기간, keyset pagination |
| POST `/staff/quality/samples/{sample_id}/material` | purpose_code=QUALITY_REVIEW; REVIEW+현재 표본 배정+team scope, 성공/거부 감사. 대상 응답·최소 질문·검증된 버전 근거만. material hash와 unknown 상태 |
| POST `/staff/quality/samples/{sample_id}/reviews` | Idempotency-Key, expected_revision, accuracy, policy_alignment, reason_codes, changed_reason. REVIEW 담당자만. sample revision+이력 receipt |
| PATCH `/staff/quality/samples/{sample_id}/assignment` | ADMIN+SAMPLE_MANAGE, expected_revision, 명시 새 담당/팀·사유. 양 팀 scope 필요; 이력 증가 |
| POST `/staff/quality/samples/{sample_id}/void` | ADMIN+SAMPLE_MANAGE, expected_revision/사유. 이력 보존, 집계에서 VOID 제외·제외수 표시 |
| GET `/staff/quality/metrics` | ADMIN+QUALITY_METRICS_READ, 현재 scope·응답 확정 기간·rubric·as_of. 각 분자/분모·미평가·불명·sampling 방법/coverage |
| POST `/staff/voc-improvements` | ADMIN+VOC_IMPROVEMENT_MANAGE, 신규 product followup+plan 동시 생성 또는 existing_action_id 등록, Idempotency-Key |
| GET `/staff/voc-improvements`, GET `/{action_id}` | ADMIN+MANAGE 및 담당 팀 scope. 기본/상태는 기존 followup 참조, plan_revision·결과 availability |
| POST `/staff/voc-improvements/{action_id}/plans` | ADMIN+MANAGE, Idempotency-Key, expected_plan_revision 및 expected_action_revision, 계획/실제 시행 사실·사유. append-only. 종료 후 정정 여부를 명시 |
| POST `/staff/voc-improvements/{action_id}/tickets` | ticket_id, Idempotency-Key, action revision. 조치와 ticket의 현재 권한/product 일치 필요 |
| GET `/admin/analytics/voc-improvements/{action_id}/effects` | ADMIN + 현재 조치 권한 + 비교 전체 team scope. plan_revision/team_ids/batch_id 선택. 게시된 v2 snapshot만, 미지원 scope는 unavailable |
| GET `/staff/workload` | **0.7.0/0007 구현**. AGENT 본인(role, grant 불필요), ADMIN WORKLOAD_READ+팀 scope. 실제 DTO는 [workload.md](workload.md); scope/page 합계·팀 대기·미라우팅 별도 |
| GET `/staff/assignment-recommendations` | ADMIN+ASSIGNMENT_RECOMMEND+업무 route scope. ticket_id(선택) 또는 팀 미배정 업무 페이지. 원문 없이 ticket/cycle/revision/route revision·후보·이유·as_of/expires_at. 배정 실행 없음 |
| POST `/analytics/batches` 계열의 v2 수신·검증·게시 | 경로는 기존 그대로, body의 명시 버전에 따라 새 allowlist 적용. 해당 effect 읽기는 새 제안 API. 현재 코드는 v2를 수락하지 않음 |

후속의 owner/status/due 변경은 기존 API를 계속 사용한다. 개선 wrapper가 동일 followup을 복제하지 않는다. 계획과 action revision은 별개이며 함께 필요한 명령만 둘 다 검증한다. 제품 개선 담당·팀이 변경되면 새 계획 범위 확인과 현재 권한 검사 없이 과거 결과를 새 담당에게 노출하지 않는다.

예시 1 — 표본 등록과 평가 요청(제안, 모든 UUID는 가상 값):

```json
{
  "message_id": "11111111-1111-4111-8111-111111111111",
  "rubric_version": "quality-rubric-v1",
  "review_team_id": "22222222-2222-4222-8222-222222222222",
  "assigned_reviewer_id": "33333333-3333-4333-8333-333333333333",
  "sample_method": "MANUAL"
}
```

```json
{
  "expected_revision": 1,
  "accuracy": "CORRECT",
  "policy_alignment": "UNDETERMINABLE",
  "reason_codes": ["POLICY_VERSION_MISSING"],
  "changed_reason": "INITIAL_REVIEW"
}
```

```json
{
  "sample_id": "44444444-4444-4444-8444-444444444444",
  "revision": 2,
  "review_state": "REVIEWED",
  "accuracy": "CORRECT",
  "policy_alignment": "UNDETERMINABLE",
  "evaluated_at": "2026-11-04T03:00:00Z"
}
```

각 변경 요청에는 Idempotency-Key 헤더를 붙인다. 다음 집계 예시는 별도의 합성 집합이며 위 평가 1건만으로 계산한 결과가 아니다.

```json
{
  "definition_version": "response-human-review-v1",
  "confirmed_response_count": 100,
  "official_review_count": 20,
  "unreviewed_count": 80,
  "accuracy": {"correct": 15, "incorrect": 3, "undeterminable": 2, "denominator": 18, "rate": 0.833333},
  "policy_alignment": {"match": 12, "mismatch": 3, "undeterminable": 3, "not_applicable": 2, "denominator": 15, "rate": 0.8},
  "sample_method": "MANUAL",
  "population_accuracy": null,
  "as_of": "2026-11-04T03:00:00Z"
}
```

예시의 confirmed_response_count는 같은 rubric/기간/scope의 평가 후보 전체이며 unreviewed_count는 표본으로 추출하지 않은 80건도 포함한다. 실제 응답에는 selected_count/pending_sample_count/void_count/excluded_count/unknown_provenance_count와 기간·scope metadata를 추가한다.

예시 2 — POST `/staff/voc-improvements`로 기존 상품 후속에 첫 개선 계획 등록(제안, 기존 계획이 없으므로 expected_plan_revision=0):

```json
{
  "existing_action_id": "77777777-7777-4777-8777-777777777777",
  "expected_action_revision": 3,
  "expected_plan_revision": 0,
  "issue_code": "DAMAGED",
  "improvement_text": "포장 완충재 규격 변경",
  "implemented_at": "2026-11-04T00:00:00Z",
  "before_start": "2026-10-21T00:00:00Z",
  "before_end": "2026-11-04T00:00:00Z",
  "after_start": "2026-11-04T00:00:00Z",
  "after_end": "2026-11-18T00:00:00Z",
  "comparison_team_ids": ["22222222-2222-4222-8222-222222222222"],
  "scope_definition_version": "fixed-team-set-v1",
  "metric_definition_version": "voc-effect-v1",
  "change_reason": "IMPLEMENTATION_CONFIRMED"
}
```

```json
{
  "availability": "UNAVAILABLE",
  "reason": "OBSERVATION_IMMATURE",
  "action_revision": 3,
  "plan_revision": 1,
  "basis": "INQUIRY_COUNT",
  "before": {"inquiry_count": null, "paid_order_count": null, "inquiry_rate": null},
  "after": {"inquiry_count": null, "paid_order_count": null, "inquiry_rate": null},
  "relative_change": null,
  "causal_effect": "NOT_ESTABLISHED"
}
```

이는 11/4 시점에 11/18까지 관측할 수 없다는 예다. 아직 Fabric 결과가 없다면 실제 사유는 `NO_PUBLISHED_EFFECT_BATCH`이고, 후속 기간이 성숙해도 데이터가 없으면 0으로 바꾸지 않는다. availability와 비교 사유는 서버가 검증한 실제 상태를 따른다.

예시 3 — 업무량·추천 응답(제안):

```json
{
  "as_of": "2026-11-04T03:00:00Z",
  "expires_at": "2026-11-04T03:00:30Z",
  "rule_version": "assignment-rules-v1",
  "ticket_id": "55555555-5555-4555-8555-555555555555",
  "cycle_no": 2,
  "ticket_revision": 5,
  "route_revision": 1,
  "sla": {"basis": "LEGACY_24H_CONTINUOUS", "due_at": "2026-11-04T04:00:00Z", "state": "DUE_SOON"},
  "candidates": [{"agent_id": "33333333-3333-4333-8333-333333333333", "active_tickets": 3, "overdue_tickets": 0, "open_followups": 1, "reason_codes": ["CATEGORY_SUPPORTED", "LOWER_ACTIVE_LOAD"]}],
  "execution": "BACKEND_B_REVALIDATION_REQUIRED"
}
```

공통 오류 응답은 기존 ErrorEnvelope 형식을 재사용한다.

```json
{"error":{"code":"QUALITY_REVISION_CONFLICT","request_id":"66666666-6666-4666-8666-666666666666"}}
```

권한 없음은 role/capability 기준 403, 존재 여부를 숨길 객체 범위 밖은 기존처럼 404, revision/중복 표본/멱등 충돌/이미 종료 등은 409, 잘못된 enum·시각·기간·금지 필드는 422, body/row 상한은 413, 현재 production 공통 ingress의 429도 유지한다. 집계자료 없음은 대체로 HTTP200+UNAVAILABLE+reason이며 실행 가능한 성공 판정과 혼동하지 않는다. 추천 만료·revision/route 충돌·후보 무효는 B의 409/WorkRejected 계열 계약에 매핑하고 자동 덮어쓰기하지 않는다. 실제 에러 코드는 구현 시 충돌 없이 확정한다.

## 4. 지표 정의표

### 4.1 공통 기간·집계 규칙

- 모든 기간은 `[start,end)`이고 as_of는 응답에 고정한다. KST 달력 구간은 서버가 UTC 경계로 변환하며 offset 없는 입력은 거부한다. 평가일 cohort와 응답 확정일 cohort를 섞지 않는다.
- 기존 관리자 KPI는 `ticket_creation_cohort/day/team/category`를 유지한다. 새 회차 진단은 `ticket_id+cycle_no`라고 표시하고 **상담 수라고 부르지 않으며 distinct ticket 수를 함께 표시**한다. 재시도 attempt/lease 재claim은 추가 회차/상담이 아니다. 재문의는 같은 ticket의 새 회차이며 별도 신규 상담으로 중복 합산하지 않는다.
- 역사적 scope는 기록된 귀속/명시 비교 팀을 사용한다. 현재 권한 검사는 별개로 매번 수행한다. 미귀속 AUTO를 임의 팀에 배분하지 않고 `UNATTRIBUTED`로 분리한다. 팀 한정 결과는 그 정확한 집합에 대해 제공된 기록만 사용한다.
- 기존 snapshot의 제한을 넘어 추정하지 않는다. 신규 전향 기록 시작 이전·합성·잘못된 연결·불완전 이벤트는 운영 통계에서 별도 제외/unknown 수와 이유를 표시한다. 분모 0이면 rate=null/NO_DENOMINATOR, 자료 미수신이면 UNAVAILABLE이고 0과 구별한다.

### 4.2 품질·자동 처리

| 지표 | 분자 | 분모 | 집계 단위·기간 | 데이터 출처·계산 담당 | 결측/제외 기준 |
|---|---|---|---|---|---|
| 자동 확정 응답 수 | 실제 AUTO 확정 PUBLIC OUT final의 distinct message 수 | 없음(건수) | 응답 committed_at∈기간, response/cycle 1건 | reply_record+messages+job, A 운영 집계 | A가 AUTO job과 응답 연결을 확정했다면 정책 근거 MISSING이어도 후보에 포함. AUTO 연결 자체 불명인 legacy는 unverified 별도. 이것만으로 정답/실제 전달 성공 아님 |
| 정확성(평가 표본 내) | 최신 공식 accuracy=CORRECT 수 | CORRECT+INCORRECT | message_id/rubric 1표, 응답 확정 기간 cohort, as_of 이전 최신 유효 REVIEW | quality revisions, A. 장기 집계는 같은 정의로 Fabric | 미평가·UNDETERMINABLE·VOID는 비율에서 제외하고 수 공개. 합성 별도 |
| 정책 근거 일치율(평가 표본 내) | MATCH 수 | MATCH+MISMATCH | 위와 같은 response/rubric cohort | 사람 판정+당시 evidence version/hash, A | UNDETERMINABLE/NOT_APPLICABLE/미평가 각각 표시. 시스템 gate/AI 점수는 분자 아님 |
| 평가 coverage | 공식 사람 REVIEW가 있는 응답 수(판단 불가 포함) | 확인 가능한 AUTO 확정 응답 전체 후보 수 | response/rubric, 같은 응답 cohort | A | 미추출·표본 PENDING 모두 미평가. VOID는 공식 평가 없음으로 보며 별도 void_count. 판정 가능 coverage도 별도 제공 |
| 미평가 수 | 분모 후보 중 공식 REVIEW 없는 응답 수 | 없음 | 위와 동일 | A | 후보 전체에서 산출. 표본 목록만 분모로 삼지 않음. UNKNOWN_PROVENANCE는 별도 coverage 밖 불명 수 표시 |
| AUTO 회차 자동 완료율(진단) | 해당 AUTO 시작 회차에서 유효 자동 final이 확정된 회차 수 | initial_mode=AUTO이며 started_at∈기간인 완전 기록 회차 수 | distinct(ticket,cycle), 관측 as_of까지. distinct ticket 수도 별도 | ticket_cycles+reply_record, A 운영 집계 / 이후 Fabric | 열린/재시도/실패 회차도 분모. 같은 job 재시도는 중복 안 됨. 불완전 legacy는 excluded. 이 값은 기존 ticket 자동완료율 대체 아님 |
| AUTO 회차 사람 이관율(진단) | 자동 시작 회차에서 처음 사람 경로로 이동한 원본 AUTO 회차 수 | 위 AUTO 시작 회차 분모 | 원본 ticket/cycle 1회, started_at cohort | B의 구조화 이관 기록+A 고객 명령의 origin 연결 | HUMAN 요청으로 생긴 새 cycle/이후 HUMAN_CONTINUATION은 다시 이관으로 세지 않음. 직접 HUMAN 시작은 별도 경로 수. 원본 연결 없으면 UNKNOWN |
| 이관 사유 구성비 | 해당 reason_code의 distinct 원본 AUTO 이관 회차 수 | 전체 AUTO 이관 회차 수(UNKNOWN 포함) | 위와 같은 cohort, 한 회차의 최초 전이 사유 | 고객 요청 사유와 B engine 이유를 trigger로 구분, A/Fabric | error_code나 큐 reason을 실질 이관 원인으로 추측하지 않음. UNKNOWN은 분모와 항목에 남김 |
| 안전한 자동 완료율 | **미확정**: 사람 평가 통과 및 W 내 재문의/사후 이관 없음, 완전 관찰 | **미확정**: W 성숙한 어떤 응답 집합을 사용할지 합의 필요 | response/cycle 후보, W 기산은 committed_at/실제 전달시각 중 합의 | 사람 검토+A/B 사건+관찰 coverage; 최종 장기 집계 Fabric | 현재 UNAVAILABLE. 미평가/관찰미성숙/다른 ticket 재문의 관측불가를 성공 처리하지 않음 |

AUTO 회차가 자동 응답 뒤 사람 이관될 수 있어 자동 완료·이관은 as_of 기준 서로 겹칠 수 있다. 두 비율 합을 100%로 만들지 않으며 `auto_completed_then_handoff_count`를 별도로 표시한다. ‘최종 경로 기준 상호배타 비율’이 필요하면 다른 definition으로 합의한다. 재문의가 AUTO로 새 시작되면 회차 진단에는 새 회차이되 고유 티켓/상담 수에는 추가하지 않는다.

숫자 검산 예: 후보 100, 검토20(정확15/오류3/판단불가2), 미평가80이면 정확성은 15/18이며 15/100이나 95/100이 아니다. 분모가 다른 정책 일치율과 같은 표본 수라고 단정하지 않는다. 수동 표본이면 population 추정치는 제공하지 않는다. rubric 버전이 다르면 나눠 보고 같은 응답의 두 rubric을 단순 합산하지 않는다.

### 4.3 VOC 개선·효과

| 지표 | 분자 | 분모 | 집계 단위·기간 | 데이터 출처·계산 담당 | 결측/제외 기준 |
|---|---|---|---|---|---|
| 시행 전/후 VOC 문의 건수 | 해당 product/issue/fixed scope의 중복 제거 문의 수 | 없음 | 최소 제안 distinct ticket 기준, 같은 ticket 재문의 중복 제외. before/after 동일 길이 | Fabric Silver/Gold→효과 mart, A 수신 | 기존 VOC complaint episode 지표와 다름. episode로 바꾸면 별도 definition. 문제 분류 변경/매핑 불일치/불완전 기간이면 NOT_COMPARABLE |
| 판매 대비 문의율(주문 건수 기준) | 해당 창의 distinct 문의 주문 수 | 같은 창/상품/정의의 유효 paid order 수 | action+plan+scope+window | orders/tickets의 합의 cohort, Fabric 계산 | 양 창 판매 완전성·중복 제거 필수. 분모0/누락은 null. 주문 연결 안 된 문의·outside cohort 건수는 제외수로 별도 표시 |
| 문의 건수 절대 변화 | after 문의 수 − before 문의 수 | 없음 | 같은 단위·정의·scope·길이 | Fabric 제공값, A 산술 검증 | 판매가 없어도 사용 가능. before/after 둘 중 누락이면 null. 0은 실제 관측0일 때만 |
| 문의 건수 상대 변화 | after 문의 수 − before 문의 수 | before 문의 수 | 위와 동일 | Fabric | before=0이면 null/BASELINE_ZERO. ‘개선 효과율’로 명명하지 않음 |
| 문의율 변화 | after_rate − before_rate | 없음(비율의 절대 차, %p 표시) | 동일 기간 길이·분모 정의 | Fabric | 분모 누락 또는 한쪽 계산 불가면 null. 수량/주문 혼용·scope/상품 변경 시 비교 제외 |
| 관찰 성숙도 | 완료된 after 관측 길이(상한 L) | 계획 after 길이 L | source_as_of와 after_end, 지연 grace는 별도 | Fabric 선언+계획 경계 A 검증 | 시간 경과만으로 원천 완전성을 보장하지 않음. SOURCE_INCOMPLETE와 분리 |
| 비교 가능 상태 | 모든 정합·coverage 조건의 충족 여부 | 비율 아님 | action+plan+batch+scope | Fabric 상태+A 검증 | LOW_SAMPLE/중첩/변경 경고를 같이 표시. 비교 가능도 인과 효과 입증은 아님 |

before/after에 같은 ticket 문의가 이어져도 최초 문의 cohort 배치 규칙으로 한쪽에만 세는 것을 최소 제안한다. 문의 재발 episode를 보려면 episode 정의·lookback·상품/이슈 귀속을 별도로 합의한다. 여러 issue/tag를 가진 ticket을 합산해 상품의 고유 문의 수를 만들지 않는다. 표본 부족 기준은 현재 위험 TOP10의 S<30/C<5/K<3을 그대로 복사하지 않고 개선 비교용으로 별도 합의한다.

### 4.4 업무량·SLA·추천

| 지표 | 분자 | 분모 | 집계 단위·기간 | 데이터 출처·계산 담당 | 결측/제외 기준 |
|---|---|---|---|---|---|
| 상담사 진행 중 문의 | 현재 유효 배정된 활성 distinct ticket/cycle 수 | 없음 | agent·as_of snapshot, 유형별 분해도 같은 집합 | assignments/tickets/users/scopes/category, A | 종료/이전 회차/무효배정 제외. 무효는 팀 예외로 별도 표시 |
| 미배정 문의 | 활성인데 유효한 현재 배정이 없는 distinct ticket/cycle | 없음 | route team/as_of. UNROUTED는 별도 capability | A, queue의 범위 정책 재사용 | FAILED이면서 유효배정 있는 건은 미배정에 더하지 않음. 미라우팅을 전사 fallback하지 않음 |
| 현재 기한 초과 | 위 활성 집합 중 due_at<as_of | 선택적으로 같은 집합 중 기한 있는 건수(현재 초과 비중) | agent/team/as_of, ticket와 followup 분리 | 현재 stored due_at, A | legacy 기한 표시와 정식 SLA 위반률 구분. 종료 후 준수 이력 복원 금지 |
| 마감 임박 | as_of<=due_at<=as_of+2시간 | 위와 동일하거나 건수만 | 같은 as_of snapshot | A, 임계값은 규칙 버전 | due 없음은 NO_DUE_DATE. exact due는 임박, 아직 초과 아님 |
| 열린 후속 | 유효 담당자의 OPEN/IN_PROGRESS distinct action 수 | 없음 | agent/team/as_of | followup ownership/handover, A | 미인수/무효담당은 개인에서 빼고 팀 대기. ticket 문의 수에 합산 금지 |
| 최초 응답 SLA 준수율 | 합의된 첫 응답이 first-response due 이내인 clock 수 | 합의된 성숙/종결 clock 수 | ticket/cycle/kind·시작 cohort | 향후 SLA facts→Fabric | 현재 UNAVAILABLE/DEFINITION_NOT_AGREED. ACK·pause·휴일·미종결 제외 규칙부터 합의 |
| 해결 SLA 준수율 | 합의된 resolved_at이 resolution due 이내인 clock 수 | 위 kind=RESOLUTION에 해당하는 clock | 위와 동일 | 향후 SLA facts→Fabric | legacy snapshot/종결시각 reset으로 과거를 채우지 않음 |
| 배정 우선순위 | 수치 비율 아님: 기한 상태/기한/대기·후보 부하 정렬 | 없음 | ticket/cycle+as_of+rule_version | A 추천, B 실행 전 재검증 | 후보 없음/unknown 자료/만료를 이유와 표시. AI/ML 점수 없음 |

운영 조회는 동일 SnapshotDB의 인증·scope·목록·카운트를 사용한다. snapshot as_of는 표시/집계용이며 B 확정의 lease 만료 판단을 대체하지 않는다. 확정은 모든 잠금 gate 이후 wall-clock UTC를 다시 검사한다.

## 5. 단계별 구현 순서와 검증 계획

### 5.1 작은 구현 단위

| 순서 | 향후 구현 단위·완료 조건 | 팀 연동과 분리 방법 |
|---|---|---|
| 0 — 설계 완료 | 이 설계 검토 및 기존 dirty 기준점 확인 | 후속 사용자의 명시 구현 요청으로 1단계만 진행. 나머지는 자동 시작하지 않음 |
| 1 — 로컬 구현 완료 | **권한 있는 현재 업무량·미배정·기존 24h 기한 조회**. 0.7.0/0007 capability/snapshot DTO. [실제 검증](evidence/workload-local/README.md) | 새 B worker·AI·Fabric 없이 격리 PostgreSQL로 검증. 추천/실배정과 분리. 실제 계정 grant/배포 없음 |
| 2 — 로컬 구현 완료(0.8.0/0008) | **상품 개선 profile·계획 이력**과 기존 product followup wrapper. owner/status는 재사용, 실제 시행일·비교창 저장 | Fabric 효과 연동 미구현은 UNAVAILABLE/EFFECT_INTEGRATION_NOT_IMPLEMENTED 및 null로 표시하고 등록 업무부터 사용. 기존 후속 terminal/권한 회귀 유지 |
| 3 — 최소 provenance 구현(0.9.0), ticket_cycles 미구현 | **확정 응답 provenance + 전향 ticket_cycles 제안**. 기존 writer transaction에 optional 확장, 과거 UNKNOWN 유지 | B에 새 필수 인자를 강제하기 전에 계약 sample으로 확인. 고정 합성 writer는 실제 AI 품질 증거가 아님 |
| 4 — 최소 로컬 구현(0.9.0/0009) | **품질 표본·사람 평가**. 좁은 검토 권한/자료 조회·불변 revision·표본 내 지표 | AI 없이 합성 provenance와 수동 평가로 API 계약 검증. 사람 rubric 검증은 실제 상담/정책 담당 참여 필요 |
| 5 — 읽기 로컬 구현(0.10.0), 실행 미구현 | **규칙 추천 읽기** 및 B의 재검증·공통 guard 배정 연동 | A 단독 추천은 가능, 실제 실행·동시배정 보장은 B 공동 PG 회귀 뒤에만 보고 |
| 6 | **Fabric analytics-v2 효과 mart**의 수신/검증/불변·원자 게시/조회 | 합성 제출로 parser/정합·scope·게시만 검증. 실제 Export/원천 계산·Fabric 연결은 별도 팀 통합 |
| 7 | 합의된 SLA clock·calendar/pause 정책·역사 지표, 안전한 자동 완료 정의 | 합의 전은 기존 기한 표시/unknown 유지. ML/새 scheduler 도입 없음 |

각 단위의 실제 구현 요청 시점에 다시 현재 head/dirty 상태를 확인한다. migration은 각 단위별 additive로 검토하고 API/OpenAPI·handoff·Fabric 계약은 실제 구현 후 함께 갱신한다. 여러 기능을 하나의 거대한 필수 migration/동시 배포로 묶지 않는다.

### 5.2 검증할 핵심 사례 — 향후 계획, 이번 실행 아님

| 영역 | 로컬에서 검증 가능한 핵심 | 실제 팀 연동이 필요한 부분 |
|---|---|---|
| 보존·migration | 기존 데이터/FK·기존 0001–0006 불변, 새 nullable/빈 테이블부터 시작, unknown backfill, 부적절한 downgrade 거부, 신규 보관 참조 표시 | 실제 배포 DB 권한/backup/복구·이행은 별도 승인 범위 |
| 권한 | CUSTOMER 신기능403, 다른 고객/팀404, capability 없음403, scope 회수/비활성 즉시 반영, 종료 티켓의 QA 표본만 접근·일반 티켓/360는 차단, AGENT 자기 workload만 | 검토자/팀장 역할 운영, 미귀속 검토 팀 지정 절차 |
| 품질 | 정확15/오류3/판단불가2/미평가80, NOT_APPLICABLE/0분모, 중복 sample·동시 review CAS·멱등 재시도, 수정 당시/과거 as_of 판정, VOID·담당변경도 이전 REVIEW를 정확히 해석 | 실제 rubric 일치도, 정책 버전/문서 불변 원본/검색 snapshot 보존, 모델 자기점수와 사람 판정 분리 |
| provenance/회차 | 늦은 worker·이전 cycle·version/token/generation/lease 거부, 메시지/job/suggestion/approval 불일치, trace 부족은 MISSING, audit/provenance 저장 실패 전체 rollback, retry가 새 회차/응답을 만들지 않음 | 실제 B writer가 trace/이관 trigger/origin 연결을 원자 기록하는지 |
| 지표 중복 | 1ticket 2cycle·3attempt가 상담1/진단2, 원본 AUTO 이관1+새 HUMAN cycle 중복0, 후속 HUMAN_CONTINUATION 제외, completed→handoff overlap 명시, tag/issue 다중 행을 distinct ticket로 오인하지 않음 | Fabric cohort/episode·판매 주문 중복 제거 원천 검증 |
| 기간·SLA | UTC/KST 경계·offset·[start,end), due 앞/동일/뒤, 임박2h 경계, null due, 재문의24h reset 사실 보존, 불완전 과거 회차 unknown, 동일 snapshot 목록/카운트 | 영업일/휴일 캘린더, pause/resume, 최초 응답 정의, 새 티켓 재문의 관측 |
| 개선 계획 | product-only, AGENT 상품 owner 거부, 실제 시행일과 DONE 분리, 동일 길이/겹침/미시행/미성숙·계획 revision 변경, unrelated product/ticket 연결 거부, scope 변경 결과 격리 | 실제 시행 확인·상품 ID 매핑, 다중 조치 중첩 판정과 범위 변화 |
| Fabric | v1 그대로 통과/미지필드 거부, v2 5테이블 row/hash·정합, null/0 판매·before0·mixed basis·scope 누락·ID mismatch 거부, 동일 batch 멱등/다른 내용409, 실패/늦은 도착은 current 유지, 하나의 pointer 원자 교체·고정 과거 snapshot·불변 trigger | 실제 Gold 계산 정확성·coverage/source 증거·Export/전송·서비스 인증 운영 |
| 추천/동시성 | 결정론적 정렬·권한 없는 후보 제외·same as_of, 만료/route CAS·티켓 재문의 경쟁. PG 실제 두 session으로 동일 티켓 중복배정 및 서로 다른 티켓의 동일 후보 부하 재계산. scope 변경 guard·잠금순서 경합 | B의 실제 배정 writer 전체가 guard/lease/generation 계약 준수, 재시도·오류의 원자성·실제 worker clock 동기화 |

회귀는 변경된 부분에 따라 선택한다. 업무량 단계는 `test_staff_queues.py`, `test_staff_internal.py`, `test_review_fixes.py`의 유효 배정/범위 관련 사례를 우선 검토한다. 개선 단계는 `test_followups.py`, `test_followup_handover.py`; 확정/provenance 단계는 `test_finalization_contract.py`, `test_postgres_jobs.py`, `test_phase6_postgres.py`; 분석 단계는 `test_analytics.py`, `test_analytics_database.py`를 기준으로 필요한 사례를 확장한다. 이번 문서 작성에서는 이 테스트들을 실행하지 않았다.

SQLite는 DTO/기본 정책 검증만 가능하고 SKIP LOCKED/PG partial UNIQUE 경쟁·advisory lock·trigger·게시 snapshot 동시성 증거는 격리 로컬 PostgreSQL에서 검증한다. 운영/공유 DB에 테스트 suite를 실행하지 않는다. 모든 단계에서 whole-suite 재실행을 관성적으로 하지 말고 영향 범위와 새 실패/회귀 우려를 기준으로 선택한다.

### 5.3 이번에 실제 실행한 확인

- `git rev-parse --show-toplevel`, `git branch --show-current`, `git status --short`, `git log -5`, `git remote get-url origin`, `git diff --stat`, 핵심 diff 및 소스/문서/기존 테스트 코드 읽기.
- AGENTS.md 경로 확인, 동일 목적 문서/모델/라우터 검색. `pyproject.toml`과 main의 버전, migration revision/down_revision을 대조했다.
- 로컬 `.venv-phase5/Scripts/python.exe -m alembic heads`: **0006 (head)**. migration을 적용하거나 DB의 현재 head를 조회한 결과가 아니다.
- 원격 `git ls-remote`는 GitHub DNS 오류로 실패했다. 원격 최신 commit 확인 완료로 보고하지 않는다.
- 최종 문서의 로컬 링크·JSON 예시 구문·구조와 기존 파일 보존을 검사했다. 보존 검사는 작업 시작 때 수집한 담당 폴더 226개 tracked/비ignored untracked 파일의 SHA256과 최종 값을 대조한다. 검증 결과는 아래 완료 기록에 남긴다.
- 앱/API/DB 기동, 업무 pytest, HTTP, Azure, 실제 AI 품질, 실제 Fabric 연동은 이번에 실행하지 않았다. 과거 368 passed 등의 기록을 이번 결과에 합산하지 않는다.

완료 기록: 로컬 참조 35개 모두 존재, JSON 예시 8개 구문 통과, 요청 순서의 6개 본문 절·코드 fence·후행 공백 검사 PASS. `git diff --check` 통과. 시작 시 수집한 기존 226개 파일의 SHA256 변경/삭제 0개, 추가는 이 설계 문서 1개뿐임을 확인했다. 최종 브랜치/HEAD도 `feature/backend-a` / `447c31890c243e1175b805596a84a19720058edf`로 동일하다. 문서의 형식·보존 검사이며 제안 API/스키마의 실행 검증은 아니다.

## 6. 팀 합의가 필요한 사항

### 6.1 해당 구현/지표를 시작하기 전에 먼저 결정할 것

| 항목 | 먼저 합의할 결정 | 담당 | 미합의 시 동작 |
|---|---|---|---|
| 품질 검토 권한·자료 | 종료 티켓의 좁은 표본 접근, 미귀속 검토팀 지정 권한, 검토자 역할·독립성, 보존/hold·PII 최소자료 | A/운영 팀장/Frontend | 기존 권한 확대 금지, 관리자 사실 조회만 유지 |
| 평가 rubric | CORRECT/INCORRECT·정책 MATCH 판정 기준, 적용 불가/판단 불가 조건, 수정·재평가 책임자 | AI/RAG/상담 운영 | UI·스키마 제안 가능, 대외 정답률 미공개 |
| 응답 provenance | 실제 확정 suggestion/approval 연계, 입력/결과 revision 구분, 당시 정책·index/chunk/hash/context 보존 | A/B/AI·RAG | missing을 unknown으로 남김. strict 필수화·과거 역추정 금지 |
| 자동/이관 지표 | 기존 ticket KPI와 새 AUTO 회차 진단 분리, 최초 이관 origin cycle/trigger·사유 taxonomy, 미귀속 scope | A/B/Fabric/PM | 기존 KPI 유지, 새 장기 비율은 정의 미합의 표시 |
| 안전한 자동 완료 | W, 기산점·검토 기준, 재문의/사후 이관·외부 전달·새 ticket 후속을 어디까지 관찰할지, 분모 | 운영/B/AI·RAG/Fabric | UNAVAILABLE, 자동완료를 안전성으로 표현하지 않음 |
| 상품 개선 담당 | 기존 ADMIN owner로 시작할지, AGENT 상품 업무를 새로 지원할지 | A/운영 | 기존 ADMIN/팀 대기 정책으로만 구현 가능 |
| 비교 의미 | 문의 ticket vs episode, 실제 시행시각/지연구간, 동일 창 L, paid order/판매 수량·문의 numerator cohort, 저표본·지연 grace·중첩 규칙 | Fabric/PM/상품 운영 | 계획 등록만 가능, 문의율/효과 지표는 unavailable |
| 비교 scope/식별 | 고정 팀 집합의 역사적 귀속, 제품 canonical UUID/매핑 버전, 부분 팀과 전사 판매 분모 관계 | A/Fabric/B | 정확한 scope·상품 불일치면 비교 중단 |
| Fabric 전환 | analytics-v2 full snapshot 5mart, v2 이후 v1 current 차단, 조치/plan coverage, 서비스 발급·Export 경로 | A/Fabric | v1 기존 수신·조회 유지, 조치 효과 수신은 미구현 |
| B 실행 경계 | 공통 helper 배포/버전 관리, ticket→job→team guard→assignment, scope writer의 guard 참여, route/job/ticket revision 동시 갱신 | A/B | 추천 읽기만 가능, 실제 배정/균형 보장 주장 금지 |
| 정식 SLA | 시작/종료·일시 정지·재문의 reset, WAITING_CUSTOMER, 업무시간/휴일, first-response vs resolution, ACK 인정 여부 | 운영/PM/B/A/Fabric | 기존24h 저장 기한 상태만 표시, 정식 SLA 준수율 unavailable |

코드로 확인한 버전·기존 API·상품 후속 지원·현재 owner 제한·24h 재설정·RBAC/큐 정책은 다시 사용자에게 질문하지 않는다. B SQLite·실제 Fabric schema·AI context는 아직 자료가 없어 공동 확인 대상으로 구분한다.

### 6.2 임시 기본값으로 진행 가능한 것

다음은 실제 구현 요청을 받으면 호환성을 지키며 적용할 수 있는 개발 기본 제안이다. 미합의 지표를 운영 성과로 공개한다는 뜻은 아니다.

- 원문 복제 없이 FK/버전/hash 참조, UTC 저장·KST 표시, [start,end), 누락=null/unknown, 표본·legacy/synthetic 별도 표시.
- 상품 개선은 기존 product followup의 ADMIN/팀 대기·상태를 재사용. 계획 L=14×24시간은 편집 가능한 기본 입력값, 실제 비교 정의는 Fabric 합의 전 unavailable.
- 업무량은 유효 활성 티켓 단순 개수, WAITING_CUSTOMER 별도 분류, 후속 별도 개수. 임박2시간·추천 유효30초·결정론적 tie-break는 rule_version에 고정하고 변경 가능하게 설계.
- 표본은 수동 선별부터 시작하고 selection method/coverage를 공개. 통계적 대표성·가중 추정·ML 점수는 추가하지 않음.
- 모든 새 capability는 기본 미부여, 명시 테스트 grant만 격리 환경에서 사용. 실제 계정 권한 부여는 별도 구현/운영 요청 범위.
- 기존 v1 wire/API·최종 확정 gate·고객 DTO는 그대로 유지. 문서상의 제안 이름은 구현 시 기존 계약과 다시 대조하되, 내부 Python 함수를 HTTP endpoint로 안내하지 않음.

**이미 있는 것:** 상품/티켓 후속, 팀 권한·유효 배정·예외 큐, 24시간 기한값, 자동 응답 공통 확정, Gold 수신·원자 게시.

**남은 것:** 운영 rubric·실제 B/AI 근거 연동, 상품 개선 전후 결과 연동, 설명 가능한 추천. 최소 전향 응답 기록·사람 평가 이력은0.9.0에서 구현했다. 현재 업무량과 상품 개선 계획 등록·이력은 로컬 구현했다.

**팀에 확인할 것:** 사람 평가 기준·표본 권한, 비교 기간/분모·Fabric v2, B 배정 충돌 계약, SLA와 ‘안전한 완료’ 정의.

**첫 구현 단계:** 현재 업무량·미배정·초과/임박 조회는 후속 요청에 따라 로컬0.7.0/0007에 구현했다. [실제 API 계약](workload.md)과 [검증 기록](evidence/workload-local/README.md)을 확인한다. 후속0.8.0/0008에서는 상품 개선 profile·계획 이력도 구현했다. 효과 연동과 나머지 제안 기능은 미구현이다.
