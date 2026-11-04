# Fabric 로컬 인수

2026-11-03 실제 ERD·DDL·PK/FK·타입과 Export 미구현/계약 제안은 [fabric-data-contract/README.md](fabric-data-contract/README.md)를 먼저 읽는다. 최신 파일0.6.1/head0006을 새 로컬 PostgreSQL에 적용해 확인했으며 이번 배포 DB 재조회·실제 Fabric 연동을 수행한 것은 아니다.

규범은 fabric-contract.md, phase4-analytics.md와 OpenAPI Submission입니다. examples/analytics-batch.json은 완전한 최소 합성 제출이며 examples/canonical-hashes.json은 실제 canonical 구현에서 생성한 재현 가능한 해시 벡터입니다. `python -m scripts.check_handoff_contract`로 확인합니다. 이는 오프라인 파일 검증이며 실제 Fabric emitter 실행이 아닙니다.

Decimal(50.000000)은 정규화 문자열 "50", +09:00 시각은 UTC Z, 정수값 float는 정수로 변환합니다. 객체 키는 정렬하고 테이블 배열은 PK 순, manifest 팀/상품/scope 집합도 정렬합니다. UTF-8/ensure_ascii=false/공백 없는 JSON을 SHA256 합니다. 벡터에는 primitive canonical JSON, 실제 제출 content hash, 네 테이블 해시와 PK 정렬 예시가 있습니다. source_input_hashes의 파일 bytes 해시와 payload/table/content 해시를 혼용하지 않습니다.

로컬 서비스 JWT는 별도 서명키/issuer/audience/allowlisted sub/exp·iat·nbf, analytics:receive와 analytics:publish 권한을 사용합니다. 관리자의 로그인 JWT로 게시할 수 없습니다. README verify는 생성한 로컬 키로 LOCAL_SYNTHETIC 토큰을 메모리에서 발급해 수신→validate→publish를 실제 loopback HTTP로 호출합니다. 토큰/비밀은 출력하거나 인수 파일에 넣지 않습니다. 운영 발급/회전·Managed Identity·출처 attestation은 미검증/팀 합의입니다.

같은 batch/같은 정규화 내용 재시도는 멱등, 다른 내용409입니다. validate200에서도 passed를 확인하며 FAILED는 새ID로 수정합니다. publish는 네 mart를 함께 원자 게시하고 저장 행 수/해시를 재검사합니다. window_end/source_as_of 각각 비감소/한쪽 증가만 허용하며 오래된 배치409가 이전 성공을 유지합니다. 과거 성공 재시도는 current 재승격하지 않습니다. 최초 미게시/실패 후 유지 응답은 Frontend 계약을 따릅니다.

15 scope는 원본4팀 UUID의 정확한 조합이며 어댑터의 FIXTURE_TEAMS로 고정했습니다. 서버는 요청자의 현재 허용 팀 집합/subset과 manifest scope의 정확한 일치를 사용합니다. ALL4 fallback, 전체 TOP10 행 숨김, 팀 점수 합산을 하지 않습니다. product 상세/근거/추세와 pinned batch도 같은 scope/현재 권한을 적용합니다.

KPI 합의가 필요합니다: 생성 cohort/팀 귀속/AUTO 미귀속, ticket·cycle·message·VOC episode 단위, 자동완료/이관 분모, 처리시간 합계/건수, 재문의/SLA/승인·검토 정의, product_daily의 팀차원/tag 중복/NULL 분모, 세부 제외 사유 enum입니다. 고정 재문의0/proxy나 팀차원 없는 전체값을 제한 관리자 실적으로 제공하지 않습니다. 원본은 합성 입력/정답 fixture이며 실제 운영 지표·불량률·Fabric 파이프라인 성공 증거가 아닙니다.

이번 분석 ‘게시’는 로컬 PostgreSQL current pointer 전환뿐입니다. 실제 원장 추출·Lakehouse·Notebook·Spark·Fabric 인증/파이프라인은 실행하지 않았습니다. 팀원 전송/원격 push·클라우드 접속도 하지 않았습니다.

## 7단계 보관 검토 합의

A는 로컬 receipt.payload/validation_result, batch.manifest/checksum/row_counts,4개 mart 저장 행을 별도로 집계합니다. receipt는 개발 추출30일(received_at), batch/mart는 집계90일(created_at)의 제안이며 source_as_of/day/window_end와 저장 시계를 구분합니다. 기간은 configurable이고 실제 운영 보존 합의가 아닙니다. 현재 batch 보호뿐 아니라 과거 SUCCEEDED의 불변 trigger·모든 receipt 불변 trigger/FK를 REQUIRES_DESIGN_CHANGE로 보고하므로 미게시/FAILED도 삭제 가능 판정이 아닙니다.

팀별 mart 행 필터가 receipt 전체·공유 batch 보관 단위와 같지 않으므로 제한된 관리자의 보관 보고에는 이 저장소 건수를NULL로 반환합니다. 전역은 명시 RETENTION_GLOBAL_REVIEW만 허용합니다. Bronze/Silver/Gold/Blob·외부 추출/백업·로그는 NOT_INSPECTED이며 실제 Fabric/Storage에 접속하지 않았습니다. 원천/중복 추출·receipt/mart 보관 시계, 재게시·불변성/백업·hold·PK/FK 참조와 정책 버전을 공동 확정해야 합니다. A는 점수 계산/삭제 SQL/실제 외부 정리를 구현하지 않습니다.

## 과거 기록: 지정 이름 이전 전 Azure 팀 개발 미연결 상태

A 수신 API 주소는 https://csflow-a-dev-api-6004dca5.azurewebsites.net/api/v1 이지만 ANALYTICS_SERVICE_IDS=[]로 실제 Fabric 게시 인증은 비활성이다. 새 서비스 키는 별도 비밀 App Settings에만 있고 문서/브라우저/ZIP에 없다. 실제 Fabric 파이프라인·호출·게시를 실행하지 않았으며 분석은 NO_PUBLISHED_BATCH 응답을 확인했다. 향후 서비스 subject·발급/회전·scope/KPI 합의 뒤 별도 승인된 연결을 진행한다. 로컬 canonical payload/검증·게시 계약은 유지한다.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
