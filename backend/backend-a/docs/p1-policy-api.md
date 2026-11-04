# P1 정책 버전·변경 비교·영향 검토 API / React 계약

기준 커밋 `0f0e0d46377b8de805aab932614d39131738deed`. P1 검토용 저장소이며 실제 정책 활성화·발송·규칙 적용 API가 아니다. 외부 Azure/AI/Search 호출은 없다.

## 기존 자료와 확인 범위

- knowledge_documents: policy_key/version UNIQUE, body/content_hash, allowed_topics, active/approval/effective 상태를 가진 로컬 지식 문서. P1이 이 행을 수정하지 않는다.
- ai_suggestions.evidence_refs: document_id/version/content_hash를 가진 인용 배열. 기존 staff_detail.evidence 검증을 재사용한다. suggestion→automation_rules.rule_id FK와 기록된 rule_version은 과거 동시 사용 근거다.
- automation_rules.conditions는 임의 JSON이며 policy dependency 계약이 없다. 문자열 유사성/정책 키 포함만으로 직접 의존 관계를 만들어내지 않는다.
- 독립 FAQ 원장·FAQ→정책 매핑, 실제 Backend B 런타임/FAQ 갱신/RAG index/Azure AI Search 활성화 계약은 확인되지 않았다. FAQ 분류의 검증된 과거 인용은 보고하지만 FAQ 카탈로그 전체 영향이라고 주장하지 않는다.

## 설정/실행

Backend A 디렉터리의 기존 고정 requirements-dev.txt와 Python 환경을 그대로 사용한다. 별도 빈 로컬 PostgreSQL과 ignored 환경파일을 준비한다. `python -m alembic upgrade head`, `python -m alembic check`를 실행한다. 단일 head는 **0010**, down_revision은 0009다. 기존 0001–0009는 그대로다. flag가 꺼져도 readiness는 0010을 요구한다.

`P1_ENABLED=true`, `P1_POLICY_ENABLED=true`로 명시 활성화한 뒤 기존 `python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`로 시작한다. 기본 P1_POLICY_ENABLED는 false다. 키나 외부 연결 정보는 필요 없다. `P1_POLICY_READ`, `P1_POLICY_WRITE`, `P1_POLICY_REVIEW`는 기존 P1 예약 권한이며 자동 grant는 없다. 활성 ADMIN과 현재 활성 SQL 팀 grant가 필요하다.

## 경로/권한

기본 prefix `/api/v1/admin/p1`. 모든 응답은 기존 Bearer·오류 봉투·request_id/no-store를 사용한다. 모든 쓰기에 Idempotency-Key(8–128, 영문/숫자/._:-)가 필요하다. 최초 생성201, 같은 key/body replay200, 검토는200이다. replay는 당시 응답 snapshot이며 최신 상태는 GET으로 확인한다.

| 경로 | 메서드 | 권한 | 입력/결과 |
|---|---|---|---|
| /policies | POST | P1_POLICY_WRITE | 정책 key/팀 집합/첫 버전 등록 → PolicyView |
| /policies | GET | P1_POLICY_READ | limit/cursor → PolicyPage |
| /policies/{policy_id} | GET | P1_POLICY_READ | PolicyView; 최근100버전과 versions_truncated |
| /policies/{policy_id}/versions | POST | P1_POLICY_WRITE | expected_previous_version + 본문/제목 → PolicyVersion |
| /policies/{policy_id}/versions | GET | P1_POLICY_READ | limit/before_version → VersionPage |
| /policies/{policy_id}/versions/{version_id} | GET | P1_POLICY_READ | 불변 버전 본문 및 source_snapshot |
| /policies/{policy_id}/comparisons | POST | P1_POLICY_WRITE | from_version_id, to_version_id → ComparisonView |
| /policies/{policy_id}/comparisons | GET | P1_POLICY_READ | limit/cursor → ComparisonPage |
| /policy-comparisons/{comparison_id} | GET | P1_POLICY_READ | diff/impact/검토 이력/현재 candidate_status |
| /policy-comparisons/{comparison_id}/reviews | POST | P1_POLICY_REVIEW | expected_revision, APPROVED/REJECTED, 비공백 reason → ComparisonView |

팀 집합은 정책 생성 때 고정한다. **모든 등록 팀**이 현재 허용되어야 읽기/추가/비교/검토/replay가 가능하다. 일부 팀만 남아도 해당 정책은 목록에서 제외되고 상세/변경은404다. 권한 자체가 없으면403. 동일 policy_key라도 팀 집합이 다르면 별도 정책이다. 같은 팀 집합+key 중복은409다.

## 요청 예시

UUID는 실제 허용된 팀/리소스 UUID로 바꾼다.

