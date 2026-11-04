# 로컬 v2 API

이 API는 React 화면이 실제 HTTP로 호출하는 Node.js 24 + SQLite 개발용 구현이다. 문서 검색, 문의 회차, 검토 승인, 후속, 자동화 중지와 저장을 서버가 처리한다. 팀 FastAPI/PostgreSQL worker나 외부 고객 채널에는 연결하지 않는다.

## 실행과 데이터

루트에서 `npm run dev`로 화면과 API를 같은 주소에서 실행한다. 빌드 결과는 `npm run build` 뒤 `npm start`로 실행한다. 기본 주소는 `http://127.0.0.1:5173`이며, 실행 스크립트의 `HOST`·`PORT` 설정을 따른다. 상태는 `.local/runtime.sqlite`에 남고 브라우저를 새로 열거나 서버를 다시 시작해도 유지된다. 이 파일은 Git에 포함하지 않는다.

`database/schema.sql`은 상태·멱등 요청·최소 이벤트·회차별 최종 답변·합성 주문의 저장 구조다. `database/demo-orders.json`에는 합성 주문 3개가 있다. 이 주문 파일은 새 DB를 만들 때 초기값으로 사용한다. 이미 만들어진 DB의 주문을 파일 수정으로 덮어쓰지 않는다. UI의 초기화는 문의 시연 상태를 새 회차 묶음으로 되돌리며, 저장소를 삭제하는 명령이 아니다.

## 역할과 요청 헤더

다음 헤더는 로컬 시연에서 역할과 합성 고객을 선택하기 위한 값이다. 비밀번호·JWT·실제 로그인 검증은 아니다. 운영 연결에서는 `frontend/src/lib/api/client.ts`와 서버 신원 경계를 팀의 인증 계약으로 바꿔야 한다.

| 헤더 | 값 |
| --- | --- |
| `X-Demo-Role` | `admin`, `agent`, `customer` 중 하나. 상태·업무 API에서는 필수 |
| `X-Demo-Customer` | `DEMO-CUSTOMER-001` 기본값 또는 `DEMO-CUSTOMER-002` |
| `Content-Type` | POST는 `application/json` |

서버는 선택한 역할의 명령 범위와 고객 문의 소유권을 확인한다. 고객 상세는 내부 초안·승인·메모·근거·배정·감사 이벤트를 포함하지 않는 공개 projection이다. 다른 고객 문의와 없는 문의는 같은 404 응답을 낸다. 개인정보를 포함한 실제 고객 자료를 넣지 않는다. 인식 가능한 연락처·주소·식별번호·결제번호·인증정보는 저장 전에 거부하며, 이 검사만으로 임의의 자유 입력이 비민감 정보임을 보증하지는 않는다.

## 제공하는 경로

| 방식·경로 | 허용 역할 | 주요 응답 |
| --- | --- | --- |
| `GET /api/status` | 공개 | 실행 모드·저장 방식·외부 모델/운영 백엔드 연결 여부 |
| `GET /api/v2/identity` | 전체 | 현재 시연 역할과 합성 고객 |
| `GET /api/v2/state` | admin, agent | `{state, revision, runtime}` |
| `GET /api/v2/customer` | 전체 | 선택 고객의 공개 문의 `{tickets, revision}` |
| `GET /api/v2/customer/{id}` | 전체 | 선택 고객의 공개 상세 `{ticket, revision}` |
| `GET /api/v2/orders` | 전체 | 선택 고객 소유 합성 주문 `{orders, revision}` |
| `GET /api/v2/rag/documents` | admin, agent | 문서·버전·유효성·예시 질문 `{knowledge, runtime}` |
| `GET /api/v2/rag/knowledge` | admin, agent | 위 문서 조회와 같은 응답 |
| `GET /api/v2/metrics` | admin, agent | 로컬 문의 원장에서 계산한 운영 지표 `{metrics, revision, source}` |
| `GET /api/v2/products/{uuid}/operations` | admin, agent | 해당 합성 상품에 연결한 현재 로컬 문의·후속과 개수 |
| `POST /api/v2/rag/ask` | 미리보기는 admin/agent, 접수는 전체 | 검색 미리보기 또는 접수·처리 결과 |
| `POST /api/v2/actions` | 명령별 | 변경된 상태 또는 고객 공개 결과 |

제품 분석 P1/P2의 기존 Fabric 합성 데이터와 위 로컬 문의 원장의 지표는 서로 다른 데이터다. `/api/status`의 `live_generation_configured`는 `false`이며, 문서 응답은 `RETRIEVAL_TEMPLATE`로 표시한다.

### 제품 상세의 문의·후속 연결

