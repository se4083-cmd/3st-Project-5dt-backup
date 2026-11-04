# Backend A 0.6.1 로컬 검증 기준

이 문서는 0.6.1/migration0006 단계의 보관 기록입니다. 현재 구현·배포 상태는 [Backend A 연동 현황](backend-a-handoff.md)과 [Frontend 연동 안내](frontend-handoff.md)를 기준으로 확인합니다.

0.6.1은 보관·삭제 dry-run까지의 A 로컬 P0 경계를 구현했습니다. 독립 검토 결함 수정 이후 PostgreSQL368개와 실제 HTTP33개 흐름이 통과했습니다. 별도 부분PG38개·SQLite37개/1skip과 합산하지 않습니다. [독립 검토 수정](review-fixes.md), [검증 기록](verification.md)에 해당 실행 범위가 있습니다.

## 보존할 계약과 한계

- 실제 삭제·외부 저장소/백업 검사·법적 준수·B/AI/RAG/Fabric/Frontend/발송 통합은 이 기록의 완료 범위가 아닙니다.
- DEV_RETENTION_V1은 개발 제안이며 기간상 후보/업무 보호/설계 변경/판단 불가/미검사를 구분합니다. 보관 보고서는 삭제 승인이나 예약이 아닙니다.
- 기존0001–0005 migration 보존과0006 readiness는 이 단계 당시 기준입니다. 이후 migration 적용 상태를 대신하지 않습니다.
- 명시 capability, 큐/상세/고객360 범위 분리, JSON allowlist, 회차·version·lease·generation fence를 유지합니다.
- 이 단계의 검증은 격리 로컬 Python/PostgreSQL·127.0.0.1에 한정됐으며 실제 클라우드·외부 모델·Fabric·발송 연결 검증은 포함하지 않았습니다.
