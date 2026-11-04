# v2 개발 설명서

- [기획형 설명서 PDF](CS_Flow_v2_1_guide_20261104.pdf): 실행·기능·수정 위치, 8페이지
- [구현 범위](IMPLEMENTATION.md): L2/L3의 의미와 로컬/팀 연결 경계
- [임시 RAG](RAG.md): 검색·근거·문서 수정·provider 계약
- [로컬 API](LOCAL_API.md): 실제 경로·역할·revision·멱등성·저장
- [팀 연결 안내](INTEGRATION.md): 확인한 브랜치와 변환·교체 위치
- [검증 결과](VALIDATION.md): 이번 버전에서 직접 실행한 결과

PDF는 앱 실행에 필요한 파일이 아닙니다. 내용을 바꾸어 재생성하려면 Python의 `reportlab`과 한국어 TTF를 준비한 뒤 `scripts/build-guide.py --help`를 참고합니다. 폰트 폴더는 `--font-dir` 또는 `CSFLOW_GUIDE_FONT_DIR`로 지정할 수 있습니다.

