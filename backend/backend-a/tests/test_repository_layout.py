"""Relocation regression: module and Alembic roots do not depend on repository cwd."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.local_support import ROOT


def test_relocated_module_and_migration_paths(tmp_path, monkeypatch):
    backend_root = Path(__file__).resolve().parents[1]
    assert ROOT == backend_root
    monkeypatch.chdir(tmp_path)
    config = Config(str(backend_root / "alembic.ini"))
    assert Path(config.get_main_option("prepend_sys_path")).resolve() == backend_root
    migrations = ScriptDirectory.from_config(config)
    assert Path(migrations.dir).resolve() == backend_root / "migrations"
    assert migrations.get_heads() == ["0006"]
