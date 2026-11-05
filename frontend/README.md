# CS Flow AI · E-commerce Manager Frontend

React + TypeScript + Vite로 만든 관리자 운영 화면입니다. 1주차 운영 홈을 기반으로 Backend A의 0.9.0 로컬 계약에 맞춘 **조회 화면**을 확장했습니다. 현재 시연은 합성 데이터입니다.

## 실행

```powershell
cd frontend
npm ci
npm run dev
npm test
npm run build
```

Node.js 22.12 이상이 필요합니다. 화면의 `개발용 상태 시연`에서 계정 범위와 응답 오류를 바꿔 볼 수 있습니다. 실제 로그인·권한 변경이 아닙니다.

## 화면

|경로|구현 범위|
|---|---|
|`/`|현재 업무·문의 미리보기·후속 업무 수·기간 KPI를 서로 다른 단위와 기준 시각으로 표시|
|`/inquiries`|Backend A 예외 큐 계약: 경로/사유 필터, 페이지 이동, 자동 처리 상태·권한 범위|
|`/inquiries/:id`|목적 지정 직원 내부 근거 조회. 초안 본문·실행 승인으로 해석하지 않음|
|`/customers/:id/360`|허용된 이력과 정형 사실. 생성형 요약으로 표시하지 않음|
|`/followups`|직원 후속 목록·상태 필터·담당 인수 필요 표시. 문의 수와 업무 수 분리|
|`/products`|게시된 VOC TOP 10·산정 불가 항목·개선 조치 목록. 같은 배치로 상세 이동|
|`/products/:id`|제품 VOC 근거·제공된 추세. 누락 날짜와 점수 null을 0으로 채우지 않음|
|`/quality`, `/quality/:id`|수동 품질 표본·지정 평가 자료 조회. 표본 평가를 전체 AI 정확도로 표시하지 않음|
|`/settings`|자동화 제어 상태 조회와 L3 조건부 자동 결정의 설계 경계|

각 화면은 로딩·0건·권한·네트워크·잘못된 응답을 구분합니다. 프로필 변경 시 이전 계정의 화면 데이터를 즉시 제거하고 진행 중인 요청을 취소합니다. 서버 응답의 권한과 범위를 프런트엔드 표시만으로 대체하지 않습니다.

## Backend A 연결 상태

현재 `VITE_DATA_MODE=mock`이 기본입니다. `http` 모드는 **동일 출처 세션/BFF**를 전제로 하고 있으며 `VITE_SESSION_PATH`와 `VITE_OVERVIEW_PATH`가 없으면 차단합니다. Backend A의 실제 API는 `/api/v1`과 Bearer JWT 방식입니다. `/auth/me`만으로는 현재 앱이 요구하는 허용 팀·scope 버전을 알 수 없습니다. 따라서 환경 변수만 바꿔 Azure API에 연결하면 로그인과 범위 검사가 완성되는 상태가 아닙니다.

조회 화면은 Backend A가 공개한 예외 큐, 직원 내부 상세, 고객 360, 후속, VOC, 개선 조치, 품질 표본, 자동화 제어 경로와 응답 필드를 기준으로 작성했습니다. [팀 인수 문서](docs/current-handoff.md)에 API별 연결 조건과 차이를 적었습니다. 실제 운영 연동에는 인증 전달 방식, 팀 범위 세션 계약, 프런트엔드 origin/CORS 또는 동일 출처 프록시가 필요합니다.

담당 인수·답변 승인/발송·후속 변경·VOC 계획 변경·품질 평가 제출·자동화 중지/재개·L3 실행은 조회 화면의 완료 범위가 아닙니다. 쓰기에는 Backend A의 revision, 멱등키, 현재 역할·팀 재검사, 충돌 시 재조회가 필요합니다. L3는 정책·검증·이의 신청 경로가 확정될 때까지 설계 범위로 표시합니다. 기본 상품 카탈로그 API가 없어 제품 목록은 VOC 분석 대상만 보여줍니다.

## 검증

`npm test`와 `npm run build`를 실행합니다. 권한 범위 변경, 데이터 제거, 계약 오류, VOC 표본 부족, 고객 360의 요약 상태 등을 테스트합니다. 합성 화면을 브라우저에서 열어 예외 큐와 메뉴 경로를 확인했습니다. Azure 실서버 인증, 실제 고객 데이터, 쓰기 명령과 모든 반응형 해상도는 아직 검증하지 않았습니다.

## JWT / P1 인증·통신 기반

`#/p1` 또는 기존 Mock 화면의 `P1 API 로그인`으로 실제 Backend A 로그인·P1 세션을 확인할 수 있습니다. JWT는 메모리에만 보관하고 P1 메뉴/직접 경로는 서버의 capability를 검사합니다. 기본 P0 합성 화면·KPI는 유지합니다. [실행·API 통신·미연결 목록](docs/p1-auth-foundation.md), [인증 기반 검증 기록](docs/p1-auth-verification.md)을 참고하세요.

`#/p1/monitoring`은 실제 monitoring summary·jobs·ai-calls 조회 화면입니다. 서버 `P1_ENABLED=true`, 활성 ADMIN의 팀 grant와 `P1_MONITOR_READ`가 필요합니다. 팀·작업 종류·목록 상태 필터와 커서 페이지 조회를 지원하며 0건·미관측·미게시·오래된 분석·조회 실패를 구분합니다. [모니터링 계약·로컬 PostgreSQL HTTP/브라우저 검증·남은 연결 범위](docs/p1-monitoring.md)를 참고하세요. 실제 Azure/Fabric 연결 완료를 뜻하지 않습니다.

`#/p1/voc`와 `#/p1/voc/:requestId`는 VOC 생성·이력·근거·검토 화면입니다. 서버 `P1_VOC_ENABLED=true`, 명시 SQL 팀 grant와 `P1_VOC_READ`, 생성/검토에는 각각 `P1_VOC_GENERATE`/`P1_VOC_REVIEW`가 필요합니다. 로컬 검증은 MOCK, Azure 전송 false로 실행합니다. [VOC 재구현·멱등 처리·검증](docs/restored-voc.md)을 참고하세요.

`#/p1/policies`, `#/p1/policies/:policyId`, `#/p1/policy-comparisons/:comparisonId`는 정책 등록·버전 추가·줄 diff·과거 연결 기록·영향 검토 화면입니다. 서버 `P1_POLICY_ENABLED=true`, 활성 ADMIN의 SQL 팀 grant와 `P1_POLICY_READ`, 등록/추가/비교에는 `P1_POLICY_WRITE`, 검토에는 `P1_POLICY_REVIEW`가 필요합니다. `activation=NOT_SUPPORTED`이며 승인은 운영 적용이 아닙니다. [정책 재구현·정확한 줄 범위·검증 기록](docs/restored-policy.md)을 참고하세요.
