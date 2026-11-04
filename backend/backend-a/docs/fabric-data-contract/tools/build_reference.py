"""Build documentation from the extracted local catalog; no DB/network access."""

import hashlib
import itertools
import json
import re
import secrets
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schema import metadata  # noqa: E402
from scripts.prepare_analytics_fixture import FIXTURE_TEAMS  # noqa: E402

OUT = ROOT / "docs/fabric-data-contract"


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    catalog = json.loads((OUT / "schema-catalog.json").read_text(encoding="utf-8"))
    columns = {}
    for c in catalog["columns"]:
        columns.setdefault(c["table_name"], []).append(c)
    keys = {}
    for c in catalog["constraints"]:
        if c["kind"] in ("p", "u", "f"):
            for field in c["columns"]:
                keys.setdefault((c["table_name"], field), set()).add(
                    {"p": "PK", "u": "UK", "f": "FK"}[c["kind"]]
                )
    erd = ["erDiagram"]
    for table, cols in columns.items():
        erd.append(f"    {table} {{")
        for c in cols:
            k = sorted(keys.get((table, c["column_name"]), set()))
            if k or c["column_name"] in (
                "status",
                "cycle_no",
                "version",
                "revision",
                "team_key",
                "scope_key",
            ):
                typ = re.sub(r"[^A-Za-z0-9_]", "_", c["pg_type"])
                erd.append(f"        {typ} {c['column_name']}" + (" " + ",".join(k) if k else ""))
        erd.append("    }")
    for fk in (x for x in catalog["constraints"] if x["kind"] == "f"):
        nullable = any(c["nullable"] for c in columns[fk["table_name"]] if c["column_name"] in fk["columns"])
        unique = any(
            x["table_name"] == fk["table_name"]
            and x["kind"] in ("p", "u")
            and set(x["columns"]) <= set(fk["columns"])
            for x in catalog["constraints"]
        )
        erd.append(
            f'    {fk["referenced_table"]} {"|o" if nullable else "||"}--{"o|" if unique else "o{"} {fk["table_name"]} : "{",".join(fk["columns"])}"'
        )
    write("erd.mmd", "\n".join(erd) + "\n")
    sections = [
        "# PostgreSQL 물리 스키마 — 구현 확인",
        "",
        "이 문서는 기존 migration을 새 로컬 PostgreSQL 16.15에 실제 적용한 카탈로그에서 생성했다. Azure DB 재조회 결과가 아니다. [DDL](schema.sql), [기계 판독 카탈로그](schema-catalog.json), [검증](schema-verification.json)을 함께 읽는다.",
        "",
        "## 테이블 이름과 관계",
        "",
        "요청한 products/customers/orders/tickets/audit_events/followup_actions/teams/users는 모두 public 안의 동일 이름 물리 테이블이다. 31개 업무·보조 테이블과 alembic_version 1개다. fixture의 customer_contacts/coverage/Silver/Gold 보조 5종과 inquiries/order_items 뷰는 A migration에 없다. [fixture 차이표](fixture-differences.md)를 따른다.",
        "",
        "아래 ERD는 전체 FK를 표시하며 주요 PK/FK/UK와 상태·회차만 보여준다. 복합 FK는 컬럼 묶음 하나이며 MATCH SIMPLE의 NULL 허용은 아래 본문을 우선한다. 부분 UNIQUE의 조건은 ERD 선만으로 표현하지 않으며 정확한 조건은 각 인덱스를 읽는다.",
        "",
        "```mermaid",
        *erd,
        "```",
        "",
        "## 고객·주문·상품·티켓의 NULL과 연결",
        "",
        "- customers.user_id는 NOT NULL + UNIQUE FK이므로 한 프로필은 한 사용자에 연결된다. DB는 사용자의 CUSTOMER 역할까지 FK로 검사하지 않으며 서비스가 확인한다.",
        "- orders.customer_id는 필수, product_id는 NULL 허용이다. 단일 제품 주문 구조이며 order_items 테이블은 없다.",
        "- tickets.customer_id는 필수, order_id/product_id/team_id는 NULL 허용이다. order_id가 있으면 product_id가 있어야 한다. (order_id,customer_id,product_id) 복합 FK가 orders의 같은 묶음을 참조하므로 주문·고객·상품 일치를 DB가 검사한다. order_id=NULL인 일반 문의는 product_id=NULL도 가능하다. product_id만 있으면 상품 FK는 적용되지만 주문 복합 FK는 MATCH SIMPLE로 건너뛴다.",
        "- team_id=NULL은 미귀속이며 전사 공개를 뜻하지 않는다. queue_routes와 배정은 별도 테이블이고 category만으로 귀속을 추정하지 않는다.",
        "- followup_actions는 ticket_id/product_id 중 정확히 하나다. 티켓 후속은 원래/책임 cycle 필수, 상품 후속은 두 cycle NULL이며 해결 blocker가 될 수 없다.",
        "",
        "## 시각·타입·기본값",
        "",
        "**구현 확인:** 모든 timestamp 컬럼은 timestamp with time zone(timestamptz)이다. app/db.py의 UTCDateTime은 naive 입력을 거부하고 aware 값을 UTC로 변환한다. API의 AwareDatetime 입력과 분석 모델도 UTC로 정규화한다. DB 연결은 timezone=UTC다. timestamptz는 원래 KST offset/지역명을 저장하는 타입이 아니므로 화면만 Asia/Seoul로 변환한다. 응답은 ISO8601 UTC(Z 또는 +00:00), date는 분석의 KST 달력 일자다. UTC 2026-10-30T15:00:00Z = KST 2026-10-31 00:00:00+09:00이고 분석 day 범위는 [start,end)다. [PostgreSQL 시각](https://www.postgresql.org/docs/16/datatype-datetime.html).",
        "",
        "**구현 확인:** DB DEFAULT와 SQLAlchemy client default는 별개다. 아래 `없음`은 raw SQL INSERT 때 자동 생성되지 않는다는 뜻이다. 대부분 UUID/created_at/updated_at/version/status/data_origin은 A Python이 채우며 DB 자동 updated_at trigger는 없다. PK UUID의 gen_random_uuid() 기본값도 없다. Export가 원본 UUID를 자체 생성하거나 default를 추측하면 안 된다.",
        "",
        "**구현 확인:** PostgreSQL native ENUM 타입은 0개다. 상태는 text/varchar + CHECK 또는 API Literal이다. CHECK가 없는 category/priority/order_status/payment_status/kind 등은 DB Enum으로 확정하지 않는다. API Category/Issue 제한은 분석 입력 모델에만 별도로 존재한다.",
        "",
        "## 전체 컬럼·제약·인덱스",
        "",
    ]
    primary = [
        "products",
        "customers",
        "orders",
        "tickets",
        "audit_events",
        "followup_actions",
        "teams",
        "users",
    ]
    for table in primary + sorted(set(columns) - set(primary)):
        sections += [
            f"### {table}",
            "",
            "| 컬럼 | PostgreSQL 정확한 타입 | NULL 허용 | DB DEFAULT | A client default | 키 |",
            "|---|---|---|---|---|---|",
        ]
        for c in columns[table]:
            col = metadata.tables[table].c[c["column_name"]] if table in metadata.tables else None
            default = "없음"
            if col is not None and col.default is not None:
                d = col.default.arg
                default = getattr(d, "__name__", "callable") + "()" if callable(d) else repr(d)
            sections.append(
                f"| `{c['column_name']}` | `{c['pg_type']}` | {'YES' if c['nullable'] else 'NO'} | {md(c['server_default'] or '없음')} | {md(default)} | {','.join(sorted(keys.get((table, c['column_name']), set())))} |"
            )
        for label, kind in [("PK", "p"), ("FK", "f"), ("UNIQUE", "u"), ("CHECK", "c")]:
            items = [x for x in catalog["constraints"] if x["table_name"] == table and x["kind"] == kind]
            if items:
                sections += ["", f"{label}:", ""] + [
                    f"- `{x['name']}`: `{md(x['definition'])}`" for x in items
                ]
        indexes = [x for x in catalog["indexes"] if x["table_name"] == table]
        if indexes:
            sections += ["", "인덱스(제약 backing index 포함):", ""] + [
                f"- `{md(x['definition'])}`" for x in indexes
            ]
        for x in catalog["triggers"]:
            if x["table_name"] == table:
                sections += ["", f"트리거: `{md(x['definition'])}`"]
        sections.append("")
    sections += [
        "## 트리거 함수",
        "",
        "분석 mart 4개 + head + receipt 불변 trigger 6개, control_history 불변 trigger 1개다. audit_events에는 모든 변경을 포착하는 CDC trigger가 없다. 아래 함수 전체와 schema.sql을 확인한다.",
        "",
    ]
    for f in catalog["functions"]:
        sections += [f"### {f['name']}", "", "```sql", f["definition"], "```", ""]
    sections += [
        "## Migration 적용 순서",
        "",
        "기존 파일을 수정하거나 새 migration을 추가하지 않았다. Alembic graph의 유일 head는 0006이다. schema.sql은 최종 head 상태의 schema-only pg_dump이며 migration 이력이나 seed/권한 설정 스크립트를 대체하지 않는다. alembic_version의 DDL은 포함하지만 행 데이터는 없으므로 이 DDL만으로 배포 revision이 stamp되지는 않는다.",
        "",
    ]
    for p in sorted((ROOT / "migrations/versions").glob("*.py")):
        if p.name.startswith("__"):
            continue
        sections.append(f"- [{p.stem}](../../migrations/versions/{p.name})")
    sections += [
        "",
        "```text",
        "base → 0001 → 0002 → 0003 → 0004 → 0005 → 0006 (head)",
        "```",
        "",
        "**팀 합의 필요:** 실제 Fabric 읽기 identity·allowlist view·네트워크·TLS·권한 부여는 별도 운영 절차다. 이 DDL은 로컬 소유자/권한을 배포 서버에 복제하지 않는다. Azure public schema owner와 앱 runtime 권한은 배포 문서의 과거 확인 사항이며 이번 작업에서는 재조회하지 않았다.",
    ]
    write("schema.md", "\n".join(sections) + "\n")
    fixture = json.loads((OUT / "fixture-schema-contract.original.json").read_text(encoding="utf-8-sig"))
    reviewed = json.loads((ROOT / "docs/fixture-schema-contract.json").read_text(encoding="utf-8-sig"))
    assert [t for t in fixture if t["primary_key"]] == reviewed
    aliases = {"timestamptz": "timestamp with time zone", "int": "integer", "float8": "double precision"}
    diff = [
        "# 기존 합성 schema_contract.json과 실제 A DB 차이",
        "",
        "**구현 확인:** 로컬 원본 reference/fixture/schema_contract.json은 27항목이며 [원본 메타데이터 사본](fixture-schema-contract.original.json)을 제공한다. 기존 docs/fixture-schema-contract.json은 그중 PK가 있는22항목만 뽑은 사본으로 내용이 같지만 전체 파일의 SHA256은 다르다. 입력 계약은 27항목: PK가 있는 fixture 22테이블 + PK가 없는 파생 5종이다. 실제 A는 이 fixture DDL을 실행하지 않고 자체 Alembic을 사용한다. 아래 비교는 실제 로컬 카탈로그 기준이다. fixture rows는 합성 파일의 건수 메타데이터이며 배포 A DB 건수가 아니다. 담당자가 언급한 5개 JSONL·12,008건은 이번에 파일/manifest를 받지 않아 검증 불가다.",
        "",
        "| fixture 항목 | A에만 추가된 컬럼 | fixture에만 있는 컬럼 | 공통 컬럼의 타입·NULL 차이 |",
        "|---|---|---|---|",
    ]
    differences = []
    for t in fixture:
        name = t["table"]
        actual = {x["column_name"]: x for x in columns.get(name, [])}
        provided = {x["name"]: x for x in t["fields"]}
        if not actual:
            diff.append(f"| {name} | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |")
            continue
        changed = []
        for field in actual.keys() & provided.keys():
            a, f = actual[field], provided[field]
            if (
                a["pg_type"].replace(", ", ",") != aliases.get(f["postgres_type"], f["postgres_type"])
                or a["nullable"] != f["nullable"]
            ):
                changed.append(
                    f"{field}: {f['postgres_type']}/NULL={f['nullable']} → {a['pg_type']}/NULL={a['nullable']}"
                )
        record = {
            "table": name,
            "a_only": sorted(actual.keys() - provided.keys()),
            "fixture_only": sorted(provided.keys() - actual.keys()),
            "changed": changed,
        }
        differences.append(record)
        diff.append(
            f"| {name} | {', '.join(record['a_only']) or 'なし'} | {', '.join(record['fixture_only']) or '없음'} | {'; '.join(changed) or '동일(타입 alias 정규화)'} |".replace(
                "なし", "없음"
            )
        )
    extra = sorted(set(columns) - {t["table"] for t in fixture})
    diff += [
        "",
        "A에만 있는 테이블: " + ", ".join(f"`{t}`" for t in extra),
        "",
        "추가 PK/FK/CHECK/부분 UNIQUE·인덱스·불변 trigger는 [schema.md](schema.md)의 전체 목록이 규범이다. fixture 타입 파일에는 그 대부분이 표현돼 있지 않다. fixture의 order FK는 (order_id,customer_id)인 반면 A는 product까지 묶는다. fixture SQL의 inquiries/order_items 뷰도 A에는 없다.",
        "",
        "**구현 확인:** fixture의 nested_json_encoded=true는 Spark 입력 JSONL에서 JSONB를 JSON 문자열로 한 번 더 인코딩하는 기존 관례다. DB의 JSONB 저장 타입과 Gold API의 중첩 JSON object를 문자열로 오해하면 안 된다. 신규 Export 제안은 typed nested JSON이며 기존 fixture와 다른 schema_version으로 합의해야 한다.",
        "",
        "**비교 불가 / 팀 합의 필요:** 주현님이 실제 적재한 Bronze/Silver 스키마·5개 JSONL의 필드/행 수/manifest/완전성 근거는 받지 않았다. 현재 문서의 27항목 및 배포32테이블과 동일하다고 주장하지 않는다. 해당 schema_contract.json, 파일별 counts/checksum, Bronze CREATE TABLE/printSchema 결과, 사용 Notebook 버전이 필요하다.",
    ]
    write("fixture-differences.md", "\n".join(diff) + "\n")
    write("fixture-differences.json", dump(differences))
    scope = []
    for n in range(1, 5):
        for names in itertools.combinations(FIXTURE_TEAMS, n):
            scope.append(
                {
                    "scope_key": "ALL4" if n == 4 else "+".join(names),
                    "team_ids": sorted(FIXTURE_TEAMS[k] for k in names),
                }
            )
    write(
        "samples/fixture-scope-map.json",
        dump(
            {
                "status": "IMPLEMENTED_FIXTURE_ADAPTER_ONLY_NOT_DEPLOYED_TEAM_INVENTORY",
                "teams": FIXTURE_TEAMS,
                "scopes": scope,
            }
        ),
    )
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=secrets.token_urlsafe(48),
        )
    )
    api = app.openapi()
    app.state.engine.dispose()
    paths = {
        p: v
        for p, v in api["paths"].items()
        if p.startswith("/api/v1/analytics/") or p.startswith("/api/v1/admin/analytics/")
    }
    needed = set()

    def refs(v):
        if isinstance(v, dict):
            if "$ref" in v and v["$ref"].startswith("#/components/schemas/"):
                needed.add(v["$ref"].split("/")[-1])
            for x in v.values():
                refs(x)
        elif isinstance(v, list):
            for x in v:
                refs(x)

    refs(paths)
    while True:
        old = len(needed)
        for k in list(needed):
            refs(api["components"]["schemas"][k])
        if len(needed) == old:
            break
    excerpt = {
        "openapi": api["openapi"],
        "info": api["info"],
        "paths": paths,
        "components": {
            "schemas": {k: api["components"]["schemas"][k] for k in sorted(needed)},
            "securitySchemes": api["components"]["securitySchemes"],
        },
    }
    write("openapi-analytics.json", dump(excerpt))
    source_files = sorted(
        set(
            [
                "README.md",
                "pyproject.toml",
                "alembic.ini",
                "docs/openapi.json",
                "docs/fabric-contract.md",
                "docs/fabric-handoff.md",
                "docs/fixture-schema-contract.json",
                "docs/phase4-analytics.md",
                "docs/azure-deployment.md",
                "docs/azure-migration.md",
            ]
            + [
                str(p.relative_to(ROOT)).replace("\\", "/")
                for d in ["app", "migrations", "scripts"]
                for p in (ROOT / d).rglob("*.py")
            ]
        )
    )
    basis = {
        "date_kst": "2026-11-03",
        "version": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        "head": catalog["migration_head"],
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "worktree_changed": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "deployed_database_rechecked": False,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files
        },
        "openapi_excerpt_paths": list(paths),
        "original_fixture_contract_sha256": hashlib.sha256(
            (OUT / "fixture-schema-contract.original.json").read_bytes()
        ).hexdigest(),
        "fixture_contract_entries": len(fixture),
        "reviewed_fixture_contract_entries": len(reviewed),
        "reviewed_22_entries_equal_original_subset": True,
    }
    write("source-basis.json", dump(basis))
    print(
        f"Built schema dictionary for {len(columns)} tables, full FK ERD, fixture diff and {len(paths)} OpenAPI paths; no DB/network access."
    )


if __name__ == "__main__":
    main()
