# OpenAI 문의 분석

이 경로는 문의 분류·요약·검토 신호와 백엔드 분석 연결 도구다.
AI Search 검색 엔진, 고객 답변 생성, 승인·발송·작업 상태 변경은 현재 구현 범위가 아니다.

- [Backend B 분석 인계: import·요청/응답·Mock·오류](BACKEND_B_ANALYSIS_HANDOFF_KO.md)
- [VOC 예측 필드: 기본 활성화·nullable boolean·최종값 분리](VOC_PREDICTION_CONTRACT_KO.md)
- [정책 근거 적격 검사와 책임 경계](BACKEND_COMPATIBILITY_KO.md)
- [최신 상태 및 과거 검증 기록](OPENAI_STATUS.md)
- [공식 참고자료 73개 분리와 R10 정의](reference_review_v01/README.md)

저장소 루트에서 모델·DB 호출 없는 인계 예시:

```text
python -m pip install -r ai/requirements.txt
python -m ai.examples.backend_b_analysis
```

실제 API 호출은 별도 모델 client를 주입할 때만 발생한다. 예시 Mock은 운영에 사용하지 않는다.
