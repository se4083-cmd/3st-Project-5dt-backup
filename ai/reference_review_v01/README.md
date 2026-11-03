# 검수 지식베이스 v01 — 연결 준비 자료

현재 단계는 **자료 분리·검증 완료 / 실제 RAG 연결 전**입니다.
검색 엔진·색인·백엔드 공통 계약을 새로 구현하지 않았습니다.

## 입력과 분리 결과

- 제공 파일: `CSFlow_검수된검색용지식베이스_20261103_v01_GPT.jsonl`
  (실제 저장소의 `data/policy_review/`에 사용자가 배치한 원본을 기준으로 재확인).
- 원본 SHA256: `45fc146d6e967cf97094922fe61588a6df3b991827a37a35d823ea57bcc441ae`.
  이전에 확인한 동일 파일의 해시와 일치합니다. 원본 파일을 수정하지 않았습니다.
- 원본 76개 중 `dataset_role == official_reference`인 **73개만**
  `official_reference_20261103_v01.jsonl`에 보존했습니다.
- `DEMO_PRODUCT_001`, `DEMO_PRODUCT_002`, `DEMO_PRODUCT_003`의 **3개 시연 자료는 제외**했습니다.
  시연 항목도 원본에서 retrieval_eligible=true이므로 그 플래그만으로 필터하면 안 됩니다.
- 선택된 항목은 원본 JSON 객체와 모든 필드가 일치합니다. title/content 외에도
  conditions, exceptions, required_facts, applicability, 출처·버전·검수/승인 메타데이터를 보존합니다.
- title/content가 제공 자료의 index_fields입니다. 원문 전체와 구조화 조건을 함께 전달해야 하며,
  conditions/exceptions를 생략한 검색 결과를 바로 초안 입력으로 사용해서는 안 됩니다.
- 73개 모두 team_approval_status=pending입니다. 사용자가 제공한 공식 참고자료의 분리이지
  팀 정책 승인 완료가 아닙니다. auto_decision_allowed / auto_send_allowed /
  auto_refund_allowed=false를 그대로 유지합니다.
- 제공된 legacy_document_ids의 교체 별칭 **26개**를 manifest에 정리했습니다.
  현재 ID 자체를 가리키는 13개 항목은 교체 별칭 수에서 제외했습니다.
  실제 기존 색인/문서 저장소가 없어 교체·삭제·upsert는 수행하지 않았습니다.

이 폴더의 .gitattributes는 JSONL의 줄바꿈 변환으로 manifest의 SHA256이 달라지는 것을
방지하기 위한 해당 파일 전용 설정입니다. 다른 팀 경로의 설정에는 영향을 주지 않습니다.

## 확인한 코드와 미연결 원인

2026-11-03 원격 브랜치를 조회하고 다음 공개 커밋을 읽었습니다.

| 브랜치 | 확인 커밋 | 관련 상태 |
| --- | --- | --- |
| main / feature/backend-b | 5ddd60a | 디렉터리 README, 검색 구현 없음 |
| feature/backend-a | 447c318 | DB 문서 구조·근거 검증은 있으나 RAG 엔진 미구현 명시 |
| feature/frontend | 46f2ca6 | 프론트엔드, FAQ/RAG 검색 구현 없음 |
| openai | e06bcab | 문의 분석·점검, 반품 초안은 연결 대기 |
| feat/openai-inquiry-analysis | fab1400 | 기존 문의 분석·점검 |

A의 `backend/backend-a/app/models.py`에는 knowledge_documents 테이블이 있지만
FAQ 파일 로더나 검색기가 아닙니다. `staff_detail.py`는 저장된 근거 참조를 검증·표시합니다.
`docs/backend-b-contract.md`와 `backend-b-handoff.md`는 AI/RAG 엔진이 미연결임을 명시합니다.

따라서 기존 검색 방식, 벡터 저장소, 임베딩 모델·차원, 색인 이름을 확인할 수 없습니다.
임베딩 API 호출·색인 갱신·새 검색기 구현·다른 팀 브랜치 병합은 수행하지 않았습니다.
JSONL의 문자열 id/source_version을 A의 UUID document_id/정수 version으로 임의 변환하거나
승인·유효기간 값을 만들어 DB에 적재하지도 않았습니다.

## R10 및 AI 초안 검수

사용자가 후속 메시지로 제공한 R10의 정확한 정의를 `R10_case.json`에 기록했습니다.
이번 정책·FAQ 산출물은 Google Drive에 보관된 자료이며 GitHub 커밋 이력은 없다는
사용자 설명도 확인했습니다. R10은 프로젝트 검색 엔진의 기존 테스트가 아니라
별도의 로컬 TF-IDF 실험에서 정의한 사례입니다.