```json
{"policy_key":"DELIVERY_GUIDE","team_ids":["00000000-0000-0000-0000-000000000001"],"title":"배송 안내","body":"배송 안내\n기존 절차\n","source_document_id":null}
```

기존 지식 문서와 연결하려면 source_document_id를 명시하고 body와 policy_key가 해당 로컬 문서와 정확히 일치해야 한다. 줄바꿈 CRLF/CR은 LF로 정규화하며 추가 공백은 유지한다. 문서 version/선언 hash/계산 body hash를 고정한다. 이것은 로컬 기록 대조이며 외부 RAG 검증이 아니다. source의 blob_path, 원시 title/source URL, 고객 원문을 자동 반입하지 않는다.

```json
{"expected_previous_version":1,"title":"배송 안내","body":"배송 안내\n변경 절차\n","source_document_id":null}
```

버전은 append-only며 title/body는 나중에 수정하지 않는다. body는 비공백·NUL 없음·최대20000자/500줄, title은 비공백·최대200자다. `expected_previous_version`이 현재 최신과 다르면409. 부모를 덮어쓰거나 자동 병합하지 않는다. source 연결은 **버전마다 명시**하며 후보 버전이 과거 RAG에서 사용됐다고 추정해 상속하지 않는다.

```json
{"from_version_id":"00000000-0000-0000-0000-000000000002","to_version_id":"00000000-0000-0000-0000-000000000003"}
```

두 버전은 같은 정책이어야 하며 from.version_no < to.version_no다. 첫 버전의 최초 등록 비교만 from=null을 허용한다. 그 외 누락/동일/역방향은422, 다른 정책의 ID는404다. 승인한 과거 버전끼리도 읽기 비교할 수 있지만 최신 미검토 후보만 승인/반려할 수 있다.

```json
{"expected_revision":1,"decision":"APPROVED","reason":"기록된 근거와 미확인 범위를 확인했으며 후보로 승인"}
```

검토는 비교 상태와 revision을 확인하고 대상 버전당 한 번만 확정한다. 다른 비교에서 이미 검토한 버전이나 최신에서 밀린 후보는409다. 같은 멱등 키/body 검토 replay는 허용한다. 승인은 P1 비교/버전 상태와 이력만 갱신하며 **서비스 활성화가 아니다**. `activate` 같은 추가 입력은422다. 삭제·버전 덮어쓰기·자동 source 갱신·외부 인덱싱 API는 없다.

## 응답 타입/상태 (React)

모든 타입은 OpenAPI의 extra-forbid 스키마로 닫혀 있다. 최신 `docs/openapi.json`을 기준으로 생성할 수 있다.

- PolicyView: policy_id, policy_key, scope_hash, latest_version, team_ids, created_by/at, versions[PolicyVersion], versions_truncated, activation=NOT_SUPPORTED. 목록 items도 이 형태다. 상세의100개 제한 이후는 versions endpoint로 페이지 조회한다.
- PolicyVersion: version_id/policy_id/version_no/title/body/content_hash, source_document_id|null, source_snapshot{}, status, revision, created_by/at. source_snapshot은 빈 객체 또는 로컬 문서 version/hash/body_hash/key/origin과 verification이다.
- VersionPage: items[], next_before_version:int|null. 내림차순이며 다음 요청 before_version은 마지막으로 받은 version_no다.
- PolicyPage/ComparisonPage: items[], next_cursor:string|null. 생성시각/UUID 내림차순. cursor는 권한 토큰이 아니며 매번 현재 범위를 검사한다.
- ComparisonView: comparison_id/policy_id/from_version_id|null/to_version_id, diff, impact, analysis_hash, status, revision, reviews[], candidate_status, reviewable, activation=NOT_SUPPORTED.
- PolicyReviewView: review_id/comparison_id/version_id/reviewed_by/decision/reason/created_at. 비교 결과와 검토 이유는 원문 로그에 복사하지 않는다.

| 상태/신호 | UI 의미 |
|---|---|
| PENDING_REVIEW + reviewable=true | 최신 미검토 후보; 현재 REVIEW capability가 있을 때만 검토 버튼 |
| PENDING_REVIEW + reviewable=false | 이미 다른 비교에서 검토됐거나 최신 버전에서 밀린 후보; GET 새로고침/최신 버전 비교 |
| APPROVED / REJECTED | 사람의 최종 후보 검토 기록; 게시/운영 활성화 배지와 구분 |
| activation=NOT_SUPPORTED | 모든 상태에서 고정; 운영 반영 버튼을 만들지 않음 |
| source_validation=UNCONFIRMED | 확인된 로컬 baseline source 없음 또는 drift. 빈 links를 영향0으로 표시하지 않음 |
| domain.status=RECORDED_LINKS | 허용팀의 과거 기록상 연결 확인. 실제 의미적 영향/미래 사용은 미확인 |
| domain.status=UNCONFIRMED | 확인된 연결 없음. 미확인으로 표시하며 정상/무영향으로 대체하지 않음 |

