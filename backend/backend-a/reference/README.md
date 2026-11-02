# 외부 전체 fixture와 작은 합성 자료

전체 원본 전달본·다운로드 원천·검수 대기열/원문·lakehouse_input·DB load SQL은 이 저장소에 포함하지 않는다. 승인/이용조건이 불명확한 AI Hub/리뷰/외부 원천도 업로드하지 않는다. 기존 검토 ZIP0.6.0을 구현 소스로 사용하지 않는다.

포함한 작은 합성 자료는 app/seed.py의 minimal 개발 계정/주문 생성, tests/analytics_helpers.py의 LOCAL_SYNTHETIC 고정 분석 fixture, docs/examples/analytics-batch.json·요청/해시 예시다. 실제 고객/대화나 외부 모델 산출물이 아니다. 비밀번호/서명키가 필요한 테스트 상수는 REVIEW_* placeholder이고 실제 실행 자격정보가 아니다.

전체 합성 전달본을 이미 합법적으로 가진 팀원은 config.json·schema_contract.json·data/22개 운영/분석 테이블·제공Gold/경계 정답 등이 든 폴더를 **저장소 밖 또는 ignored reference/fixture**에 준비한다. schema만으로 가짜 원문/Gold/과거 실행 증거를 만들지 않는다. 필드 계약 참고는 ../docs/fixture-schema-contract.json이며 이것은 전체 데이터가 아니다.

- local_runtime init: `--fixture-dir '<권한 확인한 로컬 합성 폴더>'`.
- pytest: `CSFLOW_FIXTURE_DIR`을 같은 경로로 명시. 미지정 시 Backend A의 reference/fixture를 찾는다.
- 전체 fixture 없으면 tests/conftest.py의 fixture_dir가 skip한다. 대상은 test_seed_and_migration의 전체 적재/rollback/신규 접수, test_phase2_migration의 원본 재문의·재적재, test_analytics의15scope/원본Gold·정확한 scope 부재, test_analytics_database의기존0003→0004원본 보존, test_phase6_postgres의원본업그레이드, test_retention의전체원본inventory다.
- PostgreSQL이 없으면 기본 SQLite 검증의 실제PG lock/lease/race 테스트도 별도 skip이며 전체PostgreSQL 성공으로 표현하지 않는다.
- scripts.local_runtime init/test/verify의 전체 원본 대조는 fixture 없으면 완결할 수 없다. 자동 다운로드나 네트워크 fallback은 없다. fixture 없이 시작할 최소 API는 README의 별도 빈 로컬PG+minimal 절차를 사용한다.

원본821개 사용자의 로그인 불가 표식을 유지한다. 실제 외부 서비스/판매자 API/키·모델·Fabric/Storage·발송을 호출하지 않는다.
