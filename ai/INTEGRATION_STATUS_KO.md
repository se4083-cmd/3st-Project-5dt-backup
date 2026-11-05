2026-11-05 갱신: 아래는 11월 4일 기록입니다. 최신 원격 계약을 확인하고 backend_adapter 및 운영 정책 적격 검증을 추가했습니다. 현재 호출법과 한계는 BACKEND_COMPATIBILITY_KO.md를 따릅니다.

# OpenAI 연결 규격 반영 — 2026-11-04

사용자가 제공한 최신 브랜치 비교와 공통 규격을 기준으로 수정했습니다.
원격 조회·다른 팀 코드 수정·모델 API 호출은 하지 않습니다.

- 분류·신호 함수와 CLI, 사례 검증기는 10,000자까지 받습니다. 공백 여부만
  검사하며 원문 strip·절단·사전 요약 없이 모델에 전달합니다. 초과·공백 입력은
  기존 ValueError/SystemExit 경로로 거부합니다. 모델의 미완료·거절·파싱 오류는
  기존 실패 경로를 유지합니다. 실제 배포의 10,000자 품질/시간 검증은 미실행입니다.
- 분류 함수 `classify_inquiry`를 추출했습니다. 기존 CLI 출력 구조와 프롬프트는 유지합니다.
- `integration_contract.backend_category`는 전달 경계에서만 UNKNOWN을 UNCLASSIFIED로
  변환합니다. 원본 분석 결과와 review_required는 그대로 유지해야 합니다.
  실제 백엔드 호출부가 없어 적용 대기입니다. REVIEW·승인·발송 상태를 만들지 않습니다.
- `policy_body_hash`와 `draft_content_hash`는 각각 body/draft 원문 UTF-8 SHA-256입니다.
  정규화하지 않으며 JSONL 전체 파일 해시와 별개입니다.
- `evidence_refs_from_documents`는 애플리케이션이 제공한 정책 객체 배열의 UUID,
  양의 정수 version, body와 일치하는 content_hash만 참조 배열로 추출합니다.
  승인·유효기간·allowed_topics의 적격성 검사가 아니며, 합성/비활성/미승인 정책을
  운영에 허용하는 함수가 아닙니다. 이를 모델 출력에서 호출해서는 안 됩니다.
- `execution_metadata(response, prompt_version=실행모듈.PROMPT_VERSION)`는 실제 응답의
  model과 활성 프롬프트 버전을 기록합니다. 배포명·NONE·NOT_LLM_GENERATED 예시로
  실제 실행값을 대신하지 않습니다. 생성/저장 호출부가 없어 자동 저장 연결은 대기입니다.
- 현재 분석 함수는 ticket_id/cycle_no/revision/job 정보를 받지 않습니다. 임의 필드나
  endpoint는 추가하지 않았습니다. 향후 caller가 분석 결과와 별도로 기존 작업 정보를
  유지해야 합니다. 만료·중지·오래된 결과 차단은 백엔드 책임이며 구현/검증하지 않았습니다.
- 일반 API의 배열·객체는 그대로 취급합니다. 현재 Lakehouse 입력 경로가 없어 JSON
  문자열 자동 디코딩은 추가하지 않았습니다. 향후 해당 경로에서 확정된 필드만 한 번 해석해야 합니다.

## 남은 연결 입력

73개 공식 참고자료의 원래 id/source/source_version과 기존 파일은 수정하지 않았습니다.
문자열 id → 실제 문서 UUID 매핑, 정수 정책 version 규칙, body로 사용할 원문 범위,
실제 승인 상태값·효력 기간·사용 적격성 규칙이 필요합니다. UUID/버전/승인을 생성하지 않습니다.
공유 합성 정책 30개는 이 자료에 섞거나 대체하지 않습니다.

답변 저장에는 실제 ticket_id/cycle_no/revision, category/draft/evidence_refs,
order_snapshot/gate_results, prompt_version/model_version/content_hash를 전달하는
백엔드 호출 규격과 책임 확정이 필요합니다. nullable 예시로 필수 검증을 완화하지 않습니다.
현재 요약은 답변 draft가 아니므로 이를 저장용 초안으로 변환하지 않습니다.
gate_results·승인 결과·주문 snapshot·신뢰도는 합성하거나 기본 성공값을 넣지 않습니다.
반품 생성 진입점은 NotImplementedError 상태를 유지하며 RAG·R10·E2E는 미실행입니다.

최상위 실행용 사본과 Git 저장소 ai/의 해당 분석·검증·연결 도구를 동일하게 유지합니다.
로컬 검증: 저장소에서 `python -m unittest discover -s ai -p test_integration_contract.py -v`,
`python -m unittest discover -s ai -p test_draft_return.py -v`.
