# 합성 문서 예시 — 실제 데이터·자격정보 없음

**0006 당시 보관 예시·검증 기록:** db-projections에는 실제8테이블의 allowlist 컬럼만 있는 JSONL9행이 있다. 전체 INSERT/백업 데이터가 아니다. users에는 login_name/password_hash가 없고 customers에는 이름/profile/customer_key가 없으며 두 후속 메모도 제외했다. 당시 필드명·타입·FK 관계를 migration 카탈로그와 검증했다. 당시 PostgreSQL 제약 검사에서는 빠진 필수 민감 컬럼을 **메모리의 비로그인 합성값**으로 채운 뒤 rollback했다. 디스크 예시에 그 값이나 해시는 없다. 티켓 회차2/후속 원래회차1·책임회차2 사례다. 이번 audit 보완에서 이 PostgreSQL 검증을 재실행하지 않았다.

**제안 — 2026-11-04 audit 추가:** export-proposal은 기존 합성 DB projection에서 가명 변환한 **6개 파일/총6행** 예시다. 기존 products/orders/tickets/followup_actions와 customers 1행씩은 byte 그대로 유지했고 audit_events 1행을 추가했다. customers는 customer_ref FK 확인용 보조이며 공통5종에 합쳐 총6개다. Fabric 담당 첨부5개 JSONL/12,008행(감사8,820행)의 재현본이 아니다. 첨부 validation은 기존 A 4종/각1행만 검사했고 원본 Manifest는 첨부에 없다. 고객/주문/티켓/후속/이벤트 참조는 domain별 HMAC 가명이며 raw ID를 싣지 않는다. 제품·팀 UUID는 차원 키로 유지한다. Manifest의 PROPOSED_NOT_IMPLEMENTED, EXAMPLE_ONLY_NO_SNAPSHOT_WAS_EXPORTED, completeness=unknown, silver_approval=NOT_APPROVED를 확인한다. source_migration_head0006은 역사적 fixture basis이며 별도 소스 검토만0.11.0/0011이다. 실제 DB snapshot 추출·Blob 업로드·Fabric 적재는 실행하지 않았다. hmac-vector의 키는 공개 합성 bytes00..1f로 운영 재사용 금지다.

새 schema_contract.json은 **Export projection 전용 allowlist**다. 첨부 물리 합성 schema_contract와 혼동하지 않는다. audit는 event_ref/ticket_ref/cycle_no/action/result/reason_code/created_at만 허용하며 payload를 제외한다. 감사 시각은 접촉 시각이 아니다. [차이와 미확정 사항](../audit-export-review.md), [이번 파일 검증](../audit-export-verification.json)을 확인한다.

**구현 확인용 예시:** publish-request.json은 기존 docs/examples/analytics-batch.json과 같은 완전한 Submission이다. LOCAL_SYNTHETIC이며 minimal seed 전용 팀/상품 UUID를 쓴다. 원본4팀 fixture의 T1 UUID와 다르다. 여기의 독립된 Gold 지표/점수는 db-projections의 작은 원장 예시에서 계산된 값이 아니다. A가 점수를 새 계산하지 않았다. 실제 DB FK 검증에는 별도 합성 차원을 생성해 검증 후 rollback했다.

| 파일 | 의미/상태 |
|---|---|
| publish-request.json | POST /api/v1/analytics/batches의 실제 스키마에 맞는 합성 요청. 경로 이름과 달리 이것은 수신 body이며 publish 단계 body는 없음 |
| receive-response.json | HTTP200 RECEIVED 예시 |
| validate-response.json | HTTP200 VALIDATED와 validation_result.passed=true 예시 |
| publish-response.json | HTTP200 SUCCEEDED/current=true 예시 |
| failed-validation-response.json | HTTP200 FAILED와 result codes 예시. 수신 원본이 잘못된 별도 경우를 표현하며 위 정상 request가 실패했다는 뜻 아님 |
| conflict-response.json | HTTP409 오류 envelope 예시 |
| unpublished-kpi-response.json | HTTP200 UNAVAILABLE/NO_PUBLISHED_BATCH 예시 |
| service-claims.json | 서명되지 않은 claims 구조 예시. 만료된 고정시각/가상 sub이며 현재 서비스 토큰이 아님 |
| fixture-scope-map.json | 외부4팀 fixture의 정확한15조합. 배포 inventory 아님 |
| example-metadata.json | 예시와 실제 실행/계산의 구분 |

모든 응답은 타입 검증된 **문서 예시**이지 live HTTP 수신 기록이 아니다. 정상 요청 content_hash는 실제 canonical 구현으로 계산했고4테이블 rowcounts/checksums를 검사했다. 소스 JSONL의 SHA256은 최종 LF 포함 file bytes이며 Gold payload 배열 hash와 다르다. 숫자 amount는 고정소수 문자열10000.00, Export 시각은 UTC 소수6자리다. API의 Decimal canonical score는 trailing zero를 제거한 문자열이다.

```powershell
# Backend A 폴더에서; 이번 6개 Export 제안 파일만 오프라인 검증
python docs/fabric-data-contract/tools/verify_export_proposal.py --write-report
# 기존 합성 raw 예시는 그대로 두고 audit/Manifest/schema만 재생성
python docs/fabric-data-contract/tools/build_audit_proposal.py
```

두 도구는 표준 라이브러리만 쓰며 `.env`·Azure state·앱·DB·HTTP를 읽거나 호출하지 않는다. 기존 verify_samples.py 및 PostgreSQL 기록은 0006 당시 5파일 기준 전체 자료 검증용이다. 새6파일 검증 결과와 혼용하지 않는다. 이번에는 PostgreSQL 추출/검증을 실행하지 않았다. build_samples.py 전체 재생성도 마지막에 새 audit 보완기를 호출하지만 이번에는 기존 raw/API 예시를 재생성하지 않았다.
