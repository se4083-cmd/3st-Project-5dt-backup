# Fabric 전달 자료 — Backend A 실제 DB와 데이터 계약

**2026-11-04 audit 추가 검토:** 현재 로컬 소스는 **0.11.0 / migration 파일 head0011**, Git `feature/backend-a` / `2af74b73eacb9e692e17b1ad166d35152085859d`다. DB head·Azure는 이번에 조회하지 않았다. [audit 추가 검토와 차이표](audit-export-review.md), [수정 projection 스키마](samples/export-proposal/schema_contract.json), [수정 Manifest](samples/export-proposal/manifest.json)를 우선 읽는다. 공통4개 파일·고객 참조 파일 bytes를 보존하고 audit 1행을 추가해 **6파일/6행**으로 만들었다. 첨부 전체5파일/12,008행과 첨부 validation의 작은4파일/각1행은 서로 다른 자료다. **원본 Manifest는 첨부에 없다.** 실제 Export·Silver 승인·접촉 이벤트 호환 확인은 완료되지 않았다.

[데이터 계약 항목별 검토](data-contract-review.md)는 라벨 NULL·길이·불만 필수값·후속·감사 경계를 현재 소스와 대조한 자료다. [전달 README](delivery-README.md)와 [패키지 검증](delivery-verification.json)을 함께 확인한다. 문서 중립화 후의 ZIP 정본과 별도 원본 백업은 [아카이브 관리](../delivery-archives.md)에 기록한다.

**이전 공유 검토(당시 0.7.1/head0007):** 이 폴더의 DDL·카탈로그는 **0.6.1/head0006 당시의 스키마·증거 snapshot**이다. 당시 추가된 DB 변경은 직원 WORKLOAD_READ 허용값이었다. 보관된0.6.1 소스를 사용한 오프라인 verifier를 별도 임시 사본에서 통과했고, 당시 분석 경로·참조 schema가 OpenAPI와 동일함을 확인했다. verifier의 info.version 비교는0.6.1에 고정돼 있어 최신 앱에서 그대로 실행하면 버전 차이로 실패할 수 있다. 보관 DDL을 최신0011 전체 DDL로 오해하지 않는다. 이번 audit 작업은 이 DDL·이전 검증 기록을 재생성하지 않았다.

보관 schema.sql은 추출 당시 bytes/hash를 유지한다. pg_dump 출력의 마지막 빈 줄 때문에 최초 stage의 diff whitespace 검사에서 EOF 빈 줄1건이 표시되며, 해시가 고정된 DDL을 이 스타일 경고만으로 재작성하지 않았다.

담당 폴더의 .gitattributes는 기존 text/eol 규칙을 유지하고, 해시 대상인 schema.sql과 samples의 JSONL에만 자동 줄바꿈 변환 예외를 둔다. Windows의 core.autocrlf 설정과 관계없이 DDL 및 manifest가 가리키는 JSONL bytes를 보존하기 위한 Git 공유 설정이다.

