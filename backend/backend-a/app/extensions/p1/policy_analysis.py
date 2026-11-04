"""Deterministic text diff and verified historical references, never runtime prediction."""

from difflib import SequenceMatcher

from sqlalchemy import select

from app import repository, staff_detail
from app.analytics_canonical import digest
from app.db import utcnow
from app.models import ai_suggestions, automation_rules, knowledge_documents, tickets


def text_diff(before, after):
    old = before["body"] if before else ""
    left, right = old.splitlines(keepends=True), after["body"].splitlines(keepends=True)
    changes = [
        dict(operation=op, old_start=i, old_end=j, new_start=a, new_end=b, before=left[i:j], after=right[a:b])
        for op, i, j, a, b in SequenceMatcher(None, left, right, autojunk=True).get_opcodes()
        if op != "equal"
    ]
    return dict(
        kind="INITIAL_VERSION"
        if before is None
        else "CONTENT_CHANGED"
        if old != after["body"]
        else "METADATA_ONLY"
        if before["title"] != after["title"]
        else "NO_CHANGE",
        title_before=before["title"] if before else None,
        title_after=after["title"],
        body_changed=old != after["body"],
        changes=changes,
        from_hash=before["content_hash"] if before else None,
        to_hash=after["content_hash"],
    )


def impact(session, user, team_ids, before):
    now = utcnow()
    result = dict(
        as_of=now,
        source_validation="UNCONFIRMED",
        source_reason="NO_VERIFIED_BASE_SOURCE",
        scanned_count=0,
        truncated=False,
    )
    links = []
    faq = []
    rules = []
    source = None
    if before and before["source_document_id"]:
        source = (
            session.execute(
                select(knowledge_documents)
                .where(knowledge_documents.c.document_id == before["source_document_id"])
                .with_for_update(read=True)
            )
            .mappings()
            .first()
        )
        captured = before["source_snapshot"]
        if (
            not source
            or source["version"] != captured.get("version")
            or source["content_hash"] != captured.get("content_hash")
            or digest(source["body"].replace("\r\n", "\n").replace("\r", "\n")) != captured.get("body_hash")
            or source["policy_key"] != captured.get("policy_key")
        ):
            source = None
            result["source_reason"] = "BASE_SOURCE_CHANGED_OR_MISSING"
    if source:
        result.update(
            source_validation="VERIFIED_SNAPSHOT",
            source_reason="RECORDED_DOCUMENT_VERSION_HASH_AND_BODY_MATCH",
        )
        rows = list(
            session.execute(
                select(ai_suggestions)
                .join(tickets, ai_suggestions.c.ticket_id == tickets.c.ticket_id)
                .where(repository.ticket_scope(user), tickets.c.team_id.in_(team_ids))
                .order_by(ai_suggestions.c.suggestion_id)
                .limit(1001)
            ).mappings()
        )
        result.update(scanned_count=min(len(rows), 1000), truncated=len(rows) > 1000)
        for row in rows[:1000]:
            verified, state = staff_detail.evidence(session, row["evidence_refs"], now, row["category"])
            ref = next((r for r in verified if str(r.document_id) == source["document_id"]), None)
            if state != "VERIFIED_REFERENCES" or ref is None:
                continue
            link = dict(
                suggestion_id=row["suggestion_id"],
                document_id=source["document_id"],
                document_version=source["version"],
                source_active_at_analysis=ref.active_at_as_of,
                rule_id=None,
                rule_version=None,
                category=row["category"],
                origin=row["data_origin"],
                document_origin=source["data_origin"],
                relation="RECORDED_POLICY_CITATION",
            )
            links.append(link)
            if row["category"] == "FAQ":
                faq.append(link)
            rule = (
                session.execute(
                    select(automation_rules).where(
                        automation_rules.c.rule_id == row["rule_id"],
                        automation_rules.c.version == row["rule_version"],
                    )
                )
                .mappings()
                .first()
            )
            if rule:
                rules.append(
                    dict(
                        link,
                        rule_id=rule["rule_id"],
                        rule_version=rule["version"],
                        rule_origin=rule["data_origin"],
                        rule_active=rule["active"],
                        relation="RULE_CO_USED_WITH_POLICY_CITATION",
                    )
                )
    for name, items in [("faq", faq), ("auto_replies", links), ("automation_rules", rules)]:
        result[name] = dict(
            status="RECORDED_LINKS" if items else "UNCONFIRMED",
            reason="HISTORICAL_CO_USAGE_NOT_SEMANTIC_DEPENDENCY"
            if name == "automation_rules" and items
            else "HISTORICAL_CITATIONS_NOT_FUTURE_USAGE"
            if items
            else "NO_VERIFIED_SCOPED_LINKS",
            observed_reference_count=len(items),
            links=items,
        )
    return result
