"""Local offline adapter. Copies supplied scores; does not run Fabric or scoring."""

import argparse
import itertools
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.analytics_canonical import canonical_submission, table_hashes
from app.analytics_schemas import TABLES, Submission

# Reviewed v4.1 fixture identities, independent of JSON array order or names.
FIXTURE_TEAMS = {
    "T1": "863e9dc3-6c9f-5e86-b3b7-f639a91dbdd2",
    "T2": "4a10ff03-d933-58aa-bfa2-e6c736275b70",
    "T3": "6efbae37-4e53-59e9-b68c-9711bef485b1",
    "T4": "6f797bdd-ec8f-5973-bb70-03d5a284d300",
}


def prepare(directory: Path):
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))

    config = read("config.json")
    original = read("data/analytics_batches.json")[0]
    source_teams = read("data/teams.json")
    teams = list(FIXTURE_TEAMS.values())
    if len(source_teams) != 4 or {r["team_id"] for r in source_teams} != set(teams):
        raise ValueError("Unreviewed fixture team mapping")
    products = [r["product_id"] for r in read("data/products.json")]
    coverage = {r["product_id"]: r for r in read("data/coverage.json")}
    payload = {}
    for table in TABLES:
        payload[table] = []
        for source in read("data/" + table + ".json"):
            row = {
                k: v
                for k, v in source.items()
                if k not in ("batch_id", "data_origin", "created_at", "updated_at")
            }
            if table == "analytics_product_risk":
                row["metrics"] = {
                    **row["metrics"],
                    **{
                        k: coverage[row["product_id"]][k]
                        for k in (
                            "sales_complete",
                            "quality_ok",
                            "complaints_complete",
                            "episode_state_complete",
                        )
                    },
                }
            payload[table].append(row)
    scopes = []
    for n in range(1, 5):
        for combo in itertools.combinations(range(4), n):
            scopes.append(
                {
                    "scope_key": "ALL4" if n == 4 else "+".join("T" + str(i + 1) for i in combo),
                    "team_ids": [teams[i] for i in combo],
                }
            )
    end = datetime.fromisoformat(config["window_end"].replace("Z", "+00:00"))
    windows = {
        k: (end - timedelta(days=d)).isoformat()
        for k, d in (("sales_start", 28), ("prior_start", 14), ("recent_start", 7))
    }
    windows.update(
        history_start=config["history_start"],
        operational_start=config["history_start"],
        window_end=config["window_end"],
    )
    manifest = {
        "batch_id": str(uuid5(NAMESPACE_URL, "csflow:local-publication:" + original["batch_id"])),
        "schema_version": "analytics-v1",
        "rule_version": "voc_rule_v1",
        "source": "LOCAL_SYNTHETIC",
        "source_as_of": config["source_as_of"],
        "generated_at": config["source_as_of"],
        "windows": windows,
        "team_ids": teams,
        "product_ids": products,
        "scopes": scopes,
        "row_counts": {t: len(payload[t]) for t in TABLES},
        "payload_checksums": {t: "0" * 64 for t in TABLES},
        "source_input_hashes": {k.removesuffix(".json"): v for k, v in original["checksums"].items()},
        "kpi_definition": "fixture-ticket-v1",
        "product_kpi_definition": "issue-tag-grain-v1",
        "sales_denominator_scope": "GLOBAL_PRODUCT_PAID_28D",
    }
    body = Submission.model_validate({"manifest": manifest, "payload": payload})
    value = canonical_submission(body)
    value["manifest"]["payload_checksums"] = table_hashes(value["payload"])
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(prepare(args.fixture_dir), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("LOCAL_SYNTHETIC payload prepared; no publication/network/Fabric execution")


if __name__ == "__main__":
    main()
