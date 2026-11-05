"""CS Flow AI: 가상 문의 12건 개발용 분류 확인.

classify_inquiry.py, test_openai.py, .env와 같은 폴더에 놓으세요.
실행: python check_classification.py
목록만 확인(API 호출 없음): python check_classification.py --list

각 문장을 API에 1회씩 순서대로 보냅니다. 자동 재시도는 하지 않습니다.
HTTP/연결/인증 오류가 발생하면 남은 호출을 중단하고 결과를 남깁니다.
보고서는 check_results 폴더에 생성됩니다. 제공된 합성 문의만 사용하세요.
정식 분류 정확도 평가가 아니며, 요약의 사실 일치는 별도 검토 대상입니다.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


def load_cases(path):
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not 1 <= len(cases) <= 30:
        raise ValueError("cases에는 1~30개의 합성 문의가 있어야 합니다.")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("각 사례는 JSON 객체여야 합니다.")
        for key in ("id", "text", "expected_category", "review_note"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError(f"사례의 {key} 항목을 확인하세요.")
        if case["id"] in seen or len(case["text"]) > 10000:
            raise ValueError("중복 사례 ID 또는 10,000자를 넘는 문의가 있습니다.")
        seen.add(case["id"])
    return cases


def save_report(root, report):
    folder = root / "check_results"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    destination = folder / f"classification_check_{stamp}_UTC.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="합성 문의를 순차 실행하고 분류 코드를 비교합니다.")
    parser.add_argument("--list", action="store_true", help="사례 목록만 출력. API 호출 없음.")
    args = parser.parse_args()
    try:
        cases = load_cases(root / "classification_cases.json")
    except (OSError, ValueError) as error:
        raise SystemExit(f"사례 파일 확인: {error}") from None
    if args.list:
        for case in cases:
            print(f"{case['id']} / 기대={case['expected_category']} / {case['text']}")
        print(f"총 {len(cases)}건. API는 호출하지 않았습니다.")
        return

    from azure.identity import AzureCliCredential, get_bearer_token_provider
    from openai import APIStatusError, OpenAI

    from classify_inquiry import CATEGORY_LABELS, OUTPUT_SCHEMA, PROMPT, parse_result
    from test_openai import load_settings

    if any(case["expected_category"] not in CATEGORY_LABELS for case in cases):
        raise SystemExit("사례 파일에 현재 분류 코드 목록에 없는 기대값이 있습니다.")
    endpoint, deployment = load_settings()
    token_provider = get_bearer_token_provider(
        AzureCliCredential(), "https://cognitiveservices.azure.com/.default"
    )
    report = {
        "check_kind": "development_smoke_check",
        "is_independent_evaluation": False,
        "summary_factuality_evaluated": False,
        "taxonomy_status": "draft",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "deployment": deployment,
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(OUTPUT_SCHEMA, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "planned_cases": len(cases),
        "results": [],
    }
    print(f"합성 문의 {len(cases)}건을 순차 호출합니다. 자동 재시도는 하지 않습니다.", flush=True)
    with OpenAI(
        base_url=f"{endpoint}/openai/v1/",
        api_key=token_provider,
        timeout=60.0,
        max_retries=0,
    ) as client:
        for number, case in enumerate(cases, 1):
            row = {
                "case_id": case["id"],
                "inquiry": case["text"],
                "expected_category": case["expected_category"],
                "summary_review_note": case["review_note"],
                "summary_review": "NOT_REVIEWED",
            }
            started = perf_counter()
            should_stop = False
            try:
                response = client.responses.create(
                    model=deployment,
                    instructions=PROMPT,
                    input=case["text"],
                    text={"format": {
                        "type": "json_schema",
                        "name": "inquiry_classification_draft_v1",
                        "strict": True,
                        "schema": OUTPUT_SCHEMA,
                    }},
                    reasoning={"effort": "minimal"},
                    max_output_tokens=800,
                    store=False,
                )
                row["response_model"] = response.model
                if response.usage is not None:
                    row["input_tokens"] = response.usage.input_tokens
                    row["output_tokens"] = response.usage.output_tokens
                result = parse_result(response)
                row["actual_category"] = result["category"]
                row["summary"] = result["summary"]
                row["category_match"] = result["category"] == case["expected_category"]
                row["status"] = "MATCH" if row["category_match"] else "MISMATCH"
            except APIStatusError as error:
                row.update(status="API_ERROR", http_status=error.status_code, error_type=type(error).__name__)
                should_stop = True
            except (ValueError, TypeError) as error:
                row.update(status="INVALID_OUTPUT", error_type=type(error).__name__)
            except Exception as error:
                row.update(status="CALL_ERROR", error_type=type(error).__name__)
                should_stop = True
            row["elapsed_seconds"] = round(perf_counter() - started, 3)
            report["results"].append(row)
            actual = row.get("actual_category", "-")
            print(
                f"[{number}/{len(cases)}] {case['id']} {row['status']} "
                f"기대={case['expected_category']} / 실제={actual}",
                flush=True,
            )
            if "summary" in row:
                print("  요약:", row["summary"], flush=True)
            if should_stop:
                print("호출 오류로 남은 요청을 중단합니다. 오류 종류와 HTTP 상태는 결과 파일에 기록됩니다.", flush=True)
                break

    rows = report["results"]
    matched = sum(row["status"] == "MATCH" for row in rows)
    mismatched = sum(row["status"] == "MISMATCH" for row in rows)
    errors = sum(row["status"] not in ("MATCH", "MISMATCH") for row in rows)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["counts"] = {
        "attempted": len(rows), "category_match": matched, "category_mismatch": mismatched,
        "errors": errors, "not_run": len(cases) - len(rows),
        "input_tokens_reported": sum(row.get("input_tokens", 0) for row in rows),
        "output_tokens_reported": sum(row.get("output_tokens", 0) for row in rows),
    }
    destination = save_report(root, report)
    print(f"분류 일치 {matched}/{len(cases)} / 불일치 {mismatched} / 오류 {errors} / 미실행 {len(cases)-len(rows)}")
    print("요약의 사실 일치는 별도 검토가 필요합니다.")
    print("결과 파일:", destination)
    if matched != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

