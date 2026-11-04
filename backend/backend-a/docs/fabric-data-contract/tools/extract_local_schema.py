"""Documentation-only: migrate a NEW loopback cluster and extract schema, never rows.

Run from backend/backend-a. No existing DB/URL, Azure state or credentials accepted.
The only removed directory is the tempfile created and owner-marked by this run.
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.local_support import HIDDEN, free_port, local_environment  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True, type=Path)
    parser.add_argument("--verify-samples", action="store_true")
    args = parser.parse_args()
    pg_bin = args.pg_bin.resolve(strict=True)
    output = ROOT / "docs/fabric-data-contract"
    work = ROOT / ".cache/fabric-contract-check"
    work.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="csflow-schema-docs-")).resolve()
    marker = secrets.token_hex(24)
    (temporary / "owner").write_text(marker)
    port = free_port()
    env = local_environment(
        APP_ENV="test",
        DATABASE_URL=f"postgresql+psycopg://schema_docs@127.0.0.1:{port}/postgres?sslmode=disable",
        JWT_SECRET=secrets.token_urlsafe(48),
    )
    started = False

    def run(name, *argv):
        exe = pg_bin / (name + (".exe" if os.name == "nt" else ""))
        if name == "pg_ctl":
            # A background postgres must not inherit capture pipes (Windows).
            with (work / "pg-control.log").open("ab") as log:
                result = subprocess.run(
                    [str(exe), *map(str, argv)], env=env, stdout=log, stderr=log, creationflags=HIDDEN
                )
            if result.returncode:
                raise RuntimeError("LOCAL_SCHEMA_CONTROL_FAILED")
            return b""
        result = subprocess.run(
            [str(exe), *map(str, argv)], env=env, capture_output=True, creationflags=HIDDEN
        )
        if result.returncode:
            (work / "local-command-error.log").write_bytes(result.stderr)
            raise RuntimeError("LOCAL_SCHEMA_COMMAND_FAILED: " + name)
        return result.stdout

    try:
        run(
            "initdb",
            "-D",
            temporary / "data",
            "-U",
            "schema_docs",
            "--auth-local=trust",
            "--auth-host=trust",
            "--encoding=UTF8",
            "--locale=C",
        )
        with (temporary / "data/postgresql.conf").open("a") as f:
            f.write("\nlisten_addresses='127.0.0.1'\ntimezone='UTC'\nlog_statement=none\n")
        run(
            "pg_ctl",
            "-D",
            temporary / "data",
            "-l",
            temporary / "postgres.log",
            "-o",
            f"-p {port} -h 127.0.0.1",
            "-w",
            "start",
        )
        started = True
        # Isolated child process: no inherited application/cloud/PG credentials.
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            creationflags=HIDDEN,
        )
        (work / "migration.log").write_bytes(migrated.stdout + migrated.stderr)
        if migrated.returncode:
            raise RuntimeError("LOCAL_SCHEMA_MIGRATION_FAILED")
        checked = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            creationflags=HIDDEN,
        )
        (work / "model-check.log").write_bytes(checked.stdout + checked.stderr)
        if checked.returncode:
            raise RuntimeError("LOCAL_SCHEMA_MODEL_CHECK_FAILED")
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(
            host="127.0.0.1",
            port=port,
            dbname="postgres",
            user="schema_docs",
            sslmode="disable",
            row_factory=dict_row,
        ) as c:
            c.execute("SET TRANSACTION READ ONLY")
            version = c.execute("SHOW server_version").fetchone()["server_version"]
            catalog = {
                "basis": "NEW_LOCAL_POSTGRESQL_MIGRATIONS_0001_TO_HEAD_NO_SEED",
                "server_version": version,
                "migration_head": c.execute("SELECT version_num FROM alembic_version").fetchone()[
                    "version_num"
                ],
                "deployed_database_rechecked": False,
                "columns": c.execute("""SELECT cl.relname AS table_name, a.attname AS column_name,
                  a.attnum AS ordinal, format_type(a.atttypid,a.atttypmod) AS pg_type,
                  NOT a.attnotnull AS nullable, pg_get_expr(d.adbin,d.adrelid) AS server_default
                  FROM pg_class cl JOIN pg_namespace n ON n.oid=cl.relnamespace
                  JOIN pg_attribute a ON a.attrelid=cl.oid AND a.attnum>0 AND NOT a.attisdropped
                  LEFT JOIN pg_attrdef d ON d.adrelid=cl.oid AND d.adnum=a.attnum
                  WHERE n.nspname='public' AND cl.relkind='r' ORDER BY cl.relname,a.attnum""").fetchall(),
                "constraints": c.execute("""SELECT cl.relname AS table_name, con.conname AS name,
                  con.contype AS kind, con.convalidated AS validated,
                  pg_get_constraintdef(con.oid,true) AS definition,
                  ARRAY(SELECT attname FROM unnest(con.conkey) WITH ORDINALITY k(num,ord)
                    JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.num ORDER BY k.ord) AS columns,
                  parent.relname AS referenced_table,
                  ARRAY(SELECT attname FROM unnest(con.confkey) WITH ORDINALITY k(num,ord)
                    JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=k.num ORDER BY k.ord) AS referenced_columns
                  FROM pg_constraint con JOIN pg_class cl ON cl.oid=con.conrelid
                  JOIN pg_namespace n ON n.oid=cl.relnamespace
                  LEFT JOIN pg_class parent ON parent.oid=con.confrelid
                  WHERE n.nspname='public' ORDER BY cl.relname,con.conname""").fetchall(),
                "indexes": c.execute(
                    "SELECT tablename AS table_name,indexname AS name,indexdef AS definition FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname"
                ).fetchall(),
                "triggers": c.execute("""SELECT cl.relname AS table_name,t.tgname AS name,
                  pg_get_triggerdef(t.oid,true) AS definition FROM pg_trigger t
                  JOIN pg_class cl ON cl.oid=t.tgrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
                  WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY cl.relname,t.tgname""").fetchall(),
                "functions": c.execute("""SELECT p.proname AS name,pg_get_functiondef(p.oid) AS definition
                  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                  WHERE n.nspname='public' AND p.prokind='f' ORDER BY p.proname""").fetchall(),
                "native_enums": c.execute("""SELECT t.typname,e.enumlabel,e.enumsortorder FROM pg_type t
                  JOIN pg_enum e ON e.enumtypid=t.oid JOIN pg_namespace n ON n.oid=t.typnamespace
                  WHERE n.nspname='public' ORDER BY t.typname,e.enumsortorder""").fetchall(),
                "sequences": c.execute(
                    "SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"
                ).fetchall(),
            }
        dump = run(
            "pg_dump",
            "-h",
            "127.0.0.1",
            "-p",
            port,
            "-U",
            "schema_docs",
            "-d",
            "postgres",
            "--schema-only",
            "--schema=public",
            "--no-owner",
            "--no-privileges",
        )
        header = (
            f"-- Documentation extraction: NEW isolated local PostgreSQL {version}\n"
            "-- Applied existing migrations 0001 through head; no seed; schema only, no rows.\n"
            "-- Azure deployment DB was NOT queried in this documentation task.\n"
            "-- Owners/grants/environment-specific settings are intentionally not portable DDL.\n"
        )
        (output / "schema.sql").write_bytes(header.encode() + dump.replace(b"\r\n", b"\n"))
        (output / "schema-catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = {
            "result": "PASS",
            "server_version": version,
            "migration_head": catalog["migration_head"],
            "alembic_model_check": "PASS",
            "tables": len({r["table_name"] for r in catalog["columns"]}),
            "constraints": len(catalog["constraints"]),
            "indexes": len(catalog["indexes"]),
            "triggers": len(catalog["triggers"]),
            "native_enum_types": len(catalog["native_enums"]),
            "schema_sha256": hashlib.sha256((output / "schema.sql").read_bytes()).hexdigest(),
            "existing_services_changed": False,
            "azure_accessed": False,
        }
        (output / "schema-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if args.verify_samples:
            result = subprocess.run(
                [sys.executable, str(output / "tools/verify_samples.py"), "--local-database"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                creationflags=HIDDEN,
            )
            (work / "sample-check.log").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("SYNTHETIC_DOCUMENTATION_SAMPLE_CHECK_FAILED")
            print(result.stdout.decode("utf-8"))
        print(json.dumps(report))
    finally:
        if started:
            run("pg_ctl", "-D", temporary / "data", "-m", "fast", "-w", "stop")
        # Resolve and verify this run's exact tempfile before recursive deletion.
        assert temporary.parent == Path(tempfile.gettempdir()).resolve()
        assert temporary.name.startswith("csflow-schema-docs-")
        assert (temporary / "owner").read_text() == marker
        shutil.rmtree(temporary)
        print("Created documentation-only local cluster stopped/removed; existing DB/API untouched.")


if __name__ == "__main__":
    main()
