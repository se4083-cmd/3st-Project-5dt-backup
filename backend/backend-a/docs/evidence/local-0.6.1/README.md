# 기존0.6.1 로컬 검증 증거

이 폴더는 저장소 반입 전 원본0.6.1에서 실행한 결과의 복사본이다. 이번 commit/push 과정의 새 전체 테스트 결과가 아니다.

- postgres-results.xml: 전체368 tests, 실패/skip0,398.277초. 개인 PC hostname 속성만 제거.
- http-integration-report.json: 실제 loopback Uvicorn/PostgreSQL33개 흐름 PASS, LOCAL_SYNTHETIC. 토큰·비밀번호·원문 없음.
- final-verification-summary.json: 기존 실행 환경/부분 결과와 원본 코드SHA256. 반입 시 테스트 placeholder/Alembic 경로/문서가 변경될 수 있으므로 이 SHA를 반입본 전체와 같다고 주장하지 않는다.
- openapi-compatibility-report.json: Python3.12 HTTP 문구 모사/엄격 계약 비교. 실제 Linux/Python3.12 전체 재실행 증거는 아니다.

원시 로그/실행 환경파일/PID/state/가상환경/PG binary·데이터는 제외했다. 이번 반입에서 새로 실행한 부분 검증은 ../../repository-integration.md를 따른다. 두 수치를 합산하지 않는다. 실제 B/AI/RAG/Fabric/발송/클라우드 통합은 미검증이다.
