# 프런트엔드 · CS Flow AI v2

React와 Vite로 실행하는 관리자·고객 화면입니다. 프로젝트 최상위 폴더에서 `npm install` 후 `npm run dev`로 실행합니다. 화면 코드는 API가 반환한 상태를 표시하며, 문의 처리와 저장은 `backend/`가 담당합니다.

## 수정할 위치

| 파일 | 담당 내용 |
| --- | --- |
| `src/main.tsx` | React 시작점과 공통 스타일 |
| `src/components/insight-dashboard.tsx` | 관리자 틀, 메뉴, 제품 VOC·P1·P2 화면 |
| `src/components/operations-workspace.tsx` | 운영 홈, 문의, 초안·승인·답변, 후속, 운영 설정, 고객 대화 |
| `src/components/operations-context.tsx` | 서버 상태 조회, 비동기 작업, 버전 충돌과 요청 재확인 |
| `src/components/rag-workspace.tsx` | 고객 자유 문의, 운영자 RAG 검색 확인, 문서 근거 표시 |
| `src/components/product-operations.tsx` | 제품에 연결된 현재 문의·후속 조회와 업무 이동 |
| `src/lib/api/client.ts` | API 주소·호출·오류 처리·로컬 시연 역할 |
| `src/lib/analytics/` | 기존 제품 분석과 P1·P2 계산 |
| `src/lib/prepared-suggestions.mjs` | P1 사전 작성 제안의 근거 해시 검증 |
| `src/styles/base.css` | 기존 보라색 관리자 화면의 공통 디자인 |
| `src/components/*-workspace.css` | 운영·RAG 화면 디자인 |

## 실제 연결된 흐름

- 관리자 상태: `GET /api/v2/state`
- 관리자 작업: `POST /api/v2/actions`
- 고객 공개 목록·상세: `GET /api/v2/customer`, `GET /api/v2/customer/{id}`
- 고객 주문 선택: `GET /api/v2/orders`
- 새 자유 문의: `POST /api/v2/rag/ask`의 `createTicket: true`
- 운영자 검색 미리보기: 같은 경로의 `createTicket: false`
- 개발용 정책 목록: `GET /api/v2/rag/documents`
- 제품별 현재 문의·후속: `GET /api/v2/products/{id}/operations`

문의 작업에는 서버 상태 버전과 요청 ID를 보냅니다. 버전 충돌이 발생하면 최신 상태를 표시하고 다시 확인하도록 합니다. 연결 중 결과를 확인하지 못하면 새 요청을 막고 같은 요청 ID로 결과를 재확인합니다. API 연결 실패를 브라우저의 가짜 성공 결과로 대체하지 않습니다.

고객 화면은 서버의 공개용 응답만 표시합니다. 상담 초안·승인·내부 메모·RAG 내부 근거는 고객 공개 응답에 포함되지 않습니다. 화면 전환은 로컬 시연 역할 전환이며 운영 서비스의 로그인 체계는 아닙니다.

## 팀 API를 붙일 때

먼저 `src/lib/api/client.ts`에 인증 방식과 API 경로·응답 변환을 적용합니다. 기본 API 주소는 현재 화면과 같은 서버입니다. 별도 서버를 사용하려면 `VITE_API_BASE_URL`과 해당 서버의 인증·CORS 설정을 함께 준비해야 합니다. 로컬 서버는 기본적으로 같은 출처의 변경 요청만 허용합니다.

현재 역할 헤더는 합성 데이터 시연 전용입니다. 운영 연결에서는 로그인 세션과 객체 권한을 사용해야 합니다. 응답을 서버 상태·고객 공개 정보·RAG 결과 계약으로 변환하면 화면 대부분을 유지할 수 있습니다.

## 제품 분석

기존 합성 제품의 점수·순위와 P1·P2 분석을 유지합니다. 데이터는 최상위 `data/analytics/`에 있습니다. P1 사전 작성 결과는 제품·팀 범위·배치·근거 해시가 일치할 때만 표시합니다. 운영 문의 시연을 추가해도 분석 배치의 수치를 즉시 다시 계산하지 않습니다.

제품 상세의 현재 문의·후속은 별도 합성 연결을 이용해 API로 조회합니다. 전체 시연 팀의 현재 업무이며 선택한 팀 범위의 7일 분석 집계와 합산하지 않습니다. 조회 중·실패·확인된 빈 목록을 구분하고, 실패를 0건으로 표시하지 않습니다. 관련 문의는 완료 여부와 관계없이 정확한 문의를 열고, 후속은 해당 문의와 후속 ID로 범위를 좁혀 수정 화면으로 이동합니다.
