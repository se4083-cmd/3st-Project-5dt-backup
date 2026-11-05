"""CS Flow AI: 합성 문의의 분류·검토 신호를 순차 점검합니다.

기존 classify_with_signals.py, classify_inquiry.py, test_openai.py, .env와
같은 폴더에 이 파일과 signal_cases.json을 놓으세요.
    python check_signals.py --list  # API 호출 없음
    python check_signals.py         # 합성 문의 16건, 각 1회 호출
    python check_signals.py --limit 4
    python check_signals.py --cases S02 S10 S12 S14

과거 분류·신호 재검증을 위해 predict_complaint=False로 기존 프롬프트를 명시 호출합니다. 재시도와 병렬 호출은 하지 않습니다.
호출·인증·HTTP 오류는 이후 호출을 중단합니다. 잘못된 출력은 오류로 집계합니다.
각 시도 후 check_results에 진행 상태를 저장합니다. 개인정보는 입력하지 마세요.
개발용 점검이며 독립 평가가 아닙니다. 요약의 사실 일치와 근거의 의미 적절성은
사람이 별도로 검토합니다. review_required는 자동 처리 허용 값이 아닙니다.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_cases(path):
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("synthetic_only") is not True:
        raise ValueError("synthetic_only가 true인 제공된 합성 사례 파일을 사용하세요.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 30:
        raise ValueError("합성 사례는 1~30개여야 합니다.")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("각 사례는 JSON 객체여야 합니다.")
        for key in ("id", "text", "expected_category", "review_note"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError(f"사례의 {key} 항목을 확인하세요.")
        tags = case.get("expected_risk_tags")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("기대 태그는 문자열 배열이어야 합니다.")
        if len(tags) != len(set(tags)):
            raise ValueError("기대 태그에 중복이 있습니다.")
        review = case.get("expected_review_required")
        if type(review) is not bool:
            raise ValueError("기대 검토 표시는 true 또는 false여야 합니다.")
        if review != (case["expected_category"] == "UNKNOWN" or bool(tags)):
            raise ValueError("기대 분류·태그와 기대 검토 표시가 일치하지 않습니다.")
        if case["id"] in seen or len(case["text"]) > 10000:
            raise ValueError("중복 ID 또는 10,000자를 넘는 문의가 있습니다.")
        seen.add(case["id"])
    return cases


def select_cases(cases, selected_ids=None, limit=None):
    if selected_ids is not None:
        if not selected_ids or len(selected_ids) != len(set(selected_ids)):
            raise ValueError("--cases에 중복 없이 사례 ID를 지정하세요.")
        by_id = {case["id"]: case for case in cases}
        if any(case_id not in by_id for case_id in selected_ids):
            raise ValueError("--cases에 사례 파일에 없는 ID가 있습니다.")
        return [by_id[case_id] for case_id in selected_ids]
    if limit is not None:
        if not 1 <= limit <= len(cases):
            raise ValueError(f"--limit은 1~{len(cases)} 사이여야 합니다.")
        return cases[:limit]
    return cases


def compare_result(case, result):
    """태그 순서는 무시하며 근거의 원문 포함 여부도 확인합니다."""
    tags, evidence = result["risk_tags"], result["risk_evidence"]
    if (
        not isinstance(tags, list)
        or any(not isinstance(tag, str) for tag in tags)
        or len(tags) != len(set(tags))
        or type(result["review_required"]) is not bool
        or not isinstance(evidence, list)
    ):
        raise ValueError("분석 결과의 태그·근거·검토 표시 형식을 확인하세요.")
    evidence_tags = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"tag", "quote"}:
            raise ValueError("근거 객체 형식이 올바르지 않습니다.")
        quote = item["quote"]
        if not isinstance(quote, str) or not quote.strip() or quote not in case["text"]:
            raise ValueError("원문에 없는 근거가 있습니다.")
        evidence_tags.append(item["tag"])
    if len(evidence_tags) != len(tags) or set(evidence_tags) != set(tags):
        raise ValueError("각 태그에 원문 근거가 하나씩 있어야 합니다.")
    return {
        "category_match": result["category"] == case["expected_category"],
        "risk_tags_match": set(tags) == set(case["expected_risk_tags"]),
        "review_required_match": result["review_required"] == case["expected_review_required"],
        "evidence_quotes_in_source": True,
    }


def update_counts(report):
    rows = report["results"]
    report["counts"] = {
        "attempted": len(rows),
        "all_match": sum(row["status"] == "MATCH" for row in rows),
        "mismatch": sum(row["status"] == "MISMATCH" for row in rows),
        "errors": sum(row["status"] in ("API_ERROR", "CALL_ERROR", "INVALID_OUTPUT") for row in rows),
        "interrupted": sum(row["status"] == "INTERRUPTED" for row in rows),
        "not_run": report["planned_cases"] - len(rows),
        "category_match": sum(row.get("category_match") is True for row in rows),
        "risk_tags_match": sum(row.get("risk_tags_match") is True for row in rows),
        "review_required_match": sum(row.get("review_required_match") is True for row in rows),
        "input_tokens_reported": sum(row.get("input_tokens", 0) for row in rows),
        "output_tokens_reported": sum(row.get("output_tokens", 0) for row in rows),
        "reasoning_tokens_reported": sum(row.get("reasoning_tokens", 0) for row in rows),
        "attempts_without_usage": sum("input_tokens" not in row for row in rows),
    }
    report["updated_at_utc"] = utc_now()


def write_report(path, report):
    update_counts(report)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run_checks(cases, analyze, report, checkpoint):
    """analyze를 바꿔 API 호출 없이 실행 흐름을 검증합니다."""
    for number, case in enumerate(cases, 1):
        row = {
            "case_id": case["id"],
            "inquiry": case["text"],
            "expected_category": case["expected_category"],
            "expected_risk_tags": case["expected_risk_tags"],
            "expected_review_required": case["expected_review_required"],
            "manual_review_note": case["review_note"],
            "summary_review": "NOT_REVIEWED",
            "evidence_relevance_review": "NOT_REVIEWED",
        }
        started = perf_counter()
        should_stop = False
        try:
            result, response = analyze(case["text"])
            row["response_model"] = getattr(response, "model", None)
            usage = getattr(response, "usage", None)
            if usage is not None:
                row["input_tokens"] = usage.input_tokens
                row["output_tokens"] = usage.output_tokens
                details = getattr(usage, "output_tokens_details", None)
                reasoning_tokens = getattr(details, "reasoning_tokens", None)
                if isinstance(reasoning_tokens, int):
                    row["reasoning_tokens"] = reasoning_tokens
            checks = compare_result(case, result)
            row.update(actual=result, **checks)
            row["status"] = "MATCH" if all(checks.values()) else "MISMATCH"
        except KeyboardInterrupt:
            row.update(status="INTERRUPTED", error_type="KeyboardInterrupt")
            should_stop = True
            report["interrupted"] = True
        except (ValueError, TypeError, KeyError) as error:
            row.update(status="INVALID_OUTPUT", error_type=type(error).__name__)
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            row.update(
                status="API_ERROR" if isinstance(status_code, int) else "CALL_ERROR",
                error_type=type(error).__name__,
            )
            if isinstance(status_code, int):
                row["http_status"] = status_code
            should_stop = True
        row["elapsed_seconds"] = round(perf_counter() - started, 3)
        report["results"].append(row)
        checkpoint()
        actual = row.get("actual", {})
        print(
            f"[{number}/{len(cases)}] {case['id']} {row['status']} "
            f"분류={actual.get('category', '-')} "
            f"태그={actual.get('risk_tags', '-')} "
            f"검토={actual.get('review_required', '-')}",
            flush=True,
        )
        if actual:
            print("  요약:", actual["summary"], flush=True)
            for evidence in actual["risk_evidence"]:
                print(f"  근거 [{evidence['tag']}]: {evidence['quote']}", flush=True)
        if "input_tokens" in row:
            print(
                f"  토큰: 입력={row['input_tokens']} 출력={row['output_tokens']} "
                f"(출력 중 추론={row.get('reasoning_tokens', '미제공')})",
                flush=True,
            )
        if row["status"] == "MISMATCH":
            different = [
                key for key in ("category_match", "risk_tags_match", "review_required_match")
                if row.get(key) is False
            ]
            print("  불일치 항목:", ", ".join(different), flush=True)
        elif "error_type" in row:
            print("  오류 종류:", row["error_type"], "HTTP:", row.get("http_status", "-"), flush=True)
        if should_stop:
            print("남은 호출을 중단하고 현재까지의 결과를 저장했습니다.", flush=True)
            break
    update_counts(report)


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="합성 문의의 분류·검토 신호를 비교합니다.")
    parser.add_argument("--list", action="store_true", help="목록만 확인. API 호출 없음.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--limit", type=int, help="앞에서 지정한 건수만 실행")
    selection.add_argument("--cases", nargs="+", metavar="ID", help="지정한 사례만 순서대로 실행")
    args = parser.parse_args()
    try:
        cases = load_cases(root / "signal_cases.json")
        cases = select_cases(cases, selected_ids=args.cases, limit=args.limit)
    except (OSError, ValueError) as error:
        raise SystemExit(f"사례 파일 확인: {error}") from None

    if args.list:
        for case in cases:
            print(
                f"{case['id']} / {case['expected_category']} / "
                f"{case['expected_risk_tags']} / 검토={case['expected_review_required']}\n"
                f"  {case['text']}"
            )
        print(f"총 {len(cases)}건. API는 호출하지 않았습니다.")
        return

    from azure.identity import AzureCliCredential, get_bearer_token_provider
    from openai import OpenAI

    from classify_with_signals import (
        CATEGORY_LABELS, MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, PROMPT, PROMPT_VERSION,
        REASONING_EFFORT, RISK_LABELS, analyze_inquiry,
    )
    from test_openai import load_settings

    if any(
        case["expected_category"] not in CATEGORY_LABELS
        or any(tag not in RISK_LABELS for tag in case["expected_risk_tags"])
        for case in cases
    ):
        raise SystemExit("사례의 기대 분류·태그가 현재 코드의 허용 목록과 다릅니다.")
    endpoint, deployment = load_settings()
    token_provider = get_bearer_token_provider(
        AzureCliCredential(), "https://cognitiveservices.azure.com/.default"
    )
    report = {
        "check_kind": "development_signal_smoke_check",
        "is_independent_evaluation": False,
        "summary_factuality_evaluated": False,
        "evidence_semantic_relevance_evaluated": False,
        "auto_processing_permission_evaluated": False,
        "taxonomy_status": "draft",
        "started_at_utc": utc_now(),
        "deployment": deployment,
        "prompt_version": PROMPT_VERSION,
        "generation_settings": {
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_retries": 0,
        },
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(OUTPUT_SCHEMA, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "source_sha256": {
            name: sha256_file(root / name) for name in (
                "check_signals.py", "signal_cases.json", "classify_with_signals.py",
                "classify_inquiry.py", "test_openai.py",
            )
        },
        "planned_cases": len(cases),
        "selected_case_ids": [case["id"] for case in cases],
        "results": [],
    }
    folder = root / "check_results"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    destination = folder / f"signal_check_{stamp}_UTC.json"
    checkpoint = lambda: write_report(destination, report)
    checkpoint()
    print(f"합성 문의 {len(cases)}건을 순차 호출합니다. 자동 재시도는 하지 않습니다.", flush=True)
    print(f"프롬프트: {PROMPT_VERSION} / 추론 강도: {REASONING_EFFORT}", flush=True)
    try:
        with OpenAI(
            base_url=f"{endpoint}/openai/v1/",
            api_key=token_provider,
            timeout=60.0,
            max_retries=0,
        ) as client:
            run_checks(
                cases,
                lambda inquiry: analyze_inquiry(client, deployment, inquiry, predict_complaint=False),
                report,
                checkpoint,
            )
    except KeyboardInterrupt:
        report["interrupted"] = True
    except Exception as error:
        report["runner_error_type"] = type(error).__name__
    finally:
        report["finished_at_utc"] = utc_now()
        checkpoint()
    counts = report["counts"]
    print(
        f"전체 일치 {counts['all_match']}/{len(cases)} / 불일치 {counts['mismatch']} / "
        f"오류 {counts['errors']} / 중단 {counts['interrupted']} / 미실행 {counts['not_run']}"
    )
    print("요약의 사실 일치와 근거의 의미 적절성은 별도 검토가 필요합니다.")
    print("자동 처리 허용 여부는 평가하지 않았습니다.")
    print("결과 파일:", destination)
    if report.get("runner_error_type"):
        print("실행 오류 종류:", report["runner_error_type"])
    if report.get("interrupted"):
        raise SystemExit(130)
    if counts["all_match"] != len(cases) or report.get("runner_error_type"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