`diff.kind`: INITIAL_VERSION / NO_CHANGE / METADATA_ONLY / CONTENT_CHANGED. title_before/after, from_hash/to_hash, body_changed와 changes[]를 반환한다. changes의 operation은 replace/delete/insert이고 old_start/end 및 new_start/end는 **0 기반, 끝 제외** 줄 범위다. before/after는 개행을 보존한 줄 배열이다. hash는 서버 canonical digest(title/body)다. 줄바꿈 정규화 후 같은 텍스트면 NO_CHANGE다. 문구 차이가 자동으로 법적/의미적 영향 판정이 되는 것은 아니다.

impact는 as_of, coverage=SCOPED_LOCAL_RECORDED_SUGGESTIONS, source_validation/reason, scanned_count, truncated, faq/auto_replies/automation_rules의 ImpactDomain을 포함한다. 각 domain은 status/reason, observed_reference_count와 links를 제공하며 actual_affected_count=null, runtime_effect=UNCONFIRMED다. link의 suggestion/document ID·version·현재 source active·출처, 규칙 co-use의 rule ID/version/origin/active만 허용한다. raw draft/prompt/order/customer/body/conditions/blob_path는 포함하지 않는다.

source의 로컬 version/선언 hash/실제 body가 캡처와 일치할 때만 기존 evidence validator를 적용한다. 허용팀 tickets에 속한 suggestions를 최대1000개 스캔하고 초과하면 truncated=true다. 0은 이 스캔에서의 확인된 참조 수이지 실제 영향0이 아니다. FAQ는 category=FAQ인 과거 인용일 뿐 FAQ 카탈로그 전체가 아니다. 규칙은 suggestion FK와 정확한 rule_version의 **동시 사용**이며 conditions가 정책에 직접 의존함을 증명하지 않는다.

faq_catalog, rule_condition_dependency, backend_b_runtime, rag_index, azure_ai_search는 항상 UNCONFIRMED다. source/suggestion/rule의 SYNTHETIC/APPLICATION 출처를 구분한다. 새 비교를 만들어야 변경된 참조를 다시 스캔하며 기존 diff/impact/analysis_hash는 고정된다. 분석/승인 시점 이후 실제 서비스 상태를 보장하지 않는다.

## 오류/동시성/React 동작

401 인증/비활성 계정, 403 ADMIN·capability·팀 거부, 404 없는/접근 불가 리소스, 409 키/버전/source/검토 충돌, 422 형식·추가 입력·버전쌍·길이 오류, 503 POLICY_DISABLED/P1_DISABLED/POLICY_CONFIGURATION_INVALID 및 DB 오류는 기존 오류 봉투로 반환한다. 409에서 클라이언트가 임의로 expected 값을 바꿔 자동 재시도하지 말고 최신 상태와 사용자 의도를 다시 확인한다.

Idempotency-Key는 user/operation/key로 분리하고 register/append는 POLICY_REGISTER, compare는 POLICY_COMPARE, review는 POLICY_REVIEW를 사용한다. payload에 action/대상 ID를 포함해 다른 경로로 key를 재사용하면409다. PostgreSQL actor→policy 잠금 및 대상 비교/버전 조건부 UPDATE, UNIQUE 제약으로 중복 append/검토를 방지한다. 비교에 사용하는 source에는 공유 잠금을 사용해 분석 중 source drift를 방지한다. 기존 worker/ticket 잠금이나 전역 제어를 변경하지 않는다.

React는 기존 로그인과 P1 /session의 **capabilities**에 있는 P1_POLICY_READ/WRITE/REVIEW를 사용한다. 기존 permissions 배열은 레거시 UI 표기라 새 권한이 모두 들어있다고 가정하지 않는다. 토큰·계정·팀 변경 시 이전 응답/요청을 취소하고 데이터 캐시를 비운다. 읽기/편집/검토 권한을 별도로 표시한다. body/diff/review reason은 일반 텍스트로 렌더링하며 HTML로 실행하지 않는다. 검토 버튼은 capability + reviewable를 확인하고 expected_revision을 보낸다. 생성 이후는 GET으로 최신 버전/상태를 가져온다. 미확인/스캔 제한/합성 출처를 숨기지 않는다.

프론트 실제 구현, Backend B/Search/RAG mapping 수집·활성화, 정책의 의미적/법적 해석·부하 시험·운영 배포는 이번 범위가 아니다. 이 API는 연결 확인과 검토 자료를 제공할 뿐 자동 영향 적용 엔진이 아니다.
