# 이번 전달 자료 검증 — 2026-11-03 KST

## 실제 실행

**구현 확인:** 기존 로컬 Python3.13.15/고정 의존성·PostgreSQL16.15 binaries를 재사용했다. Docker/WSL/시스템 설치·의존성 다운로드는 하지 않았다. 새 임시 loopback 클러스터에0001–0006을 순서 적용했고 `alembic check`는 모델과 차이 없음으로 통과했다. schema-only pg_dump로 실제 DDL을 추출했다. [카탈로그](schema-catalog.json), [DDL 추출 증거](schema-verification.json)에 구조와 파일 SHA256을 기록했다. 보조 생성·검증기는 tools/에 있으며 Export 파이프라인이 아니다.

| 검사 | 이번 결과 |
|---|---|
| migration head·모델 대조 | PASS / 유일 head0006, 실제32테이블 |
| PostgreSQL 카탈로그 | 제약138·인덱스57·사용자 trigger7·native ENUM0 |
| 문서 컬럼·타입·NULL·DB default·PK/FK/UNIQUE/CHECK·인덱스·트리거 | 실제 카탈로그에서 schema.md/erd.mmd 자동 생성 |
| 실제 API OpenAPI 생성·발췌 | 관련8경로와 참조 schema. 저장된 앱 전체 계약 검사도 통과 |
| 합성 DB projection | 8테이블9행의 타입/PK/FK와 실제 PostgreSQL INSERT 제약 PASS; 민감 필수값은 비로그인 합성값으로 메모리 보완 후 전부 rollback |
| 제안 Export 파일 | 5파일5행의 JSONL/UTF-8/LF/bytecount/rowcount/SHA256·참조·HMAC 공개 벡터 PASS |
| Gold 합성 요청 | Pydantic Submission/금지필드 allowlist/canonical4해시·행 수/실제 DB validate_submission 의미검증 PASS |
| 응답 예시 | BatchStatus/ErrorEnvelope/KpiResponse의 실제 모델 검사 PASS |
| 비밀정보/실데이터 | 새 자료에 실제 계정·DB URL 자격정보·JWT·해시·상담 원문을 넣지 않음. 합성 공개 HMAC test vector는 비밀키와 구분 |

최종 문서 대조는 컬럼398개·제약138개·인덱스57개와 로컬 링크를 확인했고 실제 로컬 비밀값10종/JWT 패턴/개인 PC 절대경로 검사에서 발견0건이었다. [문서 검증 증거](documentation-verification.json)를 따른다. 문서 도구4개의 Ruff check/format, 기존 엄격 OpenAPI·인수 계약 검사, git diff --check도 통과했다. 기존 작업 트리의 app/main.py 등 Azure 변경은 이번에 수정한 것이 아니라 이전부터 있던 변경으로 보존했다.

이번 샘플 검증은 pytest 전체 통과 수로 부풀리지 않는다. 과거 PostgreSQL368개/HTTP33개 및 배포61건은 이번 실행 결과가 아니다. 실제 HTTP/배포 DB 조회/모델·Fabric·Blob·발송은 이번에 실행하지 않았다. 공식 PostgreSQL 설명 페이지는 문서 확인 목적으로만 읽었으며 Azure 리소스에 접속하지 않았다.

초기 추출 시 Windows background stdout 핸들 대기로 이번에 만든 로컬 임시 서버만 정상 종료하고 도구를 수정했다. 재실행한 최종 추출·모델·샘플 검증이 PASS다. 초기 실패를 성공 검사 건수에 합산하지 않았다. 기존 DB/API를 종료하지 않았고 새 임시 클러스터만 정리했다.

## 미검증·제한

- **현재 배포 스키마 일치 미검증:** 이번에는 Azure DB에 연결하지 않았다. 이전에 저장된 배포증거는 과거 상태 참고용이다. 네트워크 접근을 새로 열지 않았다.
- **실제 Fabric 계약 비교 불가:** 실제 Bronze/Silver schema와 담당자5JSONL/12,008건 manifest를 받지 않았다. 기존 합성schema_contract만 대조했다.
- **미구현:** 운영 Export/Blob 업로드·증분CDC·실제 서비스 emitter/발급·Fabric pipeline. 문서 projection/manifest는 제안이다.
- **팀 합의 필요:** 팀 귀속 이력·episode/완전성·HMAC 조인범위/키관리·미지원 KPI·삭제/tombstone·정정 horizon.
- schema.sql은 portable schema-only 자료여서 역할/권한·비밀·seed·alembic revision 행을 포함하지 않는다. 새 운영 DB 초기화 명령으로 대체하지 않는다.

업무 코드·기존 migration·Azure 데이터/설정·기존 로컬 실행 상태는 변경하지 않았다. commit/push/Actions/팀원 전송은 하지 않았다.
