"""Synthetic HTTP contracts, also executed against fresh local PG schemas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app import audit
from app.db import utcnow
from app.model_constraints import idempotency_keys, user_team_scopes
from app.models import followup_actions as actions
from app.models import products, tickets
from app.seed import stable_id
from app.staff_models import staff_permissions
from app.voc_models import plan_teams, plans, profiles, receipts, ticket_links
from tests.analytics_helpers import publish, rehash, small_batch, stage
from tests.conftest import login_as
from tests.phase3_helpers import change_state, create_followup, make_ticket, staff_user

URL = "/api/v1/staff/voc-improvements"
TEAM = stable_id("team")


def admin(client, app):
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.insert().values(user_id=stable_id("admin"), permission="VOC_IMPROVEMENT_MANAGE")
        )
    return login_as(client, "admin")


def plan(**changes):
    return {
        "issue_code": "DAMAGED",
        "improvement_text": "포장 보강 확인",
        "comparison_team_ids": [TEAM],
        "change_reason": "첫 계획",
        **changes,
    }


def body(**changes):
    return {
        "followup": {
            "product_id": stable_id("product"),
            "owner_team_id": TEAM,
            "owner_user_id": stable_id("admin"),
            "kind": "PRODUCT_IMPROVEMENT",
        },
        "plan": plan(),
        **changes,
    }


def post(client, h, data=None, *, path=URL, key="voc-create-0001"):
    return client.post(path, headers={**h, "Idempotency-Key": key}, json=data or body())


def create(client, h, **changes):
    r = post(client, h, body(**changes))
    assert r.status_code == 201, r.text
    return r.json()["action_id"]


def detail(client, h, aid):
    r = client.get(f"{URL}/{aid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def add_plan(client, h, aid, *, key="voc-plan-0001", ar=1, pr=1, **changes):
    return post(
        client,
        h,
        {**plan(**changes), "expected_action_revision": ar, "expected_plan_revision": pr},
        path=f"{URL}/{aid}/plans",
        key=key,
    )


def link(client, h, aid, tid, *, key="voc-link-0001", ar=1, pr=1):
    return post(
        client,
        h,
        {"ticket_id": tid, "expected_action_revision": ar, "expected_plan_revision": pr},
        path=f"{URL}/{aid}/tickets",
        key=key,
    )


@pytest.mark.parametrize("role", ["customer1", "agent", "admin"])
def test_role_and_explicit_capability(client, role):
    h = login_as(client, role)
    assert client.get(URL, headers=h).status_code == 403
    assert post(client, h).status_code == 403
    assert client.get(f"{URL}/{uuid4()}", headers=h).status_code == 403


def test_agent_grant_does_not_expand_product_role(client, app):
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.insert().values(user_id=stable_id("agent"), permission="VOC_IMPROVEMENT_MANAGE")
        )
    h = login_as(client, "agent")
    assert post(client, h).status_code == 403
    assert client.get(URL, headers=h).status_code == 403
    assert (
        "VOC_IMPROVEMENT_MANAGE"
        not in client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"]
    )


def test_create_replay_detail_no_duplicate_followup_receipt(client, app):
    h = admin(client, app)
    r = post(client, h)
    assert r.status_code == 201, r.text
    aid = r.json()["action_id"]
    replay = post(client, h)
    assert replay.status_code == 200 and replay.json() == r.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert post(client, h, body(plan=plan(improvement_text="다른 내용"))).status_code == 409
    d = detail(client, h, aid)
    assert d["followup"]["status"] == "OPEN" and d["followup"]["revision"] == 1
    assert d["current_plan"]["implemented_at"] is None and d["current_plan"]["before_start"] is None
    assert d["analysis"] == {
        "availability": "UNAVAILABLE",
        "reason": "EFFECT_INTEGRATION_NOT_IMPLEMENTED",
        "metrics": None,
    }
    assert len(d["plans"]) == 1 and d["tickets"] == []
    assert not any(k in str(d) for k in ["customer_id", "order_id", "message_body", "password"])
    assert (
        "VOC_IMPROVEMENT_MANAGE" in client.get("/api/v1/staff/capabilities", headers=h).json()["capabilities"]
    )
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(actions)) == 1
        assert s.scalar(select(func.count()).select_from(receipts)) == 1
        assert s.scalar(select(func.count()).select_from(idempotency_keys)) == 0
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.delete().where(user_team_scopes.c.user_id == stable_id("admin")))
    assert post(client, h).status_code == 404
    assert client.get(URL, headers=h).json()["items"] == []
    assert client.get(f"{URL}/{aid}", headers=h).status_code == 404


def test_existing_product_only_duplicate_and_scope(client, headers, app):
    h = admin(client, app)
    generic = create_followup(
        client, h, product_id=stable_id("product"), owner_user_id=stable_id("admin"), blocks_resolution=False
    ).json()["action_id"]
    assert client.get(URL, headers=h).json()["items"] == []
    data = {"existing_action_id": generic, "expected_action_revision": 1, "plan": plan()}
    assert post(client, h, data).status_code == 201
    assert post(client, h, data, key="voc-duplicate-0002").status_code == 409
    tid = make_ticket(client, headers, app)
    ta = create_followup(client, login_as(client, "agent"), tid, key="ticket-action-0002").json()["action_id"]
    assert post(client, h, {**data, "existing_action_id": ta}, key="voc-ticket-0003").status_code == 409
    staff_user(app, "voc-other", "ADMIN", stable_id("voc-team-other"))
    other = login_as(client, "voc-other")
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.insert().values(
                user_id=stable_id("voc-other"), permission="VOC_IMPROVEMENT_MANAGE"
            )
        )
    assert client.get(f"{URL}/{generic}", headers=other).status_code == 404
    assert client.get(URL, headers=other).json()["items"] == []
    assert post(client, other).status_code == 404


def test_product_owner_still_admin_only(client, app):
    h = admin(client, app)
    data = body()
    data["followup"]["owner_user_id"] = stable_id("agent")
    assert post(client, h, data).status_code == 409
    data["followup"]["owner_user_id"] = None
    r = post(client, h, data, key="voc-unclaimed-0002")
    assert r.status_code == 201
    aid = r.json()["action_id"]
    assert change_state(client, h, aid, "DONE").json()["error"]["code"] == "FOLLOWUP_TAKEOVER_REQUIRED"


@pytest.mark.parametrize("point", ["FOLLOWUP_CREATED", "VOC_IMPROVEMENT_CREATED", "receipt"])
def test_create_failure_rolls_back_everything(client, app, monkeypatch, point):
    from app import voc_improvements as service

    h = admin(client, app)
    original = audit.record

    def fail(s, actor, action, *args, **kw):
        if action == point:
            raise RuntimeError("synthetic audit failure")
        return original(s, actor, action, *args, **kw)

    monkeypatch.setattr(audit, "record", fail)
    if point == "receipt":

        def bad(*args, **kw):
            raise RuntimeError("synthetic receipt failure")

        monkeypatch.setattr(service, "save_receipt", bad)
    assert post(client, h).status_code == 500
    with app.state.session_factory() as s:
        for t in [actions, profiles, plans, plan_teams, receipts]:
            assert s.scalar(select(func.count()).select_from(t)) == 0


def windows():
    at = utcnow() - timedelta(days=2)
    return {
        k: v.isoformat()
        for k, v in {
            "implemented_at": at,
            "before_start": at - timedelta(days=14),
            "before_end": at,
            "after_start": at,
            "after_end": at + timedelta(days=14),
        }.items()
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"implemented_at": "2099-01-01T00:00:00Z"},
        {"before_start": None},
        {"implemented_at": None},
        {"before_start": "2020-01-01T00:00:00Z"},
        {"after_start": "2020-01-01T00:00:00Z"},
        {"implemented_at": "2020-01-01T00:00:00"},
        {"before_end": "2020-01-01T00:00:00Z"},
        {"comparison_team_ids": [TEAM, TEAM]},
        {"improvement_text": " "},
    ],
)
def test_window_validation(client, app, bad):
    h = admin(client, app)
    assert post(client, h, body(plan=plan(**{**windows(), **bad}))).status_code == 422


def test_utc_boundaries_append_revision_replay_and_terminal_correction(client, app):
    h = admin(client, app)
    aid = create(client, h)
    win = windows()
    r = add_plan(client, h, aid, **win)
    assert r.status_code == 201, r.text
    assert add_plan(client, h, aid, **win).json() == r.json()
    assert add_plan(client, h, aid, key="voc-stale-0002", **win).status_code == 409
    assert add_plan(client, h, aid, key="voc-stale-action", ar=2, pr=2, **win).status_code == 409
    d = detail(client, h, aid)
    assert [p["revision"] for p in d["plans"]] == [2, 1]
    assert d["plans"][1]["implemented_at"] is None
    assert d["followup"]["revision"] == 1
    assert change_state(client, h, aid, "DONE").status_code == 200
    assert add_plan(client, h, aid, key="voc-terminal-0003", ar=2, pr=2, **win).status_code == 409
    corrected = {
        **win,
        "implemented_at": win["before_end"],
        "change_reason": "시행 사실 재확인",
        "correction": True,
    }
    r = add_plan(client, h, aid, key="voc-correct-0004", ar=2, pr=2, **corrected)
    assert r.status_code == 201, r.text
    d = detail(client, h, aid)
    assert d["followup"]["status"] == "DONE" and d["followup"]["revision"] == 2
    assert d["current_plan"]["change_kind"] == "CORRECTION"
    assert (
        add_plan(
            client, h, aid, key="voc-correct-bad", ar=2, pr=3, improvement_text="업무 내용 변경", **corrected
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/staff/followups/{aid}", headers=h, json={"expected_revision": 2, "kind": "CHANGED"}
        ).status_code
        == 409
    )


def test_ticket_link_product_scope_and_replay_current_access(client, headers, app):
    h = admin(client, app)
    aid = create(client, h)
    tid = make_ticket(client, headers, app)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(product_id=None))
    assert link(client, h, aid, tid).status_code == 409
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(product_id=stable_id("product")))
    first = link(client, h, aid, tid)
    assert first.status_code == 201, first.text
    assert link(client, h, aid, tid).json() == first.json()
    assert link(client, h, aid, tid, key="voc-link-new-key").status_code == 201
    assert len(detail(client, h, aid)["tickets"]) == 1
    other_team = stable_id("voc-ticket-other-team")
    staff_user(app, "other-voc-agent", team_id=other_team)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(team_id=other_team))
    assert link(client, h, aid, tid).status_code == 404
    assert detail(client, h, aid)["tickets"] == []
    assert link(client, h, aid, str(uuid4()), key="voc-missing-ticket").status_code == 404


def test_source_published_exact_scope_and_owner_change_history_access(client, app):
    h = admin(client, app)
    staged, _ = stage(client, app)
    src = {"source_batch_id": staged["manifest"]["batch_id"], "source_scope_key": "T1"}
    assert post(client, h, body(plan=plan(**src))).status_code == 404
    published, _ = publish(client, app)
    src["source_batch_id"] = published["manifest"]["batch_id"]
    assert post(client, h, body(plan=plan(**{**src, "source_scope_key": "NO_SUCH_SCOPE"}))).status_code == 422
    aid = create(client, h, plan=plan(**src))
    # Superseding the source publication does not invalidate the pinned reference.
    newer = small_batch()
    newer["manifest"]["source_as_of"] = "2026-11-01T03:00:00Z"
    newer["manifest"]["generated_at"] = "2026-11-01T03:00:00Z"
    for row in newer["payload"]["analytics_product_risk"]:
        row["source_as_of"] = newer["manifest"]["source_as_of"]
    publish(client, app, rehash(newer))
    assert detail(client, h, aid)["current_plan"]["source_batch_id"] == src["source_batch_id"]
    t2 = stable_id("voc-team-move")
    staff_user(app, "voc-admin-move", "ADMIN", t2)
    with app.state.session_factory.begin() as s:
        s.execute(user_team_scopes.insert().values(user_id=stable_id("admin"), team_id=t2))
    r = client.patch(
        f"/api/v1/staff/followups/{aid}",
        headers=h,
        json={"expected_revision": 1, "owner_team_id": t2, "owner_user_id": stable_id("voc-admin-move")},
    )
    assert r.status_code == 200, r.text
    assert detail(client, h, aid)["plan_refresh_required"]
    with app.state.session_factory.begin() as s:
        s.execute(
            user_team_scopes.delete().where(
                user_team_scopes.c.user_id == stable_id("admin"), user_team_scopes.c.team_id == TEAM
            )
        )
    d = detail(client, h, aid)
    assert d["current_plan"] is None and d["plans"] == [] and d["plan_access"] == "COMPARISON_SCOPE_DENIED"
    assert src["source_batch_id"] not in str(d)
    assert add_plan(client, h, aid, ar=2, comparison_team_ids=[t2]).status_code == 201
    assert not detail(client, h, aid)["plan_refresh_required"]


def test_stable_pages_and_empty_scope(client, app):
    h = admin(client, app)
    ids = []
    for n in range(3):
        r = post(client, h, key=f"voc-page-create-{n}")
        assert r.status_code == 201
        ids.append(r.json()["action_id"])
    seen, cursor = [], None
    for n in range(3):
        r = client.get(URL, headers=h, params={"limit": 1, **({"cursor": cursor} if cursor else {})}).json()
        seen.extend(x["action_id"] for x in r["items"])
        cursor = r["next_cursor"]
    assert len(set(seen)) == 3 and set(seen) == set(ids) and cursor is None
    assert client.get(URL, headers=h, params={"limit": 101}).status_code == 422
    assert client.get(URL, headers=h, params={"product_id": str(uuid4())}).json()["items"] == []
    aid = ids[0]
    for rev in range(1, 4):
        assert add_plan(client, h, aid, key=f"voc-history-{rev}", pr=rev).status_code == 201
    first = client.get(f"{URL}/{aid}?plan_limit=2", headers=h).json()
    second = client.get(
        f"{URL}/{aid}?plan_limit=2&plan_before_revision={first['next_plan_before_revision']}", headers=h
    ).json()
    assert [x["revision"] for x in first["plans"] + second["plans"]] == [4, 3, 2, 1]


@pytest.mark.postgres
def test_postgres_immutable_history_and_parallel_revisions(client, app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PG locks/triggers")
    h = admin(client, app)
    aid = create(client, h)
    second_id = staff_user(app, "voc-concurrent-admin", "ADMIN")
    with app.state.session_factory.begin() as s:
        s.execute(staff_permissions.insert().values(user_id=second_id, permission="VOC_IMPROVEMENT_MANAGE"))
    second = login_as(client, "voc-concurrent-admin")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda n: add_plan(client, [h, second][n], aid, key=f"voc-concurrent-{n}"), range(2))
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(lambda _: post(client, h, key="voc-same-create"), range(2)))
    assert sorted(r.status_code for r in same) == [200, 201]
    assert same[0].json() == same[1].json()
    other_team = stable_id("voc-history-extra-team")
    staff_user(app, "voc-history-extra-admin", "ADMIN", other_team)
    with app.state.session_factory.begin() as s:
        for table in (plans, plan_teams, receipts):
            with pytest.raises(DBAPIError), s.begin_nested():
                s.execute(table.delete())
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(plans.update().values(improvement_text="overwrite"))
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(actions.update().where(actions.c.action_id == aid).values(product_id=None))
        with pytest.raises(DBAPIError, match="VOC_HISTORY_IMMUTABLE"), s.begin_nested():
            s.execute(plan_teams.insert().values(action_id=aid, revision=1, team_id=other_team))


@pytest.mark.parametrize("operation", ["PLAN", "LINK"])
def test_command_audit_failure_no_partial_plan_link_or_receipt(client, headers, app, monkeypatch, operation):
    h = admin(client, app)
    aid = create(client, h)
    tid = make_ticket(client, headers, app)
    with app.state.session_factory.begin() as s:
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(product_id=stable_id("product")))
    original = audit.record

    def fail(session, actor, event, *args, **kw):
        if event == ("VOC_PLAN_ADDED" if operation == "PLAN" else "VOC_TICKET_LINKED"):
            raise RuntimeError("synthetic write failure")
        return original(session, actor, event, *args, **kw)

    monkeypatch.setattr(audit, "record", fail)
    r = add_plan(client, h, aid) if operation == "PLAN" else link(client, h, aid, tid)
    assert r.status_code == 500
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(plans)) == 1
        assert s.scalar(select(profiles.c.current_plan_revision)) == 1
        assert s.scalar(select(func.count()).select_from(ticket_links)) == 0
        assert s.scalar(select(func.count()).select_from(receipts)) == 1


def test_wrong_product_and_revoked_capability(client, headers, app):
    h = admin(client, app)
    aid = create(client, h)
    tid = make_ticket(client, headers, app)
    with app.state.session_factory.begin() as s:
        p = dict(s.execute(select(products)).mappings().first())
        p["product_id"] = str(uuid4())
        if "sku" in p:
            p["sku"] = "VOC-OTHER-PRODUCT"
        s.execute(products.insert().values(**p))
        s.execute(tickets.update().where(tickets.c.ticket_id == tid).values(product_id=p["product_id"]))
    assert link(client, h, aid, tid).status_code == 409
    assert detail(client, h, aid)["tickets"] == []
    with app.state.session_factory.begin() as s:
        s.execute(
            staff_permissions.delete().where(
                staff_permissions.c.user_id == stable_id("admin"),
                staff_permissions.c.permission == "VOC_IMPROVEMENT_MANAGE",
            )
        )
    assert post(client, h).status_code == 403
    assert add_plan(client, h, aid).status_code == 403


def test_equivalent_utc_offsets_and_empty_correction_reason(client, app):
    from datetime import timezone

    h = admin(client, app)
    values = windows()
    from datetime import datetime

    values["before_end"] = (
        datetime.fromisoformat(values["before_end"]).astimezone(timezone(timedelta(hours=9))).isoformat()
    )
    aid = create(client, h, plan=plan(**values))
    d = detail(client, h, aid)
    assert d["current_plan"]["before_end"] == d["current_plan"]["implemented_at"]
    assert change_state(client, h, aid, "DONE").status_code == 200
    assert add_plan(client, h, aid, ar=2, correction=True, change_reason=" ", **values).status_code == 422
