# P1 foundation / monitoring API

기존 앱·DB·Bearer 인증·오류 봉투·X-Request-ID를 그대로 사용한다. 신규 경로만 `/api/v1/admin/p1`에 추가한다. `P1_ENABLED=false` 기본값, 비활성 요청은 503 P1_DISABLED. .env 또는 CSFLOW_ENV_FILE에서도 설정할 수 있다.

| Method | 경로 | 서버 권한 | 필터 |
|---|---|---|---|
| GET | /session | 활성 ADMIN + 활성 SQL 팀 grant | 없음 |
| GET | /monitoring/summary | ADMIN + P1_MONITOR_READ + 현재 허용팀 | team_ids 반복 UUID, job_kind=AUTO/HANDOFF |
| GET | /monitoring/jobs | 위와 같음 | team_ids, job_kind, status, limit=1..100(기본20), cursor |
| GET | /monitoring/ai-calls | 위와 같음 | team_ids, from/to timezone 필수·최대7일(기본 최근1일) |

중지·재개는 새 API를 만들지 않았다. 기존 `/api/v1/staff/automation-control/stop`, `/resume`와 expected_revision/stopped_revision 계약을 그대로 사용한다. 읽기는 AUTOMATION_READ, 각 버튼은 AUTOMATION_STOP/RESUME가 별도로 필요하다. P1_MONITOR_READ만으로 global 제어 상태가 노출되지 않는다.

세션 bridge는 userId/displayName/ADMIN/active/permissions/allowedTeamIds/scopeKey/capabilities를 반환한다. scopeKey는 현재 팀 집합의 digest이며 분석 manifest의 scope_key와 다르다. allowed_team_ids JSON이 아닌 `user_team_scopes JOIN teams.active`가 근거다. ADMIN에게 P1 권한을 자동 부여하지 않는다. 기존 /auth/me와 /staff/capabilities 응답 계약은 바꾸지 않았다.

summary와 jobs는 기존 SnapshotDB/SnapshotUser의 PostgreSQL REPEATABLE READ를 사용한다. 개별 응답의 as_of는 snapshot timestamp다. 두 응답은 독립 요청이므로 카드/목록 각각 조회 시각을 표시한다.

- raw_counts: 허용팀 job의 종류·원시 상태별 수, 과거 회차 포함.
- current: job cycle_no와 expected_ticket_version 모두 현재 ticket과 일치.
- eligible_pending: current PENDING이면서 next_attempt_at 도래. AUTO는 제어 상태가 존재하고 실행 허용·generation 일치여야 한다. worker의 모든 업무 조건까지 보장하는 수치는 아니다.
- active_running: current RUNNING, lease_until > as_of.
- expired_running: current RUNNING, lease_until <= as_of.
- retry_wait: current RETRY, 예정 시각 도래 여부와 관계없이 재시도 상태 수. 개별 next_attempt_at은 목록에서 확인.
- current_failed: current FAILED. 원시 FAILED는 과거 회차도 포함할 수 있다.
- superseded: 현재 회차 또는 버전 불일치.
- generation_mismatch: current AUTO의 PENDING/RUNNING/RETRY 중 현재 generation과 불일치. 제어 상태 자체가 없으면 null.

expired_running과 generation_mismatch는 겹칠 수 있어 합산하지 않는다. job·ticket·task·AI 호출 단위를 더하지 않는다. team NULL과 허용팀 밖은 기본 집계·목록에서 제외한다. 별도 미배정 건수도 노출하지 않는다. 선택팀 중 하나라도 범위 밖이면 403, 중복 UUID는 422. cursor는 접근 권한이 아니며 매번 현재 범위를 재검사한다.

JobView는 고객 원문·worker ID·lease token·주문 snapshot을 포함하지 않는다. 오류는 코드 allowlist 또는 UNKNOWN_ERROR다. `data_origin`을 표시해 원본 job의 SYNTHETIC/APPLICATION 구분을 유지한다. cursor는 updated_at/UUID 내림차순이며 페이지 간 데이터 변경은 새 snapshot을 따른다.

analytics는 기존 resolve_snapshot의 게시 포인터·정확한 팀 집합·stale 기준을 재사용한다. source_as_of/generated_at/published_at 구분, origin_verification 유지, 미게시 및 scope 미제공은 UNAVAILABLE/null. 실제 Fabric 연결 probe는 없으므로 connection_status=UNOBSERVED다.

ai-calls는 이번 단계에서 실제 집계를 제공하지 않는다. coverage=NONE, observation_started_at·attempt_count·failed_attempt_count·retry_attempt_count·error_rate·counts_by_code·STARTED/UNKNOWN 수=null. MOCK/AZURE_OPENAI도 각각 null이다. Backend B·P1 VOC·OpenAI·Search·Fabric 연결은 미관측이며 오류 0이나 정상으로 대체하지 않는다. 후속 계측 구현 때 이 계약을 버전 관리해야 한다.

p1_tasks 블록도 counts=null, coverage=NO_TASK_PRODUCER다. 생성기·worker·VOC/정책 권한별 조회가 구현되지 않은 동안 전역 task 합계를 노출하지 않는다. /tasks/{id}, VOC·정책 쓰기 API는 이번 단계에서 없다.

상세 실행 스키마는 docs/openapi.json을 참조한다. 기존 37경로·41 operation과 원본 components/security는 docs/p0-openapi.json 및 `python -m scripts.check_p0_contract`로 따로 비교한다.
