"""Explicit worker-supplied references only; never infer latest suggestions/policies."""

import hashlib

from pydantic import ValidationError
from sqlalchemy import select

from app.models import ai_suggestions, approvals, knowledge_documents, messages
from app.quality_models import evidence, reply_records
from app.quality_schemas import ReplyProvenance
from app.resolution import WorkRejected


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ref(session, table, column, value):
    return (
        session.execute(select(table).where(column == str(value)).with_for_update(read=True))
        .mappings()
        .first()
    )


def prepare(session, command, ticket, job, now):
    p = command.provenance or ReplyProvenance()
    values = {
        "source_message_id": None,
        "question_sha256": None,
        "suggestion_id": None,
        "suggestion_revision": None,
        "suggestion_content_hash": None,
        "approval_id": None,
        "approval_reviewer_id": None,
        "model_version": p.model_version,
        "prompt_version": p.prompt_version,
        "retrieval_ref": p.retrieval_ref,
    }
    origins = [ticket["data_origin"]]
    valid_until = []
    suggestion_evidence_complete = False
    if p.source_message_id:
        q = ref(session, messages, messages.c.message_id, p.source_message_id)
        if (
            not q
            or q["ticket_id"] != ticket["ticket_id"]
            or q["cycle_no"] != command.cycle_no
            or q["direction"] != "IN"
            or q["visibility"] != "PUBLIC"
            or q["created_at"] > now
            or (job["source_message_id"] and job["source_message_id"] != str(p.source_message_id))
        ):
            raise WorkRejected("PROVENANCE_QUESTION_MISMATCH")
        values.update(source_message_id=q["message_id"], question_sha256=sha(q["body"]))
        origins.append(q["data_origin"])
    if p.suggestion_id:
        s = ref(session, ai_suggestions, ai_suggestions.c.suggestion_id, p.suggestion_id)
        if (
            not s
            or s["ticket_id"] != ticket["ticket_id"]
            or s["cycle_no"] != command.cycle_no
            or s["revision"] != p.suggestion_revision
            or s["content_hash"] != p.suggestion_content_hash
            or s["draft"] != command.message
            or s["created_at"] > now
        ):
            raise WorkRejected("PROVENANCE_SUGGESTION_MISMATCH")
        for field in ("model_version", "prompt_version"):
            if getattr(p, field) is not None and getattr(p, field) != s[field]:
                raise WorkRejected("PROVENANCE_VERSION_MISMATCH")
            # Parse the actual explicitly linked versions through the same closed input schema.
            try:
                values[field] = getattr(ReplyProvenance(**{field: s[field]}), field)
            except ValidationError:
                raise WorkRejected("PROVENANCE_VERSION_MISMATCH") from None
        values.update(
            suggestion_id=s["suggestion_id"],
            suggestion_revision=s["revision"],
            suggestion_content_hash=s["content_hash"],
        )
        origins.append(s["data_origin"])
        if p.evidence:
            stored = s["evidence_refs"]
            if not isinstance(stored, list) or any(
                not any(
                    isinstance(x, dict)
                    and all(
                        x.get(k) == value
                        for k, value in {
                            "document_id": str(e.document_id),
                            "version": e.version,
                            "content_hash": e.content_hash,
                            "chunk_ref": e.chunk_ref,
                        }.items()
                    )
                    for x in stored
                )
                for e in p.evidence
            ):
                raise WorkRejected("PROVENANCE_SUGGESTION_EVIDENCE_MISMATCH")
            suggestion_evidence_complete = len(p.evidence) == len(stored)
        if p.approval_id:
            a = ref(session, approvals, approvals.c.approval_id, p.approval_id)
            if (
                not a
                or a["ticket_id"] != ticket["ticket_id"]
                or a["cycle_no"] != command.cycle_no
                or a["ticket_version"] != command.expected_revision
                or a["suggestion_id"] != s["suggestion_id"]
                or a["content_hash"] != s["content_hash"]
                or a["decision"] != "APPROVED"
                or a["reviewed_at"] > now
                or a["expires_at"] <= now
            ):
                raise WorkRejected("PROVENANCE_APPROVAL_MISMATCH")
            values.update(approval_id=a["approval_id"], approval_reviewer_id=a["reviewer_id"])
            origins.append(a["data_origin"])
            valid_until.append(a["expires_at"])
    refs = []
    for i, e in enumerate(p.evidence, 1):
        d = ref(session, knowledge_documents, knowledge_documents.c.document_id, e.document_id)
        if (
            not d
            or d["version"] != e.version
            or d["content_hash"] != e.content_hash
            or d["effective_from"] > now
            or (d["effective_to"] and d["effective_to"] <= now)
            or not d["active"]
            or d["approval_status"] != "APPROVED"
        ):
            raise WorkRejected("PROVENANCE_EVIDENCE_MISMATCH")
        refs.append(
            dict(
                ordinal=i,
                document_id=d["document_id"],
                document_version=e.version,
                content_hash=e.content_hash,
                body_sha256=e.content_hash if sha(d["body"]) == e.content_hash else None,
                chunk_ref=e.chunk_ref,
            )
        )
        origins.append(d["data_origin"])
        if d["effective_to"]:
            valid_until.append(d["effective_to"])
    has_any = any(v is not None for v in values.values()) or bool(refs)
    complete = (
        all(
            values[k]
            for k in (
                "source_message_id",
                "suggestion_id",
                "approval_id",
                "model_version",
                "prompt_version",
                "retrieval_ref",
            )
        )
        and refs
        and suggestion_evidence_complete
        and all(e["body_sha256"] for e in refs)
    )
    values.update(
        provenance_state="COMPLETE" if complete else "PARTIAL" if has_any else "MISSING",
        origin="SYNTHETIC"
        if "SYNTHETIC" in origins
        else "APPLICATION"
        if set(origins) == {"APPLICATION"}
        else "UNKNOWN",
    )
    values["evidence_count"] = len(refs)
    return values, refs, min(valid_until) if valid_until else None


def persist(session, message_id, ticket, job, command, prepared, now):
    values, refs, _ = prepared
    session.execute(
        reply_records.insert().values(
            **values,
            message_id=message_id,
            ticket_id=ticket["ticket_id"],
            cycle_no=command.cycle_no,
            job_id=job["job_id"],
            input_ticket_revision=command.expected_revision,
            result_ticket_revision=command.expected_revision + 1,
            reply_sha256=sha(command.message),
            attribution_team_id=ticket["team_id"],
            committed_at=now,
        )
    )
    if refs:
        session.execute(evidence.insert(), [{"message_id": message_id, **e} for e in refs])
