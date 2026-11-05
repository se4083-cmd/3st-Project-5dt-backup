# 정책 React 재구현 · 2026-11-05

VOC 복구 커밋 `05308494580254b4d0ec44004f8d5ddad314b583` 위에서 정책 기능을 재구현했다. 기존 VOC·P0·인증·모니터링 구현과 백엔드는 변경하지 않았다.

화면/API:

- `#/p1/policies`: 정책 key·전체 허용 팀1–8개·첫 버전 제목/본문·선택 출처 UUID 등록, limit/cursor 목록.
- `#/p1/policies/:policyId`: 새 버전 등록, 불변 버전 본문·출처, **next_before_version** 기반 내림차순 페이지, 교차 페이지 기준/대상 선택, 비교 생성과 비교 이력.
- `#/p1/policy-comparisons/:comparisonId`: 0 기반·끝 제외 `[start,end)` 줄 diff, 과거 참조와 UNCONFIRMED 영향, 검토 사유·revision·승인/반려·이력.

기존 `/api/v1/admin/p1/policies`, `/{policy_id}/versions`, `/{policy_id}/comparisons`, `/policy-comparisons/{comparison_id}`와 reviews API만 연결한다. 비교 DTO에는 팀이 없으므로 실제 부모 정책도 GET해 전체 팀 권한을 확인한다. READ/WRITE/REVIEW capability를 각각 검사하고 서버가 최종 범위를 재검사한다. P1/POLICY_DISABLED는 네트워크 오류/정상0건과 구분하며 등록을 차단한다.

입력은 실제 스키마의 영문 시작 key 최대64자, 중복 없는 허용 팀1–8개, 제목200자/본문20000자, 각각 비공백·NUL 없음·500줄 이하를 검증한다. Unicode code point와 Python splitlines 구분자를 반영한다. CRLF/CR만 LF로 바꾸고 다른 공백은 유지한다. 선택 source_document_id는 알고 있는 로컬 UUID를 입력하며 문서 검색 API를 가정하지 않는다. 실제 key·본문 일치는 서버가 확인하고 출처 연결은 버전마다 명시한다.

추가 버전은 조회한 latest_version을 expected_previous_version으로 보낸다. 버전 페이지는 응답 next_before_version을 다음 before_version으로 전달하며 끝을 제외해 중복하지 않는다. 비교는 실제 조회한 같은 정책의 from<to 버전만 선택하며 기준 없음은 대상v1만 가능하다. 과거 버전 비교는 가능하나 최신 미검토 후보만 검토 가능하다.

기존 공통 메모리 intent를 사용해 원래 본문·키를 유지한다. 불확실한 결과의 동일 요청 재시도는 같은 본문/키이며, 다른 요청은 이력을 확인한 후 명시적으로 새 키를 사용한다. 세션 재확인 후에도 원래 비교 UUID 쌍을 표시하고 유지한다. 새로고침·재로그인 후에는 이력 확인이 필요하다. 검토는 조회 revision과 비공백 최대500자 사유를 보낸다. 성공/replay/409 후 비교와 부모 정책을 GET하며409를 자동 재제출하거나 본문을 자동 병합하지 않는다.

**activation=NOT_SUPPORTED**를 모든 정책 화면에 명시한다. 승인은 P1 검토 상태만 바꾸며 운영 정책 적용·RAG 인덱스·Azure AI Search·규칙·고객 발송을 변경하는 UI/API는 추가하지 않았다.

RECORDED_LINKS는 분석 당시 허용 팀의 로컬 제안에 기록된 과거 인용/정확한 규칙 버전 동시 사용이다. 미래 사용이나 조건 의존성의 확정이 아니다. source_validation VERIFIED_SNAPSHOT도 로컬 버전/hash/본문 대조이며 외부 연결 검증이 아니다. 실제 영향 건수는 null, 향후 실행 영향은 UNCONFIRMED로 유지한다. 과거 참조0건을 실제 영향0으로 표시하지 않는다. 스캔 최대1000개·truncated를 표시하며 영역별 참조를 합산하지 않는다. FAQ 카탈로그·규칙 조건 의존성·Backend B·RAG·Search는 별도 UNCONFIRMED다.

검증 결과:

- React 전체 **112 passed** (기존73 + VOC18 + 정책21), TypeScript/Vite 빌드 성공.
- PostgreSQL `tests/p1` 전체 **97 passed**: 정책·VOC·모니터링·Mock provider·권한/범위·멱등/동시성·기존 P1 OpenAPI 보존 포함.
- P0 37 paths/41 operations·handoff 계약 검사 통과. 백엔드 소스/DB 변경 없음. 격리 DB Alembic head0010/check 성공.
- 실제 HTTP: 빈 정책 목록, 등록201·replay200·추가201·비교201·승인/반려200·오래된 head/검토409·READ-only 관리자 쓰기403·기능 비활성503.
- 실제 21개 버전을20+1로 조회했고 next_before_version=2 다음은v1이었다. INITIAL_VERSION/NO_CHANGE/METADATA_ONLY/CONTENT_CHANGED를 확인했다.
- 합성 로컬 FAQ/자동응답/규칙 참조 각1건 확인. 이 숫자는 fixture 결과이며 화면 상수가 아니다.
- Chromium 1440×1000/390×844에서 등록→버전 추가→비교→승인, 페이지를 넘긴v1/v21 비교·과거 기록 표시·실제 반려 통과. 별도 HTTP 클라이언트가 먼저 승인한 뒤 브라우저가 실제409를 받고 최신 상세/검토 이력을 조회했다. JS 예외0, 페이지 가로 넘침 없음, 브라우저 저장소 비어 있음.
- 검증 전후 로컬 knowledge_documents/automation_rules 전체 내용 해시가 같았다. 외부 인덱스 상태 검증을 뜻하지 않는다.

재현은 로컬 `TEST_POSTGRES_URL`을 설정하고 기존 백엔드 개발 가상환경으로 `python frontend/scripts/local-policy-smoke.py`를 실행한다. 루프백만 허용하며 새 스키마·합성 자료·임시 JWT/비밀번호·서버/브라우저 프로필을 만들고 종료 시 정리한다. `--write-fixture`는 명시적인 합성 테스트 JSON 갱신 옵션이다. 일반 검증에는 사용하지 않는다. `policy-synthetic.json`은 실제 로컬 API의 합성 응답이며 비밀/고객 데이터가 아니다.

실제 Azure·Fabric·RAG/Search/Backend B 연결·배포, 정책 문구의 의미적/법적 영향, 실운영 자료와 모든 브라우저/해상도는 미검증이다. 기존 Starlette/httpx deprecation 경고1건은 남아 있다. 이전 소실 구현과 바이트 동일 복구 또는 이전 테스트134개 재현을 주장하지 않으며 이번 재구현의 실제 결과를 기록했다.
