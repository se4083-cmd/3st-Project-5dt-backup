# 팀 API·RAG로 교체하는 위치

## 2026-11-04 확인한 기준

아래는 이번 작업에서 GitHub 내용을 직접 읽은 기준이다. 원격 코드를 병합하거나 팀 환경에서 실행한 결과는 아니다.

| 대상 | 확인한 커밋 | 이번 연결에 영향을 주는 내용 |
| --- | --- | --- |
| 개인 백업 `main` | `0d598c47f870862aab37152a76c9b9a95be91cdc` | 기본 폴더와 README. 새 v2 브랜치의 기반이며 main은 유지 |
| 팀 `openai` | `e9829b85ec0410bf85237d00f3f87d985e13ba0c` | 문의 분류·검토 신호, 공식 참고자료 73개 분리. manifest상 팀 승인 pending·검색/색인/R10/초안 실행 false |
| 팀 `feature/backend-a` | `968dfe9bd6325e562aa5d31a15aa02b84ddb433a` | cycle/version/lease/전역 generation과 최종 저장 경계 |
| 팀 `feature/backend-b` | `1106e00912703c4115b23d211969971f5ff908cd` | PostgreSQL worker·claim·재시도·배정·AI 결과 검증기 추가. 실제 RAG 구현은 확인되지 않음 |
| 팀 `feature/backend-plus` | `77cba3a4892160eb2f8a1afc8f51b28a0f1282bb` | P1 데이터 기반·모니터링 GET 추가. 문서상 AI provider/producer/worker/실제 Fabric probe는 별도 |
| 팀 `feature/frontend` | `46f2ca6cab56ae493087f3dde43ceb7acfc111f3` | React 관리자 화면과 합의용 API 계약. 확정 백엔드 API라고 간주하지 않음 |

이전 대화의 “Backend B는 main과 동일”은 이 기준에서는 더 이상 맞지 않는다. 작업 처리 코드의 진전은 반영하되, 실제 검색·생성·발송 E2E가 완료됐다고 해석하지 않는다.

## 현재 파일 경계

| 연결 영역 | 현재 파일 | 교체 방식 |
| --- | --- | --- |
| 프런트 HTTP | `frontend/src/lib/api/client.ts` | 인증 헤더와 각 경로/DTO를 실제 계약으로 변환 |
| 업무 상태 저장 | `backend/src/repository.mjs` | 팀 PostgreSQL 저장 함수와 작업 lease/fence로 연결 |
| 업무 명령 | `backend/src/operations-service.mjs` | 서버가 확보한 근거·주문·권한으로 최종 gate 실행 |
| 검색/생성 | `ai/rag/index.mjs` | 같은 provider 출력으로 정식 RAG 검색과 생성 결과 제공 |
| 분류·근거 규격 변환 | `shared/contracts/team-contract.mjs` | DELIVERY/UNKNOWN, UUID·version·hash, B 입력 규격 변환 |
| 개발용 문서 | `data/rag/` | 승인된 corpus로 전환할 때 source/scope/approval/version 재검증 |

`VITE_API_BASE_URL`은 같은 v2 계약을 제공하는 서버의 주소를 바꾸는 기능이다. 이를 팀 API 주소로 바꾸기만 하면 필드와 권한이 자동 호환되는 것은 아니다. 브라우저에는 API 키, DB 비밀번호, 서비스 토큰을 넣지 않는다.

## v2 로컬 경로와 계획 경로

현재 `/api/v2/*`는 독립 로컬 계약이다. 팀 계획의 `/api/tickets`, `/api/agent/tickets`, `/api/admin/automation/switch`와 구분한다.

| v2 로컬 동작 | 향후 팀 계약에서 연결할 영역 |
| --- | --- |
| `GET /api/v2/state` | 관리자 큐/상세/자동화 상태를 권한 범위별 조회 |
| `POST /api/v2/actions` | 배정·초안·승인·응답·후속·전역 중지 명령별 API |
| `POST /api/v2/rag/ask` | 담당 B worker의 검색·생성 callback |
| `GET /api/v2/customer` 및 `/{id}` | 본인 문의 목록/상세 공개 projection |
| `GET /api/v2/orders` | 본인 주문 현재 상태 API |

v2의 개발용 `X-Demo-Role`은 실제 인증이 아니다. 정식 연결 시 서버가 검증하는 JWT/세션 및 객체 권한으로 교체한다. 클라이언트의 역할 문자열을 신뢰하는 방식으로 운영 서버에 연결하지 않는다.

## 변환 규칙

