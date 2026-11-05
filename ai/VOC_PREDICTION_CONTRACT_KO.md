# VOC 불만 예측 계약 — 2026-11-05

## 현재 구현과 적용 상태

프로젝트 소유자가 2026-11-05 제안 방식을 채택하도록 요청했다.
`analysis.voc_predicted_is_complaint`는 nullable boolean이며 기본 분석에서 예측한다.
`predict_complaint=False`를 명시하면 예측을 실행하지 않고 None(JSON null)을 반환한다.
개인 저장소에 적용한 개발 기준이며, 팀 전체 승인·운영 배포·실모델 품질 검증을 뜻하지 않는다.

| 값 | 의미 |
|---|---|
| true | 불만으로 예측 |
| false | 비불만으로 예측 |
| null | 예측 미실행 또는 정상 분석에서 판단 불가 |

호출 실패는 null 성공으로 바꾸지 않고 기존 예외/오류 계약으로 전달한다.
자료형 검증은 Python의 정확한 bool 또는 None만 허용한다. 0/1/문자열은 거부한다.

## 기본 예측과 명시적 비활성화

```python
from ai.analysis_service import analyze_job_checked

# 기본: 분류·신호·불만 예측을 함께 수행
result = analyze_job_checked(client, deployment, job, inquiry)

# 예측을 끄는 대안. 같은 문의에 위 호출과 중복 실행하지 않는다.
result = analyze_job_checked(client, deployment, job, inquiry, predict_complaint=False)
prediction = result["analysis"]["voc_predicted_is_complaint"]
```

활성화 시 execution.prompt_version은 `signals_v4_voc_v1`이다.
미활성은 기존 `signals_draft_v3`를 유지한다. 예측 여부는 실행 설정·프롬프트 버전으로
구별하고, 최종 판정을 위해 임의로 null을 false로 치환하지 않는다.
기존 analyze_job/analyze_inquiry에도 같은 keyword-only 옵션을 제공한다.
기본 모델 요청은 불만 예측을 포함한 5개 필드 스키마를 사용한다.
명시적으로 끄면 기존 4개 필드 스키마를 사용하고 반환 분석 객체에는 null을 추가한다.
따라서 응답 전체 키 집합을 엄격하게 검사하는 B 소비자는 새 필드 허용 여부를 맞춰야 한다.

## 적용하는 판단 기준

- true: 상품·서비스·처리에 대한 불만·불만족을 명시적으로 표현.
- false: 불만 표현 없이 정보·절차·상태만 문의.
- null: 문맥 부족·모호한 표현, 또는 불만 표현 없이 파손 등 문제 사실만 신고해
  별도 판단 기준이 필요한 사례.
- 반말·환불/반품 요청·상담사 연결·위험 신호만으로 불만이라고 판정하지 않는다.
- 문제 사실만 신고한 경계 사례는 null로 보존하고, 세부 기준 확장은 팀과 별도 합의한다.

## 최종 판정과 분리

AI 응답에 `is_complaint`와 `label_status`를 넣거나 변경하지 않는다.
모델이 이 필드를 출력하면 스키마/검증에서 거부한다.
백엔드가 최종 판정 절차와 저장을 담당하며 UNLABELED이면 is_complaint=NULL을 유지한다.
이 문서는 해당 DB 규칙을 실제 구현·이관한 것이 아니다.
AI 예측을 최종값에 자동 복사하거나 확정하지 않는다.

`review_required` 계산은 기존 그대로다:
`category == UNKNOWN or bool(risk_tags)`.
불만=true/검토=false, 불만=false/검토=true가 모두 가능하다.
자동답변 가능 여부·이관·승인·고객 발송 결정과도 독립적이다.

## 오프라인 검증

```text
python -m unittest discover -s ai -p test_voc_prediction.py -v
python -m ai.examples.backend_b_analysis
python -m ai.examples.backend_b_analysis --no-predict-complaint
```

신규 8개 테스트로 자료형, true/false/null, 미활성화, review 독립성,
최종 판정 필드 거부, 응답 구조 오류와 프로그래밍 오류 구분 등을 검증했다.
합성 Mock 결과이며 실제 모델의 예측 품질·정확도를 검증한 수치가 아니다.

과거 신호 16건 점검 도구 check_signals.py는 비교 가능성을 위해 기존 프롬프트를
predict_complaint=False로 명시 유지한다. 해당 점검 수치는 VOC 예측 평가가 아니다.
