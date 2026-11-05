"""Local PostgreSQL-only HTTP/browser validation; no Azure calls or deployment."""
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend/backend-a"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
base = os.environ["TEST_POSTGRES_URL"]
assert make_url(base).host in {"127.0.0.1", "localhost", "::1"}, "Local database only"
schema = "smoke_restore_" + uuid4().hex
admin = create_engine(base, hide_parameters=True)
processes = []
log = None
try:
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(base).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    os.environ.update(DATABASE_URL=url, JWT_SECRET=secrets.token_urlsafe(48), APP_ENV="test", CSFLOW_ENV_FILE="/tmp/csflow-no-env", CSFLOW_LOCAL_ONLY="1", P1_ENABLED="true", P1_VOC_ENABLED="true", P1_VOC_PROVIDER="MOCK", P1_VOC_AZURE_ENABLED="false", P1_POLICY_ENABLED="false", ANALYTICS_STALE_HOURS="720")
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    from app.config import get_settings
    from app.main import create_app
    from app.seed import seed_minimal, stable_id
    from app.models import teams
    from app.model_constraints import user_team_scopes
    from app.staff_models import staff_permissions
    from fastapi.testclient import TestClient
    from tests.p1.test_voc import evidence
    app = create_app(get_settings())
    password, empty_team = secrets.token_urlsafe(24), str(uuid4())
    with app.state.session_factory.begin() as s:
        seed_minimal(s, password)
        for cap in ["P1_VOC_READ", "P1_VOC_GENERATE", "P1_VOC_REVIEW", "P1_MONITOR_READ"]:
            s.execute(staff_permissions.insert().values(user_id=stable_id("admin"), permission=cap))
        s.execute(teams.insert().values(team_id=empty_team, name="합성 빈 분석 팀", supported_categories=[], active=True, data_origin="SYNTHETIC"))
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=empty_team))
    with TestClient(app) as client:
        evidence(client, app)
        if "--write-fixture" in sys.argv:
            login = client.post("/api/v1/auth/login", json={"login_name": "dev-admin@example.test", "password": password})
            h = {"Authorization": "Bearer " + login.json()["access_token"]}
            q = {"team_ids": stable_id("team")}
            products = client.get("/api/v1/admin/analytics/voc/top", headers=h, params=q)
            generated = client.post("/api/v1/admin/p1/voc-proposals", headers={**h, "Idempotency-Key": "synthetic-fixture-record"}, json={"product_id": stable_id("product"), "team_ids": [stable_id("team")]})
            assert generated.status_code == 201
            (ROOT / "frontend/src/test/voc-synthetic.json").write_text(json.dumps({"products": products.json(), "proposal": generated.json()}, ensure_ascii=False, indent=2) + "\n")
    app.state.engine.dispose()
    import httpx
    ports = []
    log = open("/tmp/csflow-voc-restore-server.log", "w")
    for flags in [{}, {"P1_VOC_ENABLED": "false"}, {"P1_VOC_PROVIDER": "AZURE_OPENAI", "P1_VOC_AZURE_ENABLED": "false"}]:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        env = {**os.environ, **flags}
        p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], env=env, stdout=log, stderr=log)
        processes.append(p)
        with httpx.Client(trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get(f"http://127.0.0.1:{port}/health/ready").status_code == 200: break
                except httpx.ConnectError: pass
                time.sleep(.1)
            else: raise RuntimeError("Local FastAPI startup timeout")
        ports.append(port)
    env = {**os.environ, "SMOKE_PASSWORD": password, "SMOKE_TEAM": stable_id("team"), "SMOKE_EMPTY_TEAM": empty_team, "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{ports[0]}", "SMOKE_DISABLED_URL": f"http://127.0.0.1:{ports[1]}", "SMOKE_BLOCKED_URL": f"http://127.0.0.1:{ports[2]}"}
    subprocess.run(["node", str(ROOT / "frontend/scripts/local-voc-smoke.mjs")], env=env, check=True, timeout=100)
finally:
    for p in processes:
        p.terminate()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5)
    if log: log.close()
    with admin.begin() as c: c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