- 질문: **반품 신청 후 언제 환불되는지 진행 단계를 알고 싶어요.**
- 입력 조건: shipping_type=seller, simulation_mode=false.
- 검색 대상: dataset_role=official_reference.
- 기대 문서: `COUPANG_REFUND_64201_01` / 반품 후 환불 단계.
- 통과 기준: 실제 검색 결과 **상위 5개** 안에 기대 문서 ID가 포함됨.
- 기존 로컬 TF-IDF 실험: **보완 필요** (사용자 제공 과거 결과, 이번에 재현하지 않음).
- 프로젝트 검색: **미실행 — 연결 대상 미확인**. 순위·상위 결과·통과 여부는 null로 남겼습니다.

평가 대상은 근거 문서 검색 여부입니다. LLM 답변 품질, 환불 처리, 주문 API,
상담사 승인·발송은 평가 대상이 아닙니다. 비슷한 문의를 새로 만들거나 기존 분석 사례를
R10으로 대체하지 않았고, 임의 TF-IDF 검색기를 만들어 프로젝트 검색으로 표시하지 않았습니다.

제공 자료의 `COUPANG_REFUND_64201_01` (제목: 반품 후 환불 단계)이 분리한 자료에
그대로 포함된 것은 확인했습니다. conditions의 ‘반품 접수 후’, exceptions의
‘개별 예정일 확인 필요’, required_facts의 return_status / inspection_status /
payment_method도 보존돼 있습니다. **근거 존재 확인이며 검색 순위·R10 통과 증거가 아닙니다.**

`draft_return.py`의 대기 상태를 유지했습니다. 기존 대기 테스트 2개를 실행해 통과했고,
실제 AI 초안에서 조건·예외가 반영되는지의 E2E 검수는 미실행입니다. 실제 API 호출은 0회입니다.

`prepare_reference_corpus.py --review-case`는 이 검수 정의와 기대 문서의 제목·본문·필수
확인사항이 분리된 자료와 일치하는지만 확인합니다. 검색을 실행하거나 과거 결과를 갱신하지 않습니다.

## 검증 결과

제공 자료만 이용해 8개 검사를 통과했습니다.

1. 원본 76개와 문서 ID 고유성
2. 검색 자격을 가진 공식 참고자료 73개만 선택
3. 선택된 73개 객체의 모든 원본 필드 보존
4. 시연 3개 전부 제외
5. 원본·분리 JSONL SHA256과 manifest 일치
6. 교체 별칭 26개와 원본 메타데이터 일치
7. 환불 단계 문서와 조건 메타데이터 보존
8. 팀 승인 대기와 자동 판정·발송·환불 금지 플래그 보존

사용자가 `data/policy_review/`에 배치한 원본을 기준으로 같은 8개 검사를 다시 확인했고,
추가로 제공된 R10 정의·기대 본문·필수 확인사항의 일치도 확인했습니다.

추가 합성 문의·정책·응답 fixture는 만들지 않았습니다. 검색 품질이나 AI 답변 품질 테스트로
이 수치를 해석하면 안 됩니다. 원본의 외부 링크를 다시 검수하거나 법적 효력을 판정한 것도 아닙니다.

## 필요한 팀 입력

| 이어서 필요한 항목 | 확정 GitHub 경로/값 |
| --- | --- |
| 실제 FAQ/RAG 검색 코드 및 사용 브랜치 | |
| 검색 입력/근거 출력 및 메타데이터 전달 계약 | |
| R10 원문·기대 근거·판정 기준 | 이 폴더의 `R10_case.json` (사용자 제공 정의) |
| 기존 색인 문서 목록/교체 대상 및 색인 갱신 방법 | |
| 벡터 검색 사용 시 임베딩 모델·저장소·색인 설정 | |

이 정보가 게시되면 기존 검색기의 입력에 공식 73개만 연결하고, 구 ID 교체 및 시연 제외를
검증한 뒤 R10과 실제 AI 초안을 순서대로 검수합니다.

## 재현

실제 저장소 루트에서 아래 명령을 실행하면 같은 제공 파일을 분리합니다. 기존 출력 내용이
다르면 덮어쓰지 않고 중단합니다. 다른 파일·DB·검색 색인은 변경하지 않습니다.

```powershell
..\.venv\Scripts\python.exe ai\prepare_reference_corpus.py --source "data\policy_review\CSFlow_검수된검색용지식베이스_20261103_v01_GPT.jsonl" --output-dir ai\reference_review_v01 --review-case ai\reference_review_v01\R10_case.json
```