기본 카탈로그는 2026-11-03 KST 작성했으며 후속 audit 제안을 별도로 보완했다. 모든 경로는 팀 저장소의 **backend/backend-a/** 기준이다. 자료의 Git 공유와 실제 데이터 Export·Fabric 적재는 별개다.

## 먼저 읽을 자료

1. [schema.md](schema.md), [ERD 원본](erd.mmd), [schema.sql](schema.sql): 11/3 요청인 ERD·DDL·PK/FK·정확한 타입/NULL/default를 우선 확인한다.
2. [fixture 차이표](fixture-differences.md): 합성 계약 27항목과 실제 A 32테이블을 구분한다.
3. [lifecycle-events.md](lifecycle-events.md): 회차·revision·감사·후속·중복 제거의 실제 보장 범위.
4. [export-contract.md](export-contract.md): **미구현인 DB→Blob Export의 계약 제안**이다.
5. [scope-publish-contract.md](scope-publish-contract.md), [실제 생성 OpenAPI 발췌](openapi-analytics.json): 이미 구현된 Gold 수신·게시·조회와 미합의 KPI.
6. [samples 안내](samples/README.md), [open-questions.md](open-questions.md), [검증 결과](verification.md).

## 0006 보관 자료의 코드 기준점과 확인 범위

**구현 확인:** 파일의 pyproject.toml과 app/main.py는 0.6.1이다. 실제 Alembic graph와 새 격리 로컬 PostgreSQL 적용 결과의 유일 head는 0006이다. Git feature/backend-a, 출발 commit `447c31890c243e1175b805596a84a19720058edf` 위의 기존 미커밋 Azure 변경이 포함된 작업 트리다. 문서가 해당 commit만의 내용이라고 주장하지 않는다. [source-basis.json](source-basis.json)에 실제 읽은 소스 SHA256을 남겼다. 담당 폴더와 부모에서 AGENTS.md는 발견되지 않았다.

**구현 확인:** 기존 migration 0001–0006을 **새 127.0.0.1 임시 PostgreSQL 16.15**에 적용하고 `alembic check`로 모델과 대조했다. schema-only pg_dump로 DDL을 추출했고 seed/fixture/업무 행을 덤프하지 않았다. 최종 구조는 32테이블(31개 업무·보조 + Alembic), 제약138·인덱스57·트리거7·native ENUM0이다. 기존 로컬 DB/API는 건드리지 않았다. [추출 증거](schema-verification.json).

**확인 범위 제한:** 이번에는 Azure에 접속하거나 배포 DB를 조회하지 않았다. 네트워크/방화벽을 변경하지 않아야 하는 요청을 지키며 이미 저장된 [이전 완료 증거](../evidence/azure-migration/)와 [배포 보고](../azure-migration.md)를 참고했다. 거기에는 같은 0.6.1 ZIP/head0006·PostgreSQL16.15·새 리소스·자동 PAUSED·분석 미게시가 기록돼 있다. **현재 배포 DB와 이번 DDL의 일치를 새로 검증한 것은 아니다.** 이전 DB 건수나 5개 JSONL·12,008건을 최신 실제 건수로 재표시하지 않는다.

기존 합성 원본은 [schema 메타데이터 사본](fixture-schema-contract.original.json)과 [config의 시각·라벨 참조](fixture-config-reference.json)에 한정해 실었다. 원본 데이터 파일/원문/전체 계정은 복사하지 않았다. 이 config의 2026-10-31 기준시각은 고정 합성 fixture 기준이며 현재 DB freshness가 아니다. 원본27항목과 저장소의22항목 사본을 동일 파일로 잘못 취급하지 않는다.

| 항목 | 구분 | 현재 의미 |
|---|---|---|
| 실제 물리 스키마·PK/FK·Enum/CHECK·로컬 DDL | 구현 확인 | migration 적용 + 모델 대조 완료 |
| 회차/멱등/후속 gate/분석 원자 게시 | 구현 확인 | 코드 계약. 실제 B/Fabric 엔진 통합 결과는 아님 |
| 기존 fixture 계약/오프라인 Lakehouse 파일 생성기 | 구현 확인 | 합성 파일 변환이며 운영 DB Export와 다름 |
| A DB→Blob, 예약 추출·manifest 업로드·증분/CDC | 미구현 | 이번에 새 API·파이프라인을 추가하지 않음 |
| Export serialization/HMAC/snapshot/retry | 제안 | 샘플도 제안이라고 표시. 운영 적용 전 합의 필요 |
| 팀 귀속·episode·완전성·KPI·읽기 권한·서비스 발급 | 팀 합의 필요 | [질문](open-questions.md) 참조 |
| 전달받은 합성5파일/12,008행 | 파일 검토 완료 / 의미 합의 필요 | JSONL·첨부 schema·validation은 확인. 원본 Manifest 없음. Bronze/Silver 실제 적재·승인은 미검증 |

## 보관 배포 주소 — 이번 최신 상태 미확인

배포 문서의 API base는 `https://csflow-backend-a.azurewebsites.net/api/v1`, Swagger는 `/docs`, DB FQDN은 `csflow-backend-a-pg.postgres.database.azure.com`이다. **Fabric용 DB 계정·읽기 view·방화벽·서비스 subject를 새로 설정하지 않았다.** 배포 증거상 ANALYTICS_SERVICE_IDS=[]라 서비스 게시 경계는 503으로 비활성이다. 문서에 키/비밀번호/토큰은 없다. 일반 관리자 토큰으로 게시할 수 없다.

## 재현 및 변경 제한

이번 audit 제안 파일만 검증하려면 **앱 import·DB·네트워크가 없는** 아래 명령을 사용한다. [검증 기록](audit-export-verification.json)과 [첨부 검토](incoming-audit-review.json)는 이번 범위의 별도 기록이다.

```powershell
python docs/fabric-data-contract/tools/verify_export_proposal.py --write-report
```

아래 명령과 과거 verification 파일은 **기존 0006 자료 생성/검증 절차**다. 최신 전체 스키마·DB 검증을 뜻하지 않으며 이번 audit 작업에서는 DB 추출기나 전체 verifier를 실행하지 않았다.

담당 폴더에서 고정 requirements-dev를 설치한 Python으로 실행한다. 추가 의존성 다운로드나 앱 기동 없이 샘플/OpenAPI 검증이 가능하다.

```powershell
python docs/fabric-data-contract/tools/verify_samples.py
python -m scripts.check_handoff_contract
# DDL을 다시 추출하려면: 기존 DB URL을 받지 않고 새 로컬 임시 클러스터만 생성
python docs/fabric-data-contract/tools/extract_local_schema.py --pg-bin '<로컬 PostgreSQL16 bin>'
python docs/fabric-data-contract/tools/build_reference.py
```

추출기는 기존 DB를 지정할 옵션이 없고 127.0.0.1에만 listen한다. schema.sql은 자료이며 운영 DB에 실행할 배포 명령이 아니다. 실제 적용은 기존 Alembic과 별도 승인된 DB 권한 절차를 따른다. 업무 기능·migration·클라우드 설정은 이번에 바꾸지 않았다.
