# Backend B 분석 단계 인계 — 2026-11-05

최신 추가: VOC nullable 예측 필드와 타입별 오류 경계 보완.
상세는 [VOC_PREDICTION_CONTRACT_KO.md](VOC_PREDICTION_CONTRACT_KO.md)를 따른다.

11.05.8~11.05.12 대화의 책임 분리를 반영한 개인 백업 main 변경이다.
팀 저장소의 openai 브랜치에 반영하거나 B 담당자가 오류 계약을 채택한 것은 아니다.
v2·다른 팀 브랜치는 변경하지 않는다.

## 현재 범위

- OpenAI 담당: 분류·요약·검토 신호와 원문 근거 추출, 분석 출력 검증.
- RAG/AI Search 담당: 정책·FAQ 검색과 사용 가능한 문서 메타데이터 제공.
- A/B 담당: 권한·현재 DB 작업·lease 만료·회차/버전·중지/generation 최종 검사,
  재시도 정책·상담사 이관·배정·DB 상태 변경·최종 응답 확정.
- 분석 성공은 AUTO 작업 SUCCEEDED, 문의 종결, 고객 발송을 뜻하지 않는다.
- 답변 생성, 신뢰도, 정책 검색 결과, AUTO/HANDOFF 결정값은 분석 응답에 없다.
  `risk_evidence`는 문의 원문 인용이며 정책/RAG 근거가 아니다.

## 호출과 import

프로젝트 가상환경에서 저장소 루트를 Python 검색 경로에 포함한다.
아래 명령은 저장소 루트에서 실행한다. Backend A의 별도 `app` 패키지 경로와
AI 저장소 루트는 각각 필요한 경로이며 한쪽을 다른 쪽으로 덮어쓰지 않는다.

```text
python -m pip install -r ai/requirements.txt
python -m ai.examples.backend_b_analysis
```

```python
from ai.backend_adapter import analyze_job, assert_same_job
from ai.analysis_service import AIAnalysisError, analyze_job_checked

# 기존 호출을 유지할 경우: 기존 예외 그대로
analysis = analyze_job(client, deployment, claimed_job, authorized_inquiry)

# 오류 분류를 채택하는 caller용 선택적 진입점: 성공 응답은 동일
try:
    analysis = analyze_job_checked(client, deployment, claimed_job, authorized_inquiry)
except AIAnalysisError as error:
    failure = error.as_dict()  # {code, retryable}만 포함
    # B가 DB 상태와 정책을 재검사해 처리한다. 이 예시 자체는 상태를 변경하지 않음.
```

위 두 호출은 대안이며 같은 문의에 둘 다 실행하지 않는다.
`analyze_job_checked`는 임시로 추가한 이름이며 B의 기존 `generate_reply`에 주입하지 않는다.
client는 B가 주입하고 timeout과 SDK `max_retries=0`을 명시해 중첩 재시도를 피한다.
이 함수는 client를 만들거나 API 재시도 루프·DB 트랜잭션을 실행하지 않는다.
총 작업 시간이 lease를 넘지 않도록 하는 정책과 갱신/폐기 책임은 B에 있다.
기존 `ai/` 디렉터리 안의 `from backend_adapter import ...`도 유지한다.
광범위한 ImportError fallback 대신 package 실행 여부로 상대 import를 선택한다.

## 요청·응답

`ai/examples/backend_b_analysis.py`에 실행 가능한 합성 요청과 출력 예시가 있다.
실제 요청에는 DB claim 결과의 다음 필드를 그대로 전달한다.

| 입력 | 조건 |
|---|---|
| job_id / ticket_id / lease_token | UUID 객체 또는 유효한 UUID 문자열 |
| cycle_no / expected_ticket_version / automation_generation | 양의 정수, bool 제외 |
| lease_owner | 공백이 아닌 128자 이하 문자열 |
| job_kind | AUTO만 허용. HUMAN/HANDOFF 처리는 호출자가 우선 분리 |
| inquiry | 권한 확인된 현 회차 원문, 공백만인 값 제외, 최대 10,000자 |
| client / deployment | 설정된 모델 client와 배포명 |

이전 이력·상품·주문 객체는 현재 함수 인자가 아니다. 답변 생성 단계에서 별도 합의한다.

성공 객체의 최상위 필드는 `job`, `category`, `analysis`, `execution`이다.
`analysis`는 `category, summary, risk_tags, risk_evidence, review_required,
voc_predicted_is_complaint`를 포함한다. 새 필드는 기본 null이고 예측 활성화 시 bool/null이다.
분류는 DELIVERY/RETURN/REFUND/PRODUCT/PAYMENT/ACCOUNT/UNKNOWN.
최상위 category만 UNKNOWN→UNCLASSIFIED로 바뀌며 원본 analysis.category는 유지한다.
신호는 HUMAN_REQUEST/EXCEPTION/ACCOUNT_SECURITY.
`review_required = category == UNKNOWN or bool(risk_tags)`이며 false도 자동 발송 허가가 아니다.
각 risk_evidence는 `{tag, quote}`이고 quote는 문의 원문의 연속 구절이어야 한다.
execution에는 실제 모델 응답의 model_version과 실행 프롬프트 버전이 들어간다.
job 및 lease_token은 내부 전용이며 프론트/로그로 전달하지 않는다.

