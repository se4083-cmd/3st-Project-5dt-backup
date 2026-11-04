# v2 임시 RAG 사용·수정 안내

## 지금 동작하는 기능

v2는 별도 합성 지식 문서 10개에서 **입력한 질문을 실제로 검색**합니다. 한국어 어절과 문자 bigram으로 BM25 점수를 계산하고, 검색된 유효 조항과 현재 합성 주문 조회값을 결합해 안내를 준비합니다. 정해진 시나리오 ID로 답변을 고르는 방식이 아닙니다.

기본 생성 방식은 `RETRIEVAL_TEMPLATE`입니다. 검색한 정책의 문장과 허용된 조회 필드를 사용하며, 외부 LLM이나 임베딩 API를 호출하지 않습니다. 따라서 API 키와 사용료 없이 로컬에서 실행할 수 있습니다. UI와 결과에도 `LOCAL_BM25`, `RETRIEVAL_TEMPLATE`, `modelVersion: NONE`을 남깁니다.

이 지식 묶음은 운영 승인 정책이 아닌 **독립 개발용 `DEMO_ONLY` 문서**입니다. 기존 팀 정책의 승인 상태나 활성 상태를 변경하지 않습니다. 실제 기업 정책, 고객 정보 및 법률 원문을 복사한 데이터가 아닙니다.

## 화면에서 확인하기

고객 화면에서 합성 주문을 선택하고 질문을 입력합니다. 주문 상태와 반품·교환 절차는 본인 주문이 필요합니다. FAQ와 주문 없는 일반 문의 접수 안내에는 주문을 사용하지 않습니다.

| 입력 예시 | 준비하는 결과 |
|---|---|
| 택배가 지금 어디쯤 왔나요? | 현재 합성 주문 상태. ETA가 없으면 미정으로 안내 |
| 배송 상태가 궁금해요. | 현재 합성 주문 상태 |
| 반품 신청은 어떤 순서로 하나요? | 반품 절차. 승인·회수·환불을 실행하지 않음 |
| 교환 신청 방법을 알려 주세요. | 교환 절차. 재고·상태 판단은 사람 확인 |
| 내 문의 답변은 어디서 확인해요? | 문의 상세에서 확인하는 방법 |
| 주문 없이 문의해도 되나요? | 일반 문의 접수 정책 |
| 지금 환불 승인해 주세요. | 사람 검토. 자동 환불 승인 없음 |
| 배송 상태 알려줘. 주소도 변경해줘. | 추가 요청까지 사람 검토. 배송 질문만 답하고 종료하지 않음 |

관리자 화면의 RAG 확인에서는 검색된 제목·문서 UUID·버전·해시·조항과 점수를 볼 수 있습니다. BM25 점수는 해당 검색의 순위 점수이며 확률이나 자동 처리 허가 점수가 아닙니다.

`eligible: true`는 **근거 있는 안내 후보가 준비되었다는 뜻**입니다. 백엔드가 주문 소유권·조회 신선도·현재 회차·자동화 중지·후속·문서 버전을 다시 확인한 뒤에만 안내를 확정합니다.

## 폴더별 수정 위치

| 위치 | 역할 |
|---|---|
| `data/rag/manifest.json` | 지식 묶음 식별자, revision, 등록된 정책 파일 목록 |
| `data/rag/policies/*.json` | 문서별 내용·유형·버전·해시·활성·효력 기간·템플릿 |
| `ai/rag/index.mjs` | 백엔드가 사용하는 provider 인터페이스 |
| `ai/rag/bm25.mjs` | 실제 검색 순위 계산 |
| `ai/rag/tokenize.mjs` | 어절, 기본 조사·어미 정리, 문자 bigram |
| `ai/rag/intents.mjs` | 허용 질문군·고위험·사람 요청·예외 구분 |
| `ai/rag/scope.mjs` | 질문 전체가 허용 문형에 포함되는지 검사 |
| `ai/rag/corpus.mjs` | 문서 스키마·UUID·버전·해시·효력 및 근거 재검증 |
| `ai/rag/generator.mjs` | 검색 근거와 조회값으로 안내 구성 |
| `ai/rag/privacy.mjs` | 길이, 제어 문자, 식별 가능한 민감 입력 차단 |
| `ai/rag/maintenance.mjs` | 단일 정책의 명시적 버전·해시 갱신 |
| `ai/tests/rag.test.mjs` | 검색·근거·이관·변경·입력·수정 도구 회귀 검사 |