- 화면의 `SHIPPING`은 OpenAI/팀 데이터의 `DELIVERY`로 변환한다.
- OpenAI `UNKNOWN`과 직원 상세 `UNCLASSIFIED`는 명시적으로 변환한다. `review_required`를 화면 `REVIEW`나 자동 승인으로 바꾸지 않는다.
- v2 질문 상한은 10,000자다. 확인한 기존 OpenAI 함수는 Python `len(inquiry)>4000`을 거부한다. `legacyAnalysisInput`은 4,000자를 넘으면 연결 보완 필요를 반환하고 원문을 자르지 않는다.
- 근거에는 문서 UUID, 양의 version, SHA-256, clause ID를 넣는다. 검색 점수는 승인이나 사실 확률이 아니다.
- B의 현재 `validate_ai_result`는 `draft`, `allowed`, `suggestion_id`, `rule_id`, 비어 있지 않은 `evidence_refs`를 요구한다. 이 검증기가 문서 유효성·소유권·최신성 전체를 대신 검증하지는 않는다.
- `toBackendBEnvelope`는 명시적 별도 backend 결정이 없으면 `allowed=false`다. 이번 `DEMO_ONLY` 근거는 실제 운영 승인을 뜻하지 않으므로 항상 false로 변환한다. 로컬 시연의 자동 완료와 운영 발송 승인을 구분한다.

## 최종 저장 시 반드시 연결할 것

팀 Backend A의 최종 확정 함수는 현재 티켓 회차·버전, 작업 kind/status, token/worker, lease 만료, 최종 응답 중복, 필수 후속, 전역 generation을 재확인한다. 생성 후 결과가 늦게 돌아온 경우 이전 회차 응답을 새 회차로 복사하면 안 된다.

v2는 이미 확정된 답변이 있고 마지막 필수 후속까지 끝나면 로컬 gate를 거쳐 해결 상태로 전환한다. 팀 A의 후속 PATCH 자체가 문의를 자동 해결하는 것은 아니므로, 실제 연결에서는 B가 사람 해결 gate와 최종 상태 저장을 같은 트랜잭션에 연결해야 한다.

v2 SQLite 트랜잭션과 revision CAS는 단일 로컬 참조 구현이다. PostgreSQL의 동시 worker·SKIP LOCKED·row lock·lease 복구·외부 outbox를 검증한 것으로 해석하지 않는다. 실제 발송/환불/주문 변경은 이 프로젝트에 연결되어 있지 않다.

## 추천 연결 순서

1. 팀이 확정한 인증·DTO·경로로 프런트 adapter를 연결하고 401/403/409 동작을 확인한다.
2. 승인된 문서를 정식 검색기에 넣고 provider 결과의 UUID/version/hash를 검증한다.
3. B worker의 생성 callback에 검색·생성 결과를 넣고, 별도 gate가 통과한 결과만 A 저장 경계로 보낸다.
4. 재문의·직접 사람 요청·중지 중 이전 결과, 만료 lease, 중복 최종 응답을 PostgreSQL에서 재검증한다.
5. 외부 발송은 outbox와 외부 멱등키를 연결한 후 별도로 검증한다.

## 확인한 원문

- [OpenAI 상태](https://github.com/InSSOOO/cs-flow-ai/blob/e9829b85ec0410bf85237d00f3f87d985e13ba0c/ai/OPENAI_STATUS.md)
- [73개 참고자료 준비 manifest](https://github.com/InSSOOO/cs-flow-ai/blob/e9829b85ec0410bf85237d00f3f87d985e13ba0c/ai/reference_review_v01/preparation_manifest.json)
- [Backend A/B 저장 계약](https://github.com/InSSOOO/cs-flow-ai/blob/968dfe9bd6325e562aa5d31a15aa02b84ddb433a/backend/backend-a/docs/backend-b-contract.md)
- [Backend B AI 결과 검증기](https://github.com/InSSOOO/cs-flow-ai/blob/1106e00912703c4115b23d211969971f5ff908cd/backend/app/automation/postgres/ai_adapter.py)
- [Backend B worker](https://github.com/InSSOOO/cs-flow-ai/blob/1106e00912703c4115b23d211969971f5ff908cd/backend/app/automation/postgres/worker.py)
- [프런트 합의용 API 계약](https://github.com/InSSOOO/cs-flow-ai/blob/46f2ca6cab56ae493087f3dde43ceb7acfc111f3/frontend/docs/api-contract.md)
- [Backend Plus P1 범위](https://github.com/InSSOOO/cs-flow-ai/blob/77cba3a4892160eb2f8a1afc8f51b28a0f1282bb/docs/P1_DESIGN_DIFFERENCES.md)