분석 중 전달 객체 변경은 내부에서 비교한다. DB를 재조회하지는 않는다.
`assert_same_job(analysis['job'], current_db_job)`은 별도 재조회 결과 비교에 사용할 수 있지만
DB 트랜잭션의 만료·중지·권한·중복 발송 검사를 대체하지 않는다.

## 선택적 오류 계약 v1 — B와 합의할 초안

기존 analyze_job의 동작·예외는 유지한다. 새 wrapper를 선택한 caller에만 적용한다.
성공 객체에 error 필드나 빈 분석을 섞지 않고 AIAnalysisError를 발생시킨다.
`error.as_dict()`는 고정 code와 bool retryable만 반환한다. SDK 메시지·원문·토큰을 넣지 않는다.

| code | retryable | 의미 |
|---|---|---|
| INVALID_JOB_CONTEXT | false | 잘못된 작업 필드 또는 AUTO 이외 작업 |
| INVALID_INQUIRY | false | 입력 자료형·공백·길이 오류 |
| INVALID_DEPLOYMENT | false | 빈/잘못된 배포명 |
| INVALID_ANALYSIS_OPTIONS | false | predict_complaint가 정확한 bool이 아님 |
| STALE_JOB_CONTEXT | false | 전달 작업 정보가 분석 중 변경 |
| AI_TIMEOUT | true | SDK 타임아웃 |
| AI_CONNECTION_FAILED | true | SDK 연결 오류 |
| AI_RATE_LIMITED | true | SDK 호출 제한 |
| AI_AUTHENTICATION_FAILED | false | SDK 인증 오류 |
| AI_PERMISSION_DENIED | false | SDK 권한 오류 |
| AI_SERVICE_UNAVAILABLE | true | SDK HTTP 408/409/429/5xx |
| AI_REQUEST_REJECTED | false | 그 외 SDK HTTP 오류 |
| INVALID_ANALYSIS_RESPONSE | false | 파싱·출력·실행 메타데이터 검증 실패, 미완료·거절 포함 |

retryable=true는 일시적 실패의 재시도 후보라는 뜻이다. B가 최신 DB 상태·lease·중지·횟수·지연을
검사하기 전에는 재시도하지 않는다. false도 자동 HANDOFF 명령이 아니다. 설정 오류·오래된 결과·
출력 오류는 서로 다르게 처리할 수 있다. 명시 검증 실패 전용 AnalysisResponseError,
JobContextError, StaleJobContextError만 wrapper에서 변환한다(기존 ValueError의 하위 타입).
임의 ValueError/TypeError/KeyError/AttributeError 등 프로그래밍 오류는 원래 예외를 전파한다.
응답의 status/output/message content/output_text/model 누락·형식은 명시 검증한다.
운영 로그에서 임의 예외/요청 객체 전체를 출력하지 않는다.
근거 부족 코드는 아직 없다. 현재 분석 단계가 정책 검색을 하지 않기 때문이다.

## Mock과 검증

`ai/mock_analysis.py`의 MockAnalysisClient를 명시적으로 주입한다. delivery/human_request/unknown/complaint
합성 시나리오를 제공하며 fixture 원문과 다른 문의는 거부한다. 실모델 실패 시 Mock으로
자동 대체하지 않는다. mock model_version은 MOCK_ANALYSIS_ONLY이고 운영 관측값으로 집계하지 않는다.
이 예시는 B의 발송용 mock provider와 다르며 승인된 고객 답변을 생성하지 않는다.

```text
python -m unittest discover -s ai -p test_analysis_service.py -v
python -m unittest discover -s ai -p test_backend_adapter.py -v
python -m unittest discover -s ai -p test_integration_contract.py -v
python -m unittest discover -s ai -p test_draft_return.py -v
python -m ai.examples.backend_b_analysis
python -m unittest discover -s ai -p test_voc_prediction.py -v
python -m ai.examples.backend_b_analysis --predict-complaint
```

이 명령은 모델·DB 호출 없이 실행한다. SDK/Azure 의존성은 import용으로 설치해야 한다.
실제 B worker·PostgreSQL E2E와 실모델 테스트는 별도이며 이번 변경의 검증 범위가 아니다.

## 민원 여부와 다음 합의

현재 `voc_predicted_is_complaint`는 구현했다. 기본 null이며 predict_complaint=True에서만
제안 기준으로 예측한다. nullable boolean 의미는 팀 전달 내용을 반영했고 내용 판단 기준은
합의 대기다. `is_complaint`/label_status의 확정·저장은 백엔드 영역으로 구현하지 않는다.
신호나 기존 분류를 임의로 불만 여부로 변환하지 않으며 예측값을 최종값에 복사하지 않는다.
RAG·답변 생성·정책 승인·B 작업 완료는 이번 계약과 분리한다. 테스트 날짜를 임의 약속하지 않는다.