기존 분석용 데이터와 이 지식 묶음은 별개입니다. 정책을 수정해도 기존 제품 위험 점수나 Fabric 분석 배치를 재계산하지 않습니다.

## 정책 문서 계약

각 JSON은 다음 필드를 갖습니다.

| 필드 | 의미 |
|---|---|
| `document_id` | 독립 UUID. 기존 문서 내용 수정 시 유지 |
| `policy_key` | 사람이 확인하기 쉬운 고정 식별자 |
| `version` | 양의 정수. 문서 변경 시 증가 |
| `body` | 실제 검색·안내에 사용하는 조항 |
| `content_hash` | UTF-8 본문의 SHA-256 |
| `clause_id` | 조항 식별자 |
| `allowed_topics` | 정규 분류 1개. 예: `DELIVERY` |
| `allowed_intents` | 이 문서가 지원하는 등록 질문군 |
| `allow_kind` | L2 안내군 또는 `null` |
| `template_key` | 등록된 안내 형식 |
| `order_required` | 주문 검증 필요 여부 |
| `active` | 개발 지식 묶음 안에서 사용 여부 |
| `approval_status` | `DEMO_ONLY`여야 시연 검색에 사용 |
| `effective_from`, `effective_to` | UTC 효력 시작과 종료. 종료 시각은 제외 |
| `scope`, `source` | `DEMO_ONLY`, `V2_ISOLATED_SYNTHETIC_POLICY` |

문서 본문, 분류, 허용 질문군 또는 메타정보가 바뀌면 지식 묶음의 `corpusVersion`도 달라집니다. `content_hash`는 본문을 확인하고, `corpusVersion`은 문서 구성과 메타정보까지 묶어서 확인합니다.

중복 UUID·정책 키·조항, 잘못된 스키마, 누락 파일, 해시 불일치가 발견되면 해당 지식 묶음의 사용을 중단합니다. 비활성·미승인·만료·미래 효력 문서는 검색 대상에서 제외합니다. 같은 질문군에 서로 다른 유효 정책이 두 개 있으면 점수가 높은 하나를 임의로 선택하지 않고 이관합니다.

## 문서 수정 절차

본문이나 설정은 해당 JSON 파일에서 고칩니다. 그런 다음 수정한 파일 하나를 지정합니다.

```bash
npm run rag:rehash -- policies/return-steps.json
npm run rag:check
npm run test:rag
```

`rag:rehash`는 지정한 한 문서의 본문 해시를 계산하고 문서 `version`과 manifest `revision`을 각각 1 증가시킵니다. `active`와 `approval_status`는 그대로 유지합니다. 먼저 임시 복사에서 전체 문서를 검증하고 실패하면 원본을 쓰지 않습니다. 저장 중 오류가 발생하면 두 파일을 되돌립니다. 검증 중 다른 수정이 발견되어도 덮어쓰지 않습니다.

`rag:check`는 현재 문서 수·활성 문서 수·버전·해시를 확인합니다. 이 명령의 성공은 운영 정책에 대한 팀 승인이나 내용의 법적 검토를 뜻하지 않습니다.

새 질문군을 추가하려면 문서만 추가해서는 안 됩니다. `intents.mjs`의 질문군, `scope.mjs`의 전체 입력 범위, `generator.mjs`의 등록 템플릿, 관련 회귀 검사까지 함께 수정해야 합니다. 지원하지 않는 추가 요청이 섞였을 때도 자동 완료되지 않는지 확인합니다.

