# audit_events Export 제안 자료

**합성 샘플·제안 계약입니다. 실제 DB Export·Silver 승인 자료가 아닙니다.**

현재 전달 ZIP은 저장소의 역할 중심 문서로 갱신했습니다. 교체 전 원본은 팀 체크아웃 밖에 별도로 백업했으며, 6개 JSONL·projection schema·Manifest bytes는 그대로 유지했습니다. 문서 중립화는 앱·DB 계약 수정이나 실제 Export 실행을 뜻하지 않습니다.

1. **데이터 계약 검토** [항목별 구현 및 제약 검토](data-contract-review.md)을 먼저 읽어주세요. A 구현과 유지/수정 권고/협의 사항을 구분했습니다. **기존 audit 자료가 11.docx 전체 수정 완료를 뜻하지는 않습니다.** 과거 전체 DDL 기준은0.6.1/0006, 현재 소스 검토 기준은0.11.0/0011, 동봉 schema는 최신 전체 DDL이 아닌 Export projection 제안입니다.
2. [차이 및 접촉 이벤트 미확정 사항](audit-export-review.md)을 확인해주세요.
3. [Manifest](samples/export-proposal/manifest.json): 기존 공통4종 + audit_events, 고객 참조 보조 customers까지 **6파일/6행**입니다. 파일 경로는 이 ZIP의 `samples/` 기준입니다.
4. [projection schema](samples/export-proposal/schema_contract.json): A Export allowlist입니다. 전달해주신 합성 물리 테이블 schema_contract와 별개입니다.
5. [수정 샘플 검증](audit-export-verification.json), [첨부 전체 데이터 검토](incoming-audit-review.json): 서로 다른 검증 범위입니다. 첨부 validation은 기존 A의4파일/각1행에 대한 결과이며 원본 Manifest는 ZIP에 없었습니다.

audit 샘플은 `samples/export-proposal/audit_events/part-00001.jsonl`입니다. event_ref/ticket_ref/cycle_no/action/result/reason_code/created_at만 있고 payload·원본 ID·계정·원문·연락처는 제외했습니다. 기존4파일과 고객 참조 파일은 byte 그대로입니다. customers는 주문/문의의 customer_ref FK를 확인하는 용도로 유지했습니다.

첨부의 CUSTOMER_CONTACT는 현재 A 업무 코드가 생성하지 않습니다. 감사 created_at을 실제 접촉 시각으로 간주하지 않습니다. 실제 접촉 원천·채널·시각·중복 기준을 추가로 합의해야 합니다. Manifest의 unknown/NOT_APPROVED는 의도한 상태입니다.

전달 ZIP에는 원본 첨부 전체 JSONL, 고객 원문, DB·환경 파일, 운영 키가 없습니다. hmac-vector의 키는 **공개 합성 예시 bytes00..1f**로 운영 사용 금지입니다. API·DB·Azure 상태를 변경하지 않았습니다.

ZIP을 별도 폴더에 푼 후 표준 Python으로 파일만 재검사할 수 있습니다.

```powershell
python tools/verify_export_proposal.py --delivery-only
```

이 명령은 구문·스키마 필드/타입/NULL·PK·동봉 FK·Manifest bytes/hash·공개 HMAC 벡터를 확인합니다. raw fixture를 동봉하지 않아 각 원천 ID의 HMAC 재계산은 이 전달본 명령의 범위가 아닙니다. 저장소에서 수행한 원천별 재계산 결과는 audit-export-verification.json에 있습니다. 함께 제공한 build_audit_proposal.py는 verifier가 사용하는 상수의 출처이며, 원천 fixture/카탈로그가 없는 전달 폴더에서 재생성기로 실행하지 마세요.
