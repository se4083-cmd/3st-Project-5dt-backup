"""Read published facts from a single authenticated repeatable-read snapshot."""

from collections import Counter
from datetime import timedelta

from sqlalchemy import select

from app import models
from app.analytics_canonical import digest
from app.analytics_models import analytics_publication, analytics_receipts
from app.analytics_schemas import Daily, ProductDaily, Risk, VocDaily
from app.errors import APIError
from app.model_constraints import user_team_scopes


def resolve_snapshot(session, user, settings, team_ids=None, batch_id=None):
    if user["role"] != "ADMIN":
        raise APIError(403, "ADMIN_ROLE_REQUIRED", user["user_id"])
    allowed = set(
        session.scalars(
            select(user_team_scopes.c.team_id)
            .join(models.teams)
            .where(user_team_scopes.c.user_id == user["user_id"], models.teams.c.active.is_(True))
        )
    )
    selected = set(map(str, team_ids)) if team_ids is not None else allowed
    if not selected or not selected <= allowed:
        raise APIError(403, "ANALYTICS_TEAM_SCOPE_DENIED", user["user_id"])
    if team_ids is not None and len(selected) != len(team_ids):
        raise APIError(422, "DUPLICATE_TEAM_FILTER")
    current = session.scalar(
        select(analytics_publication.c.batch_id).where(analytics_publication.c.singleton_id == 1)
    )
    chosen = str(batch_id) if batch_id else current
    if not chosen:
        return {"availability": "UNAVAILABLE", "reason": "NO_PUBLISHED_BATCH", "meta": None}
    row = (
        session.execute(
            select(models.analytics_batches)
            .join(analytics_receipts)
            .where(
                models.analytics_batches.c.batch_id == chosen,
                models.analytics_batches.c.status == "SUCCEEDED",
                models.analytics_batches.c.validation_passed.is_(True),
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise APIError(404, "PUBLISHED_BATCH_NOT_FOUND", user["user_id"])
    manifest = row["manifest"]
    scope = next((s for s in manifest["scopes"] if set(s["team_ids"]) == selected), None)
    if not scope:
        return {"availability": "UNAVAILABLE", "reason": "SCOPE_NOT_PROVIDED", "meta": None}
    from datetime import datetime

    asof = datetime.fromisoformat(manifest["source_as_of"].replace("Z", "+00:00"))
    meta = {
        k: manifest[k]
        for k in ("batch_id", "schema_version", "rule_version", "source", "source_as_of", "generated_at")
    }
    meta.update(
        window_end=manifest["windows"]["window_end"],
        windows=manifest["windows"],
        published_at=row["published_at"],
        is_current=chosen == current,
        scope_key=scope["scope_key"],
        team_ids=sorted(selected),
        stale=session.info["snapshot_as_of"] - asof > timedelta(hours=settings.analytics_stale_hours),
        origin_verification="SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        cache_fingerprint=digest([user["user_id"], row["content_hash"], sorted(selected)]),
        sales_denominator_scope=manifest["sales_denominator_scope"],
    )
    return {
        "availability": "AVAILABLE",
        "reason": None,
        "meta": meta,
        "manifest": manifest,
        "batch_id": chosen,
        "scope_key": scope["scope_key"],
        "selected": selected,
    }


def envelope(snapshot, **data):
    return {k: snapshot[k] for k in ("availability", "reason", "meta")} | data


def scoped_risks(session, snapshot):
    t = models.analytics_product_risk
    return list(
        session.execute(
            select(t).where(t.c.batch_id == snapshot["batch_id"], t.c.scope_key == snapshot["scope_key"])
        ).mappings()
    )


def voc_list(session, snapshot, unavailable=False):
    if snapshot["availability"] != "AVAILABLE":
        return envelope(snapshot, items=[])
    rows = scoped_risks(session, snapshot)
    rows = (
        [r for r in rows if r["data_status"] != "ELIGIBLE"]
        if unavailable
        else sorted((r for r in rows if r["rank"] is not None and r["rank"] <= 10), key=lambda r: r["rank"])
    )
    return envelope(snapshot, items=[Risk.model_validate({k: r[k] for k in Risk.model_fields}) for r in rows])


def product_detail(session, snapshot, product_id):
    if snapshot["availability"] != "AVAILABLE":
        return envelope(snapshot, product=None)
    risk = next((r for r in scoped_risks(session, snapshot) if r["product_id"] == str(product_id)), None)
    if not risk:
        raise APIError(404, "ANALYTICS_PRODUCT_NOT_FOUND")
    t = models.analytics_product_voc_daily
    rows = session.execute(
        select(t)
        .where(
            t.c.batch_id == snapshot["batch_id"],
            t.c.scope_key == snapshot["scope_key"],
            t.c.product_id == str(product_id),
        )
        .order_by(t.c.day, t.c.primary_issue)
    ).mappings()
    trend = [VocDaily.model_validate({k: r[k] for k in VocDaily.model_fields}) for r in rows]
    all_teams = set(snapshot["manifest"]["team_ids"]) == snapshot["selected"]
    product_kpi = {
        "availability": "AVAILABLE" if all_teams else "UNAVAILABLE",
        "reason": None if all_teams else "PRODUCT_KPI_HAS_NO_TEAM_SCOPE",
        "grain": "day/product/category/issue_tag",
        "unique_ticket_totals": "UNAVAILABLE_TAG_ROWS_MAY_OVERLAP",
        "items": [],
    }
    if all_teams:
        t = models.analytics_product_daily
        rows = session.execute(
            select(t)
            .where(t.c.batch_id == snapshot["batch_id"], t.c.product_id == str(product_id))
            .order_by(t.c.day, t.c.category, t.c.issue_tag)
        ).mappings()
        product_kpi["items"] = [
            ProductDaily.model_validate({k: r[k] for k in ProductDaily.model_fields}) for r in rows
        ]
    return envelope(
        snapshot,
        product=Risk.model_validate({k: risk[k] for k in Risk.model_fields}),
        trend=trend,
        product_kpi=product_kpi,
        score_meaning="MANAGEMENT_PRIORITY_NOT_DEFECT_RATE_OR_CONFIRMED_DEFECT",
    )


def operational_kpi(session, snapshot):
    if snapshot["availability"] != "AVAILABLE":
        return envelope(snapshot, metrics=None)
    full = set(snapshot["manifest"]["team_ids"]) == snapshot["selected"]
    t = models.analytics_daily
    team_keys = snapshot["selected"] | ({"AUTO"} if full else set())
    rows = list(
        session.execute(
            select(t)
            .where(t.c.batch_id == snapshot["batch_id"], t.c.team_key.in_(team_keys))
            .order_by(t.c.day, t.c.team_key, t.c.category)
        ).mappings()
    )
    total = sum(r["ticket_count"] for r in rows)
    duration_sum, duration_n = (
        sum(r["duration_sum_seconds"] for r in rows),
        sum(r["duration_n"] for r in rows),
    )
    categories = Counter()
    for r in rows:
        categories[r["category"]] += r["ticket_count"]
    counts = {k: sum(r[k] for r in rows) for k in ("auto_closed_count", "handoff_count")}
    fixture = snapshot["manifest"]["kpi_definition"] == "fixture-ticket-v1"
    unsupported = {
        k: {
            "availability": "UNAVAILABLE",
            "reason": "FIXTURE_PLACEHOLDER_OR_PROXY" if fixture else "DEFINITION_NOT_AGREED",
        }
        for k in ("reopened", "approval", "review", "sla")
    }
    return envelope(
        snapshot,
        definition=snapshot["manifest"]["kpi_definition"],
        quality="SYNTHETIC_APPROXIMATION" if fixture else "UPSTREAM_DECLARED_COHORT",
        coverage="ALL_MANIFEST_TEAMS_INCLUDING_UNATTRIBUTED_AUTO" if full else "ATTRIBUTED_TEAM_ROWS_ONLY",
        grain="ticket_creation_cohort/day/team/category; not messages, cycles or VOC episodes",
        metrics={
            "ticket_count": total,
            "category_counts": dict(categories),
            **counts,
            "auto_closed_ratio": counts["auto_closed_count"] / total if total else None,
            "handoff_ratio": counts["handoff_count"] / total if total else None,
            "ratio_denominator": total,
            "duration_sum_seconds": duration_sum,
            "duration_n": duration_n,
            "mean_duration_seconds": duration_sum / duration_n if duration_n else None,
            **unsupported,
        },
        rows=[Daily.model_validate({k: r[k] for k in Daily.model_fields}) for r in rows],
    )
