# P1 팀 연동 및 남은 작업

Backend A는 ADMIN + P1_MONITOR_READ + 활성 SQL 팀 범위로 읽기 API를 제공한다. P1_ENABLED 기본값은 false이며 자동 권한 부여가 없다. 기존 AUTH와 SnapshotDB/SnapshotUser를 사용한다. 중지/재개는 기존 API와 별도 AUTOMATION_READ/STOP/RESUME 권한·revision/generation 계약을 재사용한다.

프론트는 feature/frontend의 frontend/를 기준으로 ZIP의 features/p1·Bearer transport·세션 bridge를 개별 이식하고 기존 Mock 흐름과 API 클라이언트를 유지해야 한다. 토큰은 메모리에 보관하고 401/로그아웃 시 제거한다. 화면 버튼은 capabilities의 개별 STOP/RESUME 권한을 확인한다. 팀/계정 변경 시 이전 응답 폐기와 AbortSignal, 비활성 탭 polling 중단, request_id, 15초 polling/수동 갱신을 검증한다. 세부 계획은 [통합 보고서](../backend/backend-a/docs/p1-integration-20261104.md)를 따른다.

Backend B 계측 writer와 실제 provider 호출은 후속 별도 작업이다. 현재 ai-calls는 null/미관측이며 p1_tasks도 producer 없음으로 표시한다. 동기 VOC 개선 제안 API는 [VOC API](../backend/backend-a/docs/p1-voc-api.md)에 구현했다. 정책 변경 영향 분석·background worker/lease 실행은 구현하지 않는다. 향후 비동기 worker 작업에서는 기존 task target FK와 실행 엔진을 별도로 이관·설계해야 한다. Azure 리소스/배포·원격 push는 이번 범위 밖이다.
