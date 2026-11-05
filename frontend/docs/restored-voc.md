# VOC React 재구현 · 2026-11-05

환경 교체 후 기준 HEAD `55a44ec5749698ccadbd57f9bf8629ddd2f08540`에서 재구현했다. 이전32파일은 Git/stash/reflog/접근 가능한 아티팩트에 없었다. 원본과 동일한 파일 복구라고 주장하지 않는다.

`#/p1/voc`는 팀1–8개와 실제 VOC TOP10·산정 불가 API에서 확인한 상품 UUID를 선택해 생성하고 커서로 이력을 조회한다. 같은 배치로 두 상품 근거 요청을 묶으며 전체 상품 검색 API를 가정하지 않는다. `#/p1/voc/:requestId`는 상태5종, 제안, 고정 분석 기간·근거·provider·검토 이력을 표시한다.

기존 AuthManager/P1 client를 재사용한다. READ/GENERATE/REVIEW capability를 각각 확인하며 전체 요청 팀과 근거 팀을 검사한다. POST는 메모리 intent에 원래 본문과 멱등키를 보관한다. 같은 로그인에서 세션 재확인·화면 이동에도 유지하고 불확실한 결과는 같은 키로 명시 재시도한다. 중복 클릭·자동 POST 재시도는 차단한다. 로그아웃·계정/권한/팀 철회 시 제거하며 브라우저 저장소를 사용하지 않는다. 새로고침/재로그인 후에는 이력을 먼저 확인해야 한다.

검토는 revision과 최대500자 비공백 사유를 전송한다. 성공/replay/409 후 상세를 GET하고, 409를 자동 재제출하지 않는다. 201은 저장 이력 생성이며 INSUFFICIENT_DATA/FAILED도 가능하다. 실패를 Mock 성공으로 대체하지 않는다. 승인은 운영 정책·RAG·규칙·고객 발송에 영향을 주지 않는다.

위험도는 관리 우선순위다. repeat의 C/M/K·M/C는 반복 접촉 빈도가 아니며, rate의 N/S는 전역 상품 판매 코호트 내 불만 주문 비율이다. 게시 raw_rate/smoothed_rate와 구분하고 새 비율을 산정하지 않는다. 제공된 날짜만 표시하며 누락 날짜를0으로 채우지 않는다. source LOCAL_SYNTHETIC/FABRIC와 provider MOCK/AZURE_OPENAI를 구분한다. Fabric은 UNVERIFIED이고 실제 외부 연결 검증이 아니다.

검증 결과:

- React 전체 **91 passed** (기존73 + 신규18), TypeScript/Vite 빌드 성공.
- PostgreSQL VOC/provider/monitoring **60 passed**. provider 오류는 Mock 또는 Azure 전송 차단 상태다.
- P0 **37 paths / 41 operations**, handoff·기존 P1 OpenAPI 계약 유지 검사 PASS.
- 실제 로컬 Vite→FastAPI→격리 PostgreSQL: 생성201·replay200·상세/이력200·승인/반려200·409·기능 비활성503·데이터 부족·AZURE_CALLS_DISABLED 실패를 확인했다.
- 실제 Chromium 1440×1000/390×844에서 생성·근거·승인 및 별도 HTTP 클라이언트의 선행 승인 후 실제409→상세 재조회 통과. JS 예외0, 페이지 가로 넘침 없음, localStorage/sessionStorage 비어 있음.

재현: 별도 **로컬 PostgreSQL** URL을 `TEST_POSTGRES_URL`에 지정하고 기존 백엔드 개발 가상환경으로 `python frontend/scripts/local-voc-smoke.py`를 실행한다. 루프백 DB만 허용하며 새 스키마와 합성 seed를 만들고 종료 시 삭제한다. 실행 중 임시 JWT·비밀번호는 생성하여 자식 환경으로만 전달한다. `--write-fixture`는 명시적으로 합성 테스트 JSON을 갱신하는 개발 옵션이다. 일반 실행에는 사용하지 않는다. Chromium과 기존 frontend node_modules가 필요하다.

검증 fixture의 오래된 고정 날짜를 위해 로컬 ANALYTICS_STALE_HOURS=720을 사용했으며 기본/운영 설정은 변경하지 않았다. `src/test/voc-synthetic.json`은 실제 로컬 API가 반환한 합성 응답이며 인증정보나 실제 고객 자료가 아니다. `scripts/cdp.mjs`는 새 임시 프로필의 루프백 Chromium 검증 도구다.

실제 Azure 유료 호출·배포·Fabric/Search/RAG/Backend B 연결, 실고객 자료, 생성 문구의 의미적 진실성·개선 효과는 미검증이다. P0·인증·모니터링 구현, 백엔드 API·DB·마이그레이션·package/lock은 변경하지 않았다. 기존 Starlette/httpx deprecation 경고1건은 남아 있다.
