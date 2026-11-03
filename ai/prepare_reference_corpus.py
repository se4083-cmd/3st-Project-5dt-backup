"""Prepare the supplied v01 JSONL for a future existing RAG importer.

This command only filters and audits provided records. It is not a search engine,
index writer, approval gate, or backend DTO adapter.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="제공된 v01 공식 참고자료만 분리·검증합니다.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review-case", type=Path, help="사용자가 제공한 R10 정의와 기대 근거만 확인")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    lines = [line for line in source_bytes.decode("utf-8-sig").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]
    roles = Counter(record.get("dataset_role") for record in records)
    if roles != {"official_reference": 73, "simulation_only": 3}:
        raise ValueError("이번 제공 자료의 official_reference 73 / simulation_only 3 구성을 확인하세요.")
    ids = [record["id"] for record in records]
    if any(not isinstance(value, str) or not value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("문서 ID가 비어 있거나 중복됐습니다.")
    selected = []
    selected_lines = []
    legacy_map = {}
    for line, record in zip(lines, records):
        # retrieval_eligible is also true on demo records: the role is mandatory.
        if record["dataset_role"] != "official_reference":
            continue
        if record.get("retrieval_eligible") is not True or record.get("search_eligible") is False:
            raise ValueError(f"검색 제외로 표시된 공식 문서: {record['id']}")
        if record.get("index_fields") != ["title", "content"]:
            raise ValueError(f"제공된 색인 필드가 예상과 다릅니다: {record['id']}")
        for field in ("title", "content", "source", "source_url", "source_locator", "source_version"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"필수 필드 누락: {record['id']} / {field}")
        if not isinstance(record.get("applicability"), dict) or not record["applicability"]:
            raise ValueError(f"적용 범위 누락: {record['id']}")
        for field in ("conditions", "exceptions", "required_facts"):
            if not isinstance(record.get(field), list):
                raise ValueError(f"조건 메타데이터 누락: {record['id']} / {field}")
        for field in ("auto_decision_allowed", "auto_send_allowed", "auto_refund_allowed"):
            if record.get(field) is not False:
                raise ValueError(f"자동 처리 제한을 확인하세요: {record['id']} / {field}")
        for old_id in record.get("legacy_document_ids", []):
            if not isinstance(old_id, str) or not old_id.strip():
                raise ValueError("이전 ID 형식 오류")
            if old_id in legacy_map and legacy_map[old_id] != record["id"]:
                raise ValueError(f"교체 ID 충돌: {old_id}")
            if old_id in ids and old_id != record["id"]:
                raise ValueError(f"현재 문서 ID와 교체 ID 충돌: {old_id}")
            legacy_map[old_id] = record["id"]
        selected.append(record)
        selected_lines.append(line)
    review_case = None
    if args.review_case is not None:
        review_case = json.loads(args.review_case.read_text(encoding="utf-8-sig"))
        if (review_case["case_id"] != "R10"
                or review_case["input_conditions"] != {"shipping_type": "seller", "simulation_mode": False}
                or review_case["corpus_filter"] != {"dataset_role": "official_reference"}
                or review_case["pass_criterion"] != {"metric": "expected_document_in_top_k", "top_k": 5}):
            raise ValueError("사용자가 제공한 R10 검수 조건을 확인하세요.")
        expected = review_case["expected_document"]
        document = next((record for record in selected if record["id"] == expected["id"]), None)
        if document is None or any(document.get(field) != value for field, value in expected.items()):
            raise ValueError("R10 기대 문서·본문·필수 확인사항이 제공 자료와 다릅니다.")
    corpus = ("\n".join(selected_lines) + "\n").encode("utf-8")
    # Verify lossless preservation of every field, including approval and limits.
    if [json.loads(line) for line in corpus.decode("utf-8").splitlines()] != selected:
        raise ValueError("분리한 자료가 입력과 다릅니다.")
    manifest = {
        "source_filename": args.source.name,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "prepared_corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "source_records": len(records),
        "selected_role": "official_reference",
        "selected_records": len(selected),
        "selected_ids": [record["id"] for record in selected],
        "excluded_ids": [r["id"] for r in records if r["dataset_role"] != "official_reference"],
        "team_approval_status_counts": dict(Counter(r["team_approval_status"] for r in selected)),
        "legacy_id_to_current_id": legacy_map,
        "replacement_aliases": {old: new for old, new in legacy_map.items() if old != new},
        "runtime_search_connected": False,
        "index_updated": False,
        "r10_executed": False,
        "draft_generation_executed": False,
    }
    payloads = {
        "official_reference_20261103_v01.jsonl": corpus,
        "preparation_manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    # Never overwrite a different corpus or manifest from someone else's work.
    for filename, data in payloads.items():
        target = args.output_dir / filename
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f"기존 파일 내용이 달라 덮어쓰지 않습니다: {target.name}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, data in payloads.items():
        target = args.output_dir / filename
        if not target.exists():
            target.write_bytes(data)
    print("공식 참고자료 73개 분리 / 시연 3개 제외 / 필드 보존 확인")
    print(f"이전 ID 교체 후보 {len(manifest['replacement_aliases'])}개 (실제 저장소 교체 미실행)")
    print("검색·색인·R10·AI 초안 연결은 미실행입니다.")
    if review_case is not None:
        print("R10 정의·기대 근거 보존 확인 (프로젝트 검색 실행이나 통과 판정 아님)")


if __name__ == "__main__":
    main()
