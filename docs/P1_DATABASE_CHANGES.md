# P1 DB 통합 변경

기준: Backend A 0.7.1 / 25e4aad720198ea2a3a0287ccf6f58f69c92d228.

ZIP의 revision 0007은 현재 업무량 권한 revision과 충돌하므로 P1을 **0008 (down_revision=0007)**로 이식했다. 기존 0001–0007 파일은 변경하지 않는다. readiness head는 P1 flag와 관계없이 0008이다.

- `p1_idempotency`: P0 멱등 저장소와 분리된 user/operation/key 및 응답 snapshot 기반.
- `p1_tasks`: 종류별 대상, 상태·시도·lease·완료시각 CHECK, 활성 context 부분 UNIQUE. worker/producer/API는 없다.
- `p1_ai_call_attempts`: task 또는 기존 automation job 대상 FK, attempt UNIQUE, nullable token/latency 계측 기반. writer/집계는 없다.
- `staff_permissions`: 기존 권한과 **WORKLOAD_READ**를 유지하고 P1 권한 문자열을 추가한다. 자동 부여는 없다. VOC/정책 문자열은 예약된 저장 제약이며 해당 기능 구현을 뜻하지 않는다.

P0 원장 행·업무 테이블은 변경하지 않는다. P1 테이블은 공식 22테이블 fixture에서 명시적으로 제외한다. 0008→0007 downgrade는 P1 데이터 또는 권한이 남으면 중단하며 자동 삭제하지 않는다. 빈 P1 저장소의 왕복 및 기존 P0 행·WORKLOAD_READ 보존은 신규 테스트에서 확인한다. 기존 0007의 workload 권한/감사 이력 보호도 유지한다.

VOC/정책 대상 테이블이 없는 UUID에는 후속 revision에서 FK가 필요하다. 현재는 생성·조회·worker를 노출하지 않는다. 이번 결과는 [통합 보고서](../backend/backend-a/docs/p1-integration-20261104.md)를 참조한다.
