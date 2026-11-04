# 문서 중립화 및 계약 보존 검증

2026-11-04 KST. Backend A 0.11.0 / migration 파일 head0011의 문서 정리 기록이다. 애플리케이션·migration·업무 테스트·runtime 스크립트는 변경하지 않았다.

## 정리 범위

- 개인 이름·호칭은 Frontend, Backend A/B, Fabric 등 역할로 표기했다. 인수 문서의 메시지 형식 요약은 기술 계약·연동 우선순위에 통합했다.
- 과거 작업 안내는 해당 버전의 검증 기준·제약으로 정리했다. 구현/미구현, 실패·skip·검증 한계와 과거 실행 수치는 유지했다.
- JUnit의 중립화된 로컬 경로를 `<BACKEND_A_ROOT>`로 단순화했다. 테스트 결과·시간·사유·suite/testcase 속성은 동일하다.
- 기존 Fabric 미커밋 자료도 같은 문서 기준으로 정리했지만, 새 샘플·스키마·Manifest 추가는 문서 중립화 커밋에 포함하지 않는다. 기존 변경과 겹치는 두 추적 문서는 중립화 차이만 index에 반영한다.
- API/DB 계약·리소스명·서비스 식별자·저장소 URL·합성 계정/공개 HMAC 예시·외부 출처는 유지했다. Git 작성자와 과거 이력은 변경하지 않았다.

## 실제 수행한 검사

| 검사 | 결과와 범위 |
|---|---|
| 추적 파일 및 기존 Fabric 미커밋 파일의 개인 이름·호칭·메시지 형식 잔존 검색 | 정리 대상 표현 없음. 담당 폴더 밖 추적 파일에서도 대상 이름 발견 없음 |
| 상대 파일 링크·Markdown 코드 fence·JSON/XML/Python 구문 | 검사. 과거 고정 DDL·카탈로그·패키지/소스 hash는 해당 시점의 기록으로 유지 |
| `python -m scripts.check_handoff_contract` | PASS. 실제 OpenAPI·DTO·요청/권한 형태·canonical 벡터. DB/네트워크 연결 없음 |
| `python docs/fabric-data-contract/tools/verify_export_proposal.py` | PASS. 로컬 미커밋 제안6파일/6행의 필수값·타입·PK·확인 가능한 FK·HMAC·Manifest bytes/hash. Git 공유 범위의 Export 확장을 의미하지 않음 |
| 문서 원본 생성기 | 비교 문서를 임시 폴더에 재생성해 중립화된 본문과 일치 확인. 보관 DDL·카탈로그를 최신 DB 자료로 재생성하지 않음 |
| 로컬 ZIP 생성기 | 별도 QA 경로에서16멤버 패키지 생성. 계약 검토 문서 포함 및 상대 링크 확인. 기존 출력 재사용은 거부하며 기존 전달 ZIP의 SHA256 보존 확인 |
| 민감정보 및 staged diff | 명시한 경로만 stage. 환경 파일·DB·캐시·ZIP·운영 비밀값 제외. `git diff --check` 확인 |

전체 업무 테스트·PostgreSQL·Azure·B Worker·Fabric·Frontend 연동은 재실행하지 않았다. 과거 PASS 수를 이번 검사 수로 합산하지 않는다. ZIP은 ignored 로컬 검증 산출물이며 Git에 추가하지 않는다.

9d427ea 문서 정리 단계에서는 기존 전달 ZIP을 변경하지 않았다. 이후 [전달 아카이브 정리](../../delivery-archives.md)에서 원본을 별도 백업하고 현재 전달 경로의 문서를 갱신했다. 백업과 Git 과거 이력에는 이전 표현이 남으며, 현재 문서 중립화가 그 원본까지 수정했다는 뜻은 아니다.
