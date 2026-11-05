# AI / Backend 호환 연결 — 2026-11-05

검토한 원격 커밋: Backend A `aa7ba6d`, Backend B `5596fdd`,
Backend Plus `5cae230`, Frontend `f983054`.
최초 구현은 openai 브랜치에서 수행했다. 이후 사용자 요청으로 개인 백업 저장소 main에
분석 인계를 보완했다. 현재 import·Mock·선택적 오류 계약은
[BACKEND_B_ANALYSIS_HANDOFF_KO.md](BACKEND_B_ANALYSIS_HANDOFF_KO.md)를 우선 참조한다.
팀 저장소/다른 팀 브랜치에는 이번 인계 변경을 반영하지 않았다.

## 실제 호출

```python
from ai.backend_adapter import analyze_job, assert_same_job

# Backend A claim_jobs가 반환한 AUTO job과 권한 확인된 현 회차 원문
result = analyze_job(client, deployment, job, inquiry)
# caller가 DB에서 현재 작업을 다시 읽었을 때 비교할 수 있다.
assert_same_job(result["job"], current_job)
```

result.job에는 job_id/ticket_id/cycle_no/expected_ticket_version,
lease_token/lease_owner/automation_generation/job_kind만 복사한다.
UUID 객체와 UUID 문자열을 받으며 정수 필드에 bool을 허용하지 않는다.
HUMAN/HANDOFF 요청은 모델 호출 전에 거부한다. lease_token은 내부 전용이며
프론트 응답이나 로그로 내보내지 않는다.

result.category는 Backend A 코드(UNKNOWN→UNCLASSIFIED), analysis는 기존
분류·요약·태그·원문 근거·review_required, execution은 실제 모델과 프롬프트 버전이다.
analysis는 답변이 아니므로 draft/allowed/suggestion_id/rule_id를 생성하지 않는다.
Backend B process_auto_jobs의 generate_reply는 승인된 답변 문자열을 요구하므로
이 함수를 그대로 주입하면 안 된다. 현재 B의 운영 gate 미설정 차단을 유지한다.

assert_same_job은 식별자와 회차/버전/generation/lease 변경을 비교한다.
lease 만료·전역 중지·권한·이미 발송된 응답은 DB 트랜잭션 안에서 A의
commit_automatic_reply가 최종 재검증해야 한다. 이 모듈은 저장/발송하지 않는다.

## 정책 근거

integration_contract.eligible_evidence_refs는 caller가 권한 확인해 제공한
knowledge_documents 배열을 받는다. 정확한 원문 SHA-256, UUID, 양의 version,
active=True, approval_status=APPROVED, data_origin=APPLICATION,
allowed_topics와 효력 기간을 확인한다. as_of와 효력 시각은 시간대가 필수다.
effective_from은 포함, effective_to는 제외한다. 하나라도 부적격이면 전체를 거부한다.
합성 자료를 허용하는 기존 구조 추출 함수와 운영 적격 검사를 분리했다.

P1 정책 비교의 APPROVED는 운영 지식 문서 활성화가 아니다.
P1 정책 본문 줄바꿈 정규화/hash와 knowledge_documents의 원문 hash도
서로 바꿔 사용하지 않는다. 실제 검색·승인·규칙·주문 조회는 해당 소유자가 제공해야 한다.

## 검증

로컬에서 모델/클라우드/DB 호출 없이 실행:

```text
python -m unittest test_backend_adapter test_integration_contract -v
```

저장소 루트에서(기존 ai/ 내부 import도 호환 유지):

```text
python -m unittest discover -s ai -p test_backend_adapter.py -v
python -m unittest discover -s ai -p test_integration_contract.py -v
python -m unittest discover -s ai -p test_draft_return.py -v
```

검증 범위: UNKNOWN 변환과 원본 유지, 잘못된/HANDOFF 작업의 호출 차단,
처리 중 lease 변경 및 오래된 회차/버전/generation 거부, 실제 실행 메타데이터,
정책 topic/합성 출처/비활성/효력 경계/시간대 거부. 실제 B worker 및 DB E2E는 별도다.