로컬 파일 편집과 SQLite 확정은 하나의 분산 트랜잭션이 아닙니다. 문서 편집 작업 중의 서비스 운영을 조정하고, 정식 서비스에서는 정책 버전을 DB 또는 검증 가능한 정책 저장소에서 원자적으로 확인해야 합니다.

## 입력 처리와 자동 안내 범위

입력은 유니코드 문자 기준 1~10,000자입니다. 검색과 위험 검사는 전체 입력을 사용합니다. 앞 4,000자만 자르거나 뒤에 있는 환불·사람 요청을 버리지 않습니다. 10,000자를 넘으면 명시적으로 거절합니다.

현재 분류기는 등록된 질문군을 처리하는 보수적인 로컬 규칙입니다. 범용 자연어 분류 모델이 아닙니다. 배송 관련 단어가 있다는 이유만으로 안내를 완료하지 않습니다. 하나의 질문군을 찾은 뒤에도 전체 어절이 그 안내군의 허용 어휘와 문형으로 설명되는지 확인합니다. 주소 변경, 쿠폰 발급, 날씨처럼 미지원 내용이 남으면 질문 전체를 사람 검토로 보냅니다. 이 때문에 뜻이 안전해 보이는 새로운 표현도 자동 안내 대상에서 제외될 수 있습니다.

계정 권리 변경, 환불 승인, 보상 결정, 일정 보장, 개봉·기한 예외, 분쟁, 사람 상담 요청, 프롬프트 지시 변경은 자동 완료 대상이 아닙니다. 이관용 정책이 검색되더라도 자동 승인 결과나 실제 실행을 만들지 않습니다.

배송 문구에는 허용된 `status` enum의 표시값과 유효한 날짜 형식의 `eta`만 들어갑니다. 임의 `statusLabel`이나 고객의 문장을 배송 상태로 사용하지 않습니다. ETA가 `null`이면 미정으로 안내합니다. 문서에 없는 금액·도착 보장·계정 조치를 보충하지 않습니다.

## 코드 인터페이스

```js
import { createRagProvider } from './ai/rag/index.mjs';

const rag = createRagProvider();
const result = rag.ask({
  query: '배송 상태가 궁금해요.',
  order: { status: 'IN_TRANSIT', eta: null, version: 1 },
  now: Date.now(),
});

// 저장 직전, 현재 문서와 비교한다.
const validation = rag.validateEvidence(result.evidence, {
  now: Date.now(),
  expectedCorpusVersion: result.corpusVersion,
});
```

| 메서드 | 반환 |
|---|---|
| `search(query, {category?, limit?, now?})` | 순위별 `hits`, 지식 버전, 검색 모드, 질문 길이·해시 |
| `answer(query, context)` | 근거 있는 안내 후보 또는 이관 사유 |
| `ask({query, category?, order?, now?})` | `answer`와 같은 결과 |
| `knowledge({now?})` | 문서 목록, 지식 버전, 모드, 예시 질문 |
| `validateEvidence(evidence, {now?, expectedCorpusVersion?})` | 현재 근거의 `valid`, 실패 사유, 현재 지식 버전 |

`createRagProvider({corpusDir, now})`로 테스트 문서 묶음과 고정 시각을 주입할 수 있습니다. 기본 함수 `askRag`, `search`, `answer`, `knowledge`, `validateEvidence`도 같은 entry에서 export합니다. 현재 구현은 모두 동기 함수입니다.

핵심 응답 계약:

```text
schemaVersion = csflow.rag.result.v1
category = DELIVERY | RETURN | REFUND | PRODUCT | PAYMENT | ACCOUNT | UNKNOWN
intent = 등록 질문군 | null
allowKind = ORDER_STATUS | GENERAL_FAQ | RETURN_PROCEDURE | POLICY_GUIDANCE | null
eligible = 근거·형식이 맞는 안내 후보 준비 여부
reply = 안내 문장 | null
reasons = [{ code, detail }]
evidence = [{ documentId, version, contentHash, clauseId, title, text,
              active, source, scope, templateKey, score, ... }]
mode = RETRIEVAL_TEMPLATE
modelVersion = NONE
corpusVersion = 현재 지식 묶음 버전
retrieval = { mode: LOCAL_BM25, hits, queryLength, queryHash, ... }
```

