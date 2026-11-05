# openai 브랜치 중복·충돌 검토 — 2026-11-05

## 비교 범위

| 비교 브랜치 | 검토 커밋 | 수정 전 Git 병합 충돌 |
|---|---|---|
| main | 5ddd60a | 없음 |
| feat/openai-inquiry-analysis | fab1400 | 없음; openai에 이미 포함된 과거 이력 |
| feature/backend-a | aa7ba6d | 없음 |
| feature/backend-b | 5596fdd | 루트 .gitignore |
| feature/backend-plus | 5cae230 | 없음 |
| feature/frontend | f983054 | 없음 |

비교는 각 브랜치와 openai 사이만 수행한다. 다른 브랜치끼리의 충돌을
해결하거나 해당 브랜치를 병합하지 않는다. 참고용 v2-local-rag는 프로젝트
검토 대상에서 제외한다.

## 변경

openai가 공용 .gitignore 끝에 추가한 AI 개발 규칙이 Backend B의 동일 위치
변경과 충돌했다. 공용 파일은 원래 main 버전으로 돌리고 AI 규칙을
ai/.gitignore에 한 번만 둔다. 공용 파일에서 이미 상속되는 .env,
가상환경, Python 캐시, 로그 규칙은 반복하지 않는다. .env.example 예외는
AI 폴더에 유지하여 B의 .env.* 규칙과 병합해도 AI 설정 예시가 노출된다.
AI의 압축 파일·에디터 설정 제외 규칙은 다른 팀 폴더에 적용되지 않는다.

ai/의 분석/검증/메타데이터 코드는 Backend A/B의 저장·승인·작업 엔진과
역할이 다르므로 제거하지 않았다. Backend A jobs.claim_jobs의 반환 필드와
backend_adapter의 job_context 필드를 대조했다. Backend B의 generate_reply는
승인된 문자열을 요구하므로 분석 객체를 그대로 주입하지 않는 기존 경계를
유지한다. P1 정책 후보 승인과 운영 knowledge_documents 활성화도 구분한다.

## 검증 및 한계

수정 후 위 6개 브랜치를 각각 git merge-tree --write-tree로 검사하여
모두 충돌 없이 병합 가능한지 확인한다. 실제 merge commit이나 다른
브랜치 변경은 만들지 않는다. 기존 AI 단위 테스트 10개를 다시 실행한다.
이 결과는 현재 커밋 기준의 pairwise Git 병합 가능성 및 기존 AI 동작 검증이다.
다른 팀 브랜치 전체를 함께 합친 결과나 DB/RAG/발송 E2E를 보장하지 않는다.
