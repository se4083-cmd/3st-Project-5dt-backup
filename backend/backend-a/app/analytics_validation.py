"""Validate supplied facts and ranking; never compute replacement VOC scores."""

from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.analytics_canonical import normalize, table_hashes
from app.analytics_schemas import KEYS, TABLES
from app.db import utcnow
from app.models import products, teams


def validate_submission(session, submission):
    m, p = submission.manifest, submission.payload
    errors = set()

    def check(ok, code):
        if not ok:
            errors.add(code)

    check(m.schema_version == "analytics-v1", "SCHEMA_VERSION")
    check(m.rule_version == "voc_rule_v1", "RULE_VERSION")
    check(m.generated_at <= utcnow() + timedelta(minutes=5), "FUTURE_WATERMARK")
    w = m.windows
    check(
        w.history_start <= w.operational_start < w.window_end <= m.source_as_of <= m.generated_at,
        "TIME_WINDOW",
    )
    check(
        w.sales_start == w.window_end - timedelta(days=28)
        and w.prior_start == w.window_end - timedelta(days=14)
        and w.recent_start == w.window_end - timedelta(days=7)
        and w.history_start <= w.sales_start,
        "RULE_WINDOWS",
    )
    check(w.window_end.astimezone(ZoneInfo("Asia/Seoul")).time().isoformat() == "00:00:00", "DAY_BOUNDARY")
    team_ids, product_ids = set(map(str, m.team_ids)), set(map(str, m.product_ids))
    check(len(team_ids) == len(m.team_ids) and len(product_ids) == len(m.product_ids), "MANIFEST_DUPLICATE")
    check(
        team_ids == set(session.scalars(select(teams.c.team_id).where(teams.c.team_id.in_(team_ids)))),
        "TEAM_FK",
    )
    check(
        product_ids
        == set(session.scalars(select(products.c.product_id).where(products.c.product_id.in_(product_ids)))),
        "PRODUCT_FK",
    )
    scopes = {s.scope_key: set(map(str, s.team_ids)) for s in m.scopes}
    check(len(scopes) == len(m.scopes), "SCOPE_DUPLICATE")
    check(len({tuple(sorted(v)) for v in scopes.values()}) == len(scopes), "SCOPE_SET_DUPLICATE")
    check(
        all(
            set(map(str, s.team_ids)) <= team_ids and len(set(s.team_ids)) == len(s.team_ids)
            for s in m.scopes
        ),
        "SCOPE_TEAMS",
    )
    raw = normalize(p)
    check(table_hashes(raw) == m.payload_checksums.model_dump(), "PAYLOAD_CHECKSUM")
    check({t: len(raw[t]) for t in TABLES} == m.row_counts.model_dump(), "ROW_COUNT")
    for table in TABLES:
        rows = raw[table]
        check(len({tuple(str(r[k]) for k in KEYS[table]) for r in rows}) == len(rows), "DUPLICATE_PK")
        for row in rows:
            if "product_id" in row:
                check(row["product_id"] in product_ids, "ROW_PRODUCT_FK")
            if "scope_key" in row:
                check(row["scope_key"] in scopes, "ROW_SCOPE_FK")
    start = w.operational_start.astimezone(ZoneInfo("Asia/Seoul")).date()
    end = w.window_end.astimezone(ZoneInfo("Asia/Seoul")).date()
    for row in p.analytics_daily:
        check(row.team_key in team_ids | {"AUTO"}, "DAILY_TEAM")
        check(start <= row.day < end, "DAILY_WINDOW")
        check(
            all(
                getattr(row, k) <= row.ticket_count
                for k in (
                    "auto_closed_count",
                    "handoff_count",
                    "sla_breach_count",
                    "duration_n",
                    "approval_count",
                    "review_count",
                )
            ),
            "DAILY_COUNTER",
        )
        check(row.duration_n > 0 or row.duration_sum_seconds == 0, "DURATION_DENOMINATOR")
    for row in p.analytics_product_daily:
        check(start <= row.day < end, "PRODUCT_DAILY_WINDOW")
        check(
            max(row.auto_count, row.handoff_count, row.return_refund_count) <= row.ticket_count,
            "PRODUCT_COUNTER",
        )
    trends = defaultdict(lambda: [0, 0])
    recent = w.recent_start.astimezone(ZoneInfo("Asia/Seoul")).date()
    for row in p.analytics_product_voc_daily:
        check(recent <= row.day < end, "TREND_WINDOW")
        check(row.unresolved_count <= row.episode_count, "TREND_COUNTER")
        key = (row.scope_key, str(row.product_id))
        trends[key][0] += row.episode_count
        trends[key][1] += row.unresolved_count
    check(
        {(r.scope_key, str(r.product_id)) for r in p.analytics_product_risk}
        == {(s, product) for s in scopes for product in product_ids},
        "RISK_COVERAGE",
    )
    ranked, sales = defaultdict(list), {}
    for r in p.analytics_product_risk:
        a = r.metrics
        for name, weight in (
            ("volume", 0.1),
            ("rate", 0.35),
            ("growth", 0.25),
            ("repeat", 0.2),
            ("unresolved", 0.1),
        ):
            component = getattr(r.components, name)
            check(abs(component.weight - weight) < 1e-12, "EXPLANATION_WEIGHT")
            # Arithmetic consistency of provided evidence only; normalized
            # factors are never derived from operating metrics here.
            check(
                abs(component.contribution - 100 * component.normalized * component.weight) < 1e-9,
                "EXPLANATION_COMPONENT",
            )
        check(
            r.rule_version == m.rule_version
            and r.source_as_of == m.source_as_of
            and r.window_end == w.window_end,
            "RISK_WATERMARK",
        )
        # N = distinct recent complaint orders in the paid sales cohort;
        # M = largest primary-issue episode count (not a subset of N).
        check(a.U <= a.C and a.M <= a.C and a.K <= a.C and a.N <= min(a.C, a.S), "METRIC_COUNTER")
        expected = (
            "DATA_MISSING"
            if not a.sales_complete
            else "QUALITY_BLOCKED"
            if not (a.quality_ok and a.complaints_complete and a.episode_state_complete)
            else "LOW_SAMPLE"
            if a.S < 30 or a.C < 5 or a.K < 3
            else "ELIGIBLE"
        )
        check(r.data_status == expected, "DATA_STATUS")
        check(trends[(r.scope_key, str(r.product_id))] == [a.C, a.U], "TREND_TOTAL")
        key = str(r.product_id)
        check(key not in sales or sales[key] == a.S, "GLOBAL_SALES_DENOMINATOR")
        sales[key] = a.S
        if r.data_status != "ELIGIBLE":
            check(r.score is None and r.rank is None and r.risk_band is None, "NONELIGIBLE_NULLS")
        else:
            check(r.score is not None and r.rank is not None and r.risk_band is not None, "ELIGIBLE_VALUES")
            if r.score is not None:
                check(
                    r.risk_band == ("HIGH" if r.score >= 60 else "WATCH" if r.score >= 40 else "NORMAL"),
                    "RISK_BAND",
                )
                # Compare supplied explanation, not the operational formula.
                check(
                    abs(float(r.score) - sum(c.contribution for c in r.components.__dict__.values()))
                    <= 0.0000011,
                    "EXPLANATION_TOTAL",
                )
            ranked[r.scope_key].append(r)
    for rows in ranked.values():
        rows.sort(key=lambda r: (-(r.score or 0), -r.metrics.C, str(r.product_id)))
        check([r.rank for r in rows] == list(range(1, len(rows) + 1)), "RANK_ORDER")
    return {
        "passed": not errors,
        "codes": sorted(errors),
        "validator_version": "analytics-v1",
        "origin_verified": False,
    }