분류의 기준 이름은 `DELIVERY`입니다. 기존 화면의 `SHIPPING`은 `DELIVERY`로 변환하고 `UNCLASSIFIED`는 `UNKNOWN`으로 변환합니다. 외부에서 제공한 분류와 현재 질문군이 다르면 이관합니다.

입력이 유효한데 지식 파일을 읽거나 검증할 수 없으면 `corpusVersion: UNAVAILABLE`, `eligible: false`, 빈 근거와 입력 해시를 돌려줍니다. 백엔드는 문의를 사람 큐에 남길 수 있습니다. 입력 자체가 잘못되었거나 민감정보가 검출되면 입력 해시를 만들지 않으며 API가 422로 거절합니다.

## API와 백엔드의 책임

현재 로컬 API:

- `POST /api/v2/rag/ask`: 검색 시연 또는 `createTicket: true`로 문의 접수·처리.
- `GET /api/v2/rag/documents`: 관리자·상담사의 문서와 모드 확인.
- `GET /api/v2/orders`: 현재 합성 고객이 선택할 수 있는 주문.

API가 서버에서 확인한 주문만 provider에 전달합니다. 고객이 준 `eligible`, `evidence` 또는 승인 결과를 신뢰하지 않습니다. 검색 결과를 저장하기 전에 현재 정책, 주문 버전·신선도, 회차·버전, 자동화 중지 상태, 후속 작업을 재검증합니다. `eligible`을 팀 API의 최종 `allowed`나 `SYSTEM` 승인으로 직접 변환하면 안 됩니다.

정식 RAG로 바꿀 때는 `createRagProvider`의 경계와 evidence 계약을 유지하면 화면과 저장 검증을 재사용할 수 있습니다. 외부 검색·OpenAI 호출은 저장 잠금 이전의 준비 단계에서 수행하고, 마지막 정책 유효성 확인은 운영 저장소의 현재 버전을 기준으로 처리해야 합니다. 현재 동기 `validateEvidence` 자리에 원격 Promise를 그대로 넣으면 안 됩니다. 정책 캐시의 버전과 철회 상태를 안전하게 검증하는 운영 adapter가 필요합니다.

현재 코드에는 확인되지 않은 팀 검색 URL, 가짜 원격 성공 결과, 실패를 숨기는 자동 로컬 대체가 없습니다. 외부 provider를 추가하면 모드를 명시하고 실패를 이관 사유로 반환해야 합니다.

## 정보 저장과 검증 범위

RAG 모듈은 문의 원문을 파일·로그·지식 색인에 기록하지 않습니다. 본문을 포함한 실제 고객 자료를 개발 데이터로 사용하지 마세요. 이메일·전화번호·식별번호·카드번호·주소·인증정보처럼 식별 가능한 입력은 검색 전에 차단합니다. 이 검사는 모든 개인정보를 알아내는 보증이 아니므로 합성 문장만 사용해야 합니다. 운영 API의 개발 원장에는 승인된 합성 문의가 저장됩니다.

회귀 검사는 실제 검색 결과, 문장 변형, 미지원 복합 요청, 고위험 이관, 입력 10,000자, 정책 비활성·만료·미승인, 해시·UUID 충돌, 문서 변경 이후의 오래된 근거 거절, 본문을 넘어선 약속 차단, 단일 문서 갱신 실패 시 복구를 확인합니다.

이 검증은 작은 개발용 corpus의 기능 회귀 검사입니다. 팀의 전체 KB 검색 성능, 정식 R10 평가, 실제 OpenAI 생성 품질, 운영 환경의 보안·부하·동시성 평가를 완료한 것으로 보고하지 않습니다.
