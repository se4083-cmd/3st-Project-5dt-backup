# ZIP과 최신 Backend A 통합 차이

사용자 첨부 ZIP의 README·변경 47개 목록·테스트 기록과 SHA256 manifest 238항목을 확인했다. ZIP은 Backend A 0.6.1/0006 기반이며 당시 GitHub 최신 비교는 미수행으로 명시되어 있다. 첨부 문서의 브랜치 복원·프론트 실행 등은 참고 지시로만 읽고 사용자 요청 범위만 적용했다. bundle 이력은 가져오지 않았다.

실제 작업 기준은 feature/backend-plus의 25e4aad720198ea2a3a0287ccf6f58f69c92d228 (Backend A 0.7.1)이다. 전체 ZIP으로 덮어쓰지 않고 patch의 backend 신규 파일을 선별하고 공유 파일은 현재 코드에 최소 변경으로 연결했다. 최신 workload 서비스·스키마·라우터·권한과 기존 migration 0007을 보존했다. P1 revision은 0008이다.

P0 계약 baseline은 ZIP의 오래된 p0-openapi가 아니라 현재 HEAD의 OpenAPI로 고정했다. 기존 37경로·41 operation 및 모든 기존 components/security가 동일해야 한다. 새 모니터링 4개 GET만 추가한다.

P1 데이터 기반과 조회만 제공한다. VOC 생성·정책 비교/영향 분석·AI provider·task producer/worker·attempt writer·실제 Fabric probe는 포함하지 않는다. 미계측 수치는 null/UNOBSERVED이고 실제 Fabric 연결 정상으로 해석하지 않는다. 모니터링은 tickets.team_id 범위라 queue_routes 기반 큐 수치와 다를 수 있다.

프론트는 원격 feature/frontend의 frontend/를 별도 기준으로 통합해야 하며 ZIP ops-review 전체를 반입하지 않았다. ZIP 과거 테스트 결과와 이번 Linux/SQLite/PostgreSQL 실행 결과는 합산하지 않는다. 자세한 새 결과와 미완료 범위는 [통합 보고서](../backend/backend-a/docs/p1-integration-20261104.md)에 기록한다.
