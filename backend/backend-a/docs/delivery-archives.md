# Backend A 전달 아카이브 관리

2026-11-04 KST. 현재 전달 파일은 역할 중심 문서로 갱신했다. 교체 전 원본은 팀 체크아웃 밖의 Git 제외 백업에 보존했다. Git 과거 revision과 백업의 원래 문구는 수정하지 않는다.

## 정본 경로와 버전

`<BACKEND_A_ROOT>`는 저장소의 `backend/backend-a/`, `<WORKSPACE_ROOT>`는 팀 체크아웃을 포함한 작업 공간이다. ZIP은 로컬 산출물이며 Git에 추가하지 않는다.

| 파일 | 용도와 기준 | 갱신 범위 |
|---|---|---|
| `<BACKEND_A_ROOT>/.cache/fabric-audit-export-proposal-20261104.zip` | audit 포함 Export 제안. 6 JSONL/6행, 전체16멤버 | 역할 중심 문서·README·데이터 계약 검토 문서. 기존15멤버에서 검토 문서를 포함하도록 보완 |
| `<BACKEND_A_ROOT>/.cache/fabric-audit-export-final-with-doc11-reply-20261104.zip` | 위와 같은 내용의 최종 전달 경로 | 기존 파일명을 유지해 오래된 전달본 선택을 방지. 내부 문서명은 `data-contract-review.md` |
| `<BACKEND_A_ROOT>/.cache/docs-neutralization-20261104/review-delivery.zip` | 동일한 문서 검증용 로컬 사본 | 같은 정본 내용으로 갱신 |
| `<WORKSPACE_ROOT>/CS_Flow_AI_Backend_A_review.zip` | **0.6.0 / migration0006 과거 검토 소스**. 최신0.11.0 소스가 아님 | 작업 지시 문구와 검토 기준 안내만 정리. 앱·migration·업무 테스트·합성 데이터는 기존 bytes 유지 |

audit ZIP 세 개는 같은16멤버 bytes를 사용한다. 6개 JSONL·projection 스키마·Manifest·공개 합성 HMAC 벡터는 교체 전과 byte 단위로 동일하다. 문서 정리가 실제 DB Export·Fabric 적재·Silver 승인·협의 항목 구현 완료를 뜻하지 않는다.

과거 검토 ZIP은 문서가 바뀌어 `PACKAGE_MANIFEST.json`의 해당 파일 bytes/SHA256과 전체 파일 목록을 갱신했다. 원래 버전과 변경 이유는 내부 `ARCHIVE_NOTES.md`에 있다. 외부 원천의 `docs/source-manifest.json`, fixture 전달/출력 해시는 변경하지 않았다. 과거 업무 테스트 결과는 재실행하지 않았다.

## 백업과 생성 규칙

원본은 `<WORKSPACE_ROOT>/.cache/backend-a-original-deliveries-20261104/`에 보존했다. 백업은 현재 사용자만 접근하도록 제한했고, 팀 체크아웃 밖에 있으며 작업 공간 Git에서도 제외된다. 백업명은 원래 파일명과 원본 SHA256 일부를 포함한다. 백업을 최신 전달본으로 사용하지 않는다.

일반 생성기는 기존 파일을 조용히 덮어쓰지 않는다. 저장소의 최신 문서로 새 경로에 생성하고 검증한 뒤, 교체가 필요한 경우 원본 백업과 보호 파일 byte 비교를 먼저 수행한다.

```powershell
# backend/backend-a 기준. 새 출력 경로를 사용
python docs/fabric-data-contract/tools/build_audit_delivery.py --output .cache/new-reviewed-delivery.zip
```

생성기는 `data-contract-review.md`를 함께 포함해 README 링크가 빠지지 않게 한다. 원문 fixture 전체·DB·환경 파일·운영 비밀값은 audit 전달본에 포함하지 않는다.

## 이번에 실행한 검증

- 현재 추적 파일과 기존 Fabric 자료에서 정리 대상 이름·호칭·대화/작업 지시 표현을 검색했다.
- 갱신 ZIP4개를 파일명·문서·README·JSON의 decoded 문자열·중첩 아카이브까지 검사했다. 금지 표현0건, 중첩 ZIP/Office 아카이브0개, CRC·상대 링크 통과다.
- audit6파일의 행 수·bytes·SHA256과 FK/타입 등 기존 파일 계약을 확인했다. 서로 동일한 audit ZIP3개는 공통 exact bytes에 대해 동봉 verifier를 독립 폴더에서1회 실행했다.
- 과거 검토 ZIP의 `PACKAGE_MANIFEST.json`을 실제 멤버 bytes와 대조했다. 27개 JSONL과 모든 기존 스키마·앱·migration·업무 테스트·SQL은 보존했다.
- 로컬 배포/복구 ZIP4개도 검색했다. 대상 표현이 없어 그대로 유지했고 기존 SHA256과 일치한다. 배포 상태를 새로 확인하거나 변경한 것은 아니다.

실제 해시·변경 멤버 목록은 [검증 기록](evidence/archive-neutralization/summary.json), audit 제안의 정본 패키지는 [파일 검증](fabric-data-contract/delivery-verification.json)에 있다. 현재 Git 파일 수정은 과거 커밋의 문구를 지우지 않는다. 앱·DB·Azure 변경과 전체 업무 테스트는 이 검증 범위에 포함하지 않는다.
