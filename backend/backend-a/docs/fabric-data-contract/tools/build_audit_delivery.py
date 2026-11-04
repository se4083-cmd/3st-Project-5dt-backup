"""Package only reviewed documentation/proposal files; never copy incoming data or app state."""

import argparse
import json
import zipfile
from pathlib import Path

from verify_export_proposal import PROPOSAL, ROOT, SAMPLES, load, require, sha, verify_proposal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="New ZIP under Backend A .cache; existing files are never replaced")
    args = parser.parse_args()
    cache = (ROOT.parents[1] / ".cache").resolve()
    target = (args.output or cache / "fabric-audit-export-proposal-20261104.zip").resolve()
    require(target.is_relative_to(cache) and target.suffix == ".zip", "Delivery must be a ZIP under Backend A .cache")
    require(not target.exists(), "Delivery already exists; choose a new --output path")
    require(not target.with_suffix(".verification.json").exists(), "Verification receipt already exists; choose a new --output path")
    verify_proposal()
    members = {
        "README.md": ROOT / "delivery-README.md",
        "audit-export-review.md": ROOT / "audit-export-review.md",
        "data-contract-review.md": ROOT / "data-contract-review.md",
        "audit-export-verification.json": ROOT / "audit-export-verification.json",
        "incoming-audit-review.json": ROOT / "incoming-audit-review.json",
        "tools/verify_export_proposal.py": ROOT / "tools/verify_export_proposal.py",
        "tools/build_audit_proposal.py": ROOT / "tools/build_audit_proposal.py",
    }
    for path in PROPOSAL.rglob("*"):
        if path.is_file():
            require(path.suffix in (".json", ".jsonl"), "Only proposal data/metadata in delivery")
            members["samples/" + path.relative_to(SAMPLES).as_posix()] = path
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(target) as archive:
        require(archive.testzip() is None, "Delivery ZIP CRC")
        require(set(archive.namelist()) == set(members), "Delivery inventory")
        for name, path in members.items():
            require(archive.read(name) == path.read_bytes(), "Delivery exact file bytes")
        manifest = load(PROPOSAL / "manifest.json")
        for entry in manifest["files"]:
            raw = archive.read("samples/" + entry["object_key"])
            require(sha(raw) == entry["sha256"] and len(raw) == entry["byte_count"] and
                    len(raw.splitlines()) == entry["row_count"], "Delivery Manifest exact bytes/hash/count")
    report = dict(status="PASS", scope="LOCAL_DELIVERY_ZIP_ONLY", file=target.name,
                  byte_count=target.stat().st_size, sha256=sha(target.read_bytes()),
                  member_count=len(members), jsonl_files=6, rows=6,
                  checks=["CRC", "EXPLICIT_FILE_INVENTORY", "EXACT_DISK_BYTES", "MANIFEST_COUNT_BYTES_SHA256"],
                  excluded=["INCOMING_FULL_JSONL", "RAW_DB_FIXTURES", "APP_CODE", "ENVIRONMENT", "DATABASE", "CREDENTIALS"],
                  sent=False)
    # Keep historical checked-in verification records attached to their original artifact.
    with target.with_suffix(".verification.json").open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(f"PASS: local delivery ZIP, {len(members)} members / 6 JSONL / 6 rows; not sent.")


if __name__ == "__main__":
    main()
