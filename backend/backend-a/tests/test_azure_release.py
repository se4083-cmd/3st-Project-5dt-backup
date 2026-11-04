import json
import zipfile

import pytest

from scripts import azure_release


def test_exact_git_package_and_compatible_recovery_no_credentials(tmp_path):
    sha = "2cb07cfc0bcbf1a203b6d54c5ebb1bb905a7be93"
    source = azure_release.package(tmp_path, sha)
    recovery = azure_release.package(tmp_path, sha, recovery=True)
    assert source["source_sha"] == recovery["source_sha"] == sha
    with zipfile.ZipFile(tmp_path / "recovery.zip") as z:
        names = z.namelist()
        assert all(
            n.startswith(("app/", "migrations/"))
            or n in {"requirements.txt", "pyproject.toml", "alembic.ini", "startup.sh"}
            for n in names
        )
        assert all(not n.endswith((".env", ".db", ".sqlite", ".json")) for n in names)
        main = z.read("app/main.py")
        assert b'!= "0011"' in main and b"0.10.0+recovery0011" in main
    changed = [n for n, v in source["files"].items() if recovery["files"][n] != v]
    assert changed == ["app/main.py"]
    assert json.loads((tmp_path / "release.zip.manifest.json").read_text())["source_sha"] == sha


def test_deploy_rejects_manifest_tampering_without_azure(tmp_path, monkeypatch):
    monkeypatch.setattr(azure_release, "WORK", tmp_path)
    (tmp_path / "release.zip").write_bytes(b"synthetic")
    (tmp_path / "release.zip.manifest.json").write_text(
        json.dumps({"source_sha": "test-sha", "package_sha256": "wrong"})
    )

    def forbidden(*args):
        pytest.fail("Azure must not be called on invalid artifact")

    monkeypatch.setattr(azure_release.cloud, "az", forbidden)
    with pytest.raises(AssertionError):
        azure_release.deploy("test-sha")


def test_recovery_app_is_ready_on_0011_without_downgrade(settings, monkeypatch, tmp_path):
    import os
    import subprocess
    import sys

    from tests.conftest import migrate

    migrate(settings, monkeypatch)
    azure_release.package(tmp_path, "2cb07cfc0bcbf1a203b6d54c5ebb1bb905a7be93", recovery=True)
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    with zipfile.ZipFile(tmp_path / "recovery.zip") as z:
        z.extractall(recovery)  # locally generated allowlisted archive, never user paths
    env = dict(
        os.environ,
        PYTHONPATH=str(recovery),
        DATABASE_URL=settings.database_url,
        JWT_SECRET=settings.jwt_secret,
        APP_ENV="test",
        CSFLOW_ENV_FILE=str(tmp_path / "absent.env"),
    )
    code = """
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient
with TestClient(create_app(get_settings())) as client:
    assert client.get('/health/ready').status_code == 200
    assert client.get('/openapi.json').json()['info']['version'] == '0.10.0+recovery0011'
    assert client.get('/api/v1/staff/workload').status_code == 401
print('RECOVERY_COMPATIBLE_WITH_0011')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=recovery, env=env, capture_output=True)
    assert result.returncode == 0, "Isolated recovery app failed; private process output suppressed"
    assert b"RECOVERY_COMPATIBLE_WITH_0011" in result.stdout


def test_valid_package_still_requires_verified_migration_backup(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setattr(azure_release, "WORK", tmp_path)
    content = b"synthetic local package"
    (tmp_path / "release.zip").write_bytes(content)
    (tmp_path / "release.zip.manifest.json").write_text(
        json.dumps({"source_sha": "local-sha", "package_sha256": hashlib.sha256(content).hexdigest()})
    )
    with pytest.raises(RuntimeError, match="VERIFIED_MIGRATION_AND_BACKUP_REQUIRED"):
        azure_release.deploy("local-sha")


def test_rowset_fingerprint_detects_change_even_with_same_count(app):
    from sqlalchemy import text

    with app.state.engine.begin() as c:
        before = azure_release.fingerprint(c, ["users"])
        c.execute(text("UPDATE users SET active=NOT active"))
        after = azure_release.fingerprint(c, ["users"])
        assert before["users"]["count"] == after["users"]["count"]
        assert before["users"]["rowset_md5"] != after["users"]["rowset_md5"]