제품 운영 조회는 `{productId, revision, source, mappingVersion, scope, tickets, followups, counts}`를 반환한다. `tickets`에는 `id, subject, status, cycle, version, team`, `followups`에는 `id, ticketId, title, status, blocking, dueAt`만 포함한다. 문의 원문·고객 식별정보·내부 메모는 반환하지 않는다. `counts`의 키는 `tickets`, `openTickets`, `followups`, `openFollowups`다. 알려진 상품에 연결이 없으면 빈 배열과 0을 반환하고, 알 수 없는 상품은 404, 고객 역할은 403이다.

독립된 `data/operations/product-links.json`이 시나리오·합성 주문을 기존 상품 UUID에 연결한다. 고정 시나리오의 배송 안내·환불 요청·필수 후속은 합성 상품 16에 연결된다. RAG 문의는 검증된 본인 주문이 있을 때에만 주문으로 연결한다. `DEMO-ORDER-001`은 상품 16, `DEMO-ORDER-002`는 상품 11이며, 미확인 소유권·주문 없는 RAG 문의에는 연결을 추측하지 않는다.

이 응답의 `source`는 `SYNTHETIC_OPERATION_LINKS_NOT_ANALYTICS_EPISODES`, `scope`는 `LOCAL_CURRENT_ALL_DEMO_TEAMS`다. 현재 로컬 시연의 전체 팀 범위를 표시하며 제품 분석의 선택 팀·기간·295개 분석 episode와 같은 분모로 해석하지 않는다. 분석 원본과 DB 스키마를 변경하지 않는 읽기 projection이다.

## 실제 RAG 검색과 문의 접수

검색 미리보기:

```json
{
  "query": "택배가 지금 어디쯤 왔나요?",
  "orderId": "DEMO-ORDER-001",
  "createTicket": false
}
```

응답은 `{result, revision}`이다. `result`에는 분류, 허용 안내군, 검색된 문서 UUID·버전·해시·조항, 템플릿 답변, 이관 사유와 corpus 버전이 있다. `eligible: true`는 검색기가 근거 있는 안내 후보를 만들었다는 뜻이다. 최종 자동 처리 허가는 서버가 별도로 판단한다.

접수하려면 `createTicket: true`와 현재 상태 revision, 새 요청 식별자를 전달한다.

```json
{
  "query": "택배가 지금 어디쯤 왔나요?",
  "orderId": "DEMO-ORDER-001",
  "createTicket": true,
  "expectedStateRevision": 1,
  "requestId": "demo-request-0001"
}
```

검색은 쓰기 트랜잭션 전에 수행한다. 저장 직전에 자동화 버전·현재 상태 revision·합성 고객·주문 소유권·주문 버전·조회 후 60초·정책 UUID/버전/해시/유효기간·미완료 후속을 확인한다. 모두 만족하면 최종 안내 한 건을 저장한다. 확인이 부족하거나 요청 전체를 허용 안내로 설명할 수 없으면 사람 큐로 보낸다. 문서가 없거나 손상된 경우에도 근거를 만들지 않고 사람 문의로 남긴다.

직원 응답은 `{state, revision, replayed, receipt, result}`다. 고객 응답은 `{ticket, tickets, revision, replayed, receipt, notice}`이며 내부 검색 상세를 포함하지 않는다. 실제 `result`는 직원 상세의 `ticket.rag`, 사용한 문서는 `ticket.evidence.policies`에서 볼 수 있다.

## 업무 명령

```json
{
  "expectedStateRevision": 2,
  "requestId": "demo-request-0002",
  "action": {
    "type": "CLAIM",
    "ticketId": "DEMO-0005",
    "expectedVersion": 2,
    "expectedCycle": 1
  }
}
```

| 명령 | 역할 | 추가 입력 |
| --- | --- | --- |
| `CREATE_CASE` | 전체 | `scenarioId`, 선택 `body`. 고정 합성 시나리오 접수 |
| `REOPEN` | 전체, 고객은 본인 문의 | `body`. `scenarioId`를 생략하면 전체 추가 문의를 RAG로 다시 검색. 선택 `orderId` |
| `REQUEST_HUMAN` | 전체, 고객은 본인 문의 | 새 사람 처리 회차 생성 |
| `RUN_AUTO` | admin, agent | 현재 문의의 자동 처리 조건 재검사 |
| `CLAIM` | admin, agent | 사람 문의 인수 |
| `SAVE_DRAFT` | admin, agent | `text` |
| `APPROVE` | admin, agent | 현재 본문·근거·회차·후속 상태 검토 승인 |
| `SEND_HUMAN` | admin, agent | 10분 이내의 현재 HUMAN 승인 사용 |
| `ADD_FOLLOWUP` | admin, agent | `title`, `blocking`, 선택 `dueAt`, `publicNote`, `internalNote` |
| `UPDATE_FOLLOWUP` | admin, agent | `followupId`, `expectedFollowupVersion`, `status`; 취소 시 `reason` |
| `STOP_AUTOMATION` | admin | `reason` |
| `RUN_REGRESSION` | admin | 중지 상태에서 상태 엔진 회귀 검사 |
| `RESUME_AUTOMATION` | admin | 같은 중지 버전의 회귀 검사 통과 후 명시적 재개 |
| `RESET` | admin | 문의 시연 상태 초기화. 멱등 회차 묶음(epoch) 증가 |

문의 대상 명령은 `expectedVersion`과 `expectedCycle`을 함께 요구한다. 모든 변경 요청에는 `expectedStateRevision`과 8~128자의 `requestId`가 필요하다. 후속 상태는 `OPEN → IN_PROGRESS → DONE` 또는 `OPEN/IN_PROGRESS → CANCELLED`다. 종료한 후속을 다시 열지 않는다. 사람 처리로 넘어간 문의는 재문의 후에도 사람 경로를 유지한다.

## 충돌·재시도·저장 경계

같은 역할·합성 고객·API 범위에서 같은 `requestId`와 같은 업무 본문을 다시 보내면 작업을 다시 실행하지 않고 기존 receipt를 돌려준다. `replayed`가 `true`이고 `receipt.appliedRevision`이 최초 적용 revision이다. 화면 동기화를 위해 응답의 `state`와 `revision`은 현재 값을 제공한다. `expectedStateRevision`은 멱등 본문 해시에 포함하지 않는다. 같은 식별자에 다른 내용을 넣으면 409다.

409 응답 후에는 최신 상태를 확인한 뒤 사용자가 새로 실행해야 한다. 네트워크가 끊겨 결과를 모를 때에는 기존 식별자와 같은 본문으로 조회하듯 재요청한다. 자동으로 새 식별자를 만들어 중복 실행하지 않는다.

| HTTP | 대표 코드 | 의미 |
| --- | --- | --- |
| 401 | `DEMO_IDENTITY_REQUIRED` | 역할 헤더가 없거나 지원하지 않음 |
| 403 | `ROLE_NOT_ALLOWED`, `CROSS_ORIGIN_REJECTED` | 역할 또는 요청 출처 불일치 |
| 404 | `TICKET_NOT_FOUND`, `FOLLOWUP_NOT_FOUND` | 접근 가능한 대상 없음 |
| 409 | `STALE_STATE_REVISION`, `STALE_TICKET_REVISION`, `STALE_FOLLOWUP_REVISION` | 이전 상태로 실행하려 함 |
| 409 | `IDEMPOTENCY_CONFLICT`, `REQUEST_FROM_RESET_SESSION` | 요청 식별자 충돌 또는 초기화 이전 요청 |
| 409 | `INVALID_TRANSITION` | 현재 배정·승인·후속·상태 조건 미충족 |
| 413 / 415 | `BODY_TOO_LARGE` / `JSON_REQUIRED` | 최대 본문 128 KiB 또는 JSON 형식 위반 |
| 422 | 입력·개인정보·버전 필드 검증 코드 | 저장 전에 입력 거부 |
| 502 | `RAG_CONTRACT_INVALID`, `RAG_QUERY_MISMATCH` | 검색기 응답 계약 불일치 |
| 503 | `STORE_BUSY` | SQLite 저장 경합. 동일 요청으로 결과 확인 |

문자 수는 Unicode code point 기준 10,000자이며 초과분을 잘라 처리하지 않는다. SQLite `BEGIN IMMEDIATE` 트랜잭션 안에서 상태 CAS, 멱등 receipt, 최소 이벤트, 회차별 최종 답변을 함께 저장한다. 최종 답변은 `(epoch, ticket_id, cycle)` UNIQUE이고 기존 답변의 본문은 덮어쓰지 않는다. 초기화 이전 최종 이력과 최소 감사는 별도 epoch로 구분한다.

이는 단일 로컬 저장소의 저장 경계 검증이다. 팀 PostgreSQL의 worker lease·claim·재시도·분산 잠금·외부 발송 exactly-once를 구현하거나 검증한 것으로 해석하지 않는다.

## 검증

`npm run test:api`는 실제 임시 HTTP 서버와 SQLite를 사용하는 API 통합 검사 및 순수 상태 엔진 검사를 실행한다. 재시작 보존, 고객 공개 범위, 소유권, 전체 입력 길이, 멱등 재시도, 동시 revision 충돌, 검색 중 자동화 중지, 문서·주문 변경, 검토 승인, 재문의, 복합 요청의 자동 완료 차단을 확인한다. 테스트 DB는 임시 디렉터리 또는 메모리에서 생성하고 종료 시 정리한다.
