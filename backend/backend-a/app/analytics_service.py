from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app import audit, models
from app.analytics_canonical import canonical_submission, digest, normalize, table_hashes
from app.analytics_models import analytics_publication as pointer
from app.analytics_models import analytics_receipts as receipts
from app.analytics_schemas import TABLES, BatchStatus, Submission
from app.analytics_validation import validate_submission
from app.db import utcnow
from app.errors import APIError

head = models.analytics_batches


def status(session, batch_id):
    row = (
        session.execute(
            select(head, receipts.c.validation_result).join(receipts).where(head.c.batch_id == batch_id)
        )
        .mappings()
        .first()
    )
    if not row:
        raise APIError(404, "BATCH_NOT_FOUND")
    return {key: row[key] for key in BatchStatus.model_fields}


def event(session, identity, action, batch_id):
    audit.record(session, None, action, "ANALYTICS_BATCH", batch_id, service=identity["id"])


def receive(session, submission, identity, max_rows):
    value = canonical_submission(submission)
    if sum(len(value["payload"][t]) for t in TABLES) > max_rows:
        raise APIError(413, "ANALYTICS_ROW_LIMIT")
    batch_id, content_hash = str(submission.manifest.batch_id), digest(value)
    try:
        with session.begin_nested():
            session.execute(
                head.insert().values(
                    batch_id=batch_id,
                    status="RECEIVED",
                    is_current=False,
                    source_as_of=submission.manifest.source_as_of,
                    schema_version=submission.manifest.schema_version,
                    manifest=value["manifest"],
                    row_counts=value["manifest"]["row_counts"],
                    checksums=value["manifest"]["payload_checksums"],
                    content_hash=content_hash,
                )
            )
            session.execute(
                receipts.insert().values(
                    batch_id=batch_id,
                    content_hash=content_hash,
                    payload=value,
                    validation_result={"passed": False, "codes": ["NOT_VALIDATED"]},
                )
            )
            event(session, identity, "ANALYTICS_RECEIVED", batch_id)
    except IntegrityError:
        existing = session.execute(
            select(receipts.c.content_hash).where(receipts.c.batch_id == batch_id)
        ).scalar_one_or_none()
        if existing != content_hash:
            raise APIError(409, "BATCH_CONTENT_CONFLICT") from None
    return status(session, batch_id)


def lock_head(session, batch_id):
    row = (
        session.execute(select(head).where(head.c.batch_id == batch_id).with_for_update()).mappings().first()
    )
    receipt = session.execute(select(receipts).where(receipts.c.batch_id == batch_id)).mappings().first()
    if not row or not receipt:
        raise APIError(404, "MANAGED_BATCH_NOT_FOUND")
    return row, receipt


def validate(session, batch_id, identity):
    row, receipt = lock_head(session, batch_id)
    if row["status"] != "RECEIVED":
        return status(session, batch_id)
    submission = Submission.model_validate(receipt["payload"])
    result = validate_submission(session, submission)
    if result["passed"]:
        # All normalized tables and validation evidence commit atomically.
        for name in TABLES:
            table = getattr(models, name)
            for chunk_start in range(0, len(getattr(submission.payload, name)), 500):
                values = []
                for item in getattr(submission.payload, name)[chunk_start : chunk_start + 500]:
                    item = item.model_dump(mode="python")
                    for key in ("product_id",):
                        if key in item:
                            item[key] = str(item[key])
                    for key in ("metrics", "components"):
                        if key in item:
                            item[key] = normalize(item[key])
                    values.append({**item, "batch_id": batch_id})
                session.execute(table.insert(), values)
    now = utcnow()
    session.execute(update(receipts).where(receipts.c.batch_id == batch_id).values(validation_result=result))
    session.execute(
        update(head)
        .where(head.c.batch_id == batch_id)
        .values(
            status="VALIDATED" if result["passed"] else "FAILED",
            validation_passed=result["passed"],
            validated_at=now,
            updated_at=now,
        )
    )
    event(session, identity, "ANALYTICS_VALIDATED" if result["passed"] else "ANALYTICS_REJECTED", batch_id)
    return status(session, batch_id)


def stored_payload(session, batch_id):
    result = {}
    for name in TABLES:
        table = getattr(models, name)
        fields = list(
            Submission.model_fields["payload"]
            .annotation.model_fields[name]
            .annotation.__args__[0]
            .model_fields
        )
        result[name] = [
            dict(r)
            for r in session.execute(
                select(*(table.c[f] for f in fields)).where(table.c.batch_id == batch_id)
            ).mappings()
        ]
    # Revalidate types (notably Decimal values) before canonical hashing.
    from app.analytics_schemas import Payload

    return normalize(Payload.model_validate(result))


def publish(session, batch_id, identity):
    current_id = session.execute(
        select(pointer.c.batch_id).where(pointer.c.singleton_id == 1).with_for_update()
    ).scalar_one()
    row, receipt = lock_head(session, batch_id)
    if row["status"] == "SUCCEEDED":
        return status(session, batch_id)
    if (
        row["status"] != "VALIDATED"
        or not row["validation_passed"]
        or not receipt["validation_result"].get("passed")
    ):
        raise APIError(409, "BATCH_NOT_VALIDATED")
    try:
        payload = stored_payload(session, batch_id)
    except ValidationError:
        raise APIError(409, "VALIDATED_PAYLOAD_CHANGED") from None
    if table_hashes(payload) != row["checksums"] or {t: len(payload[t]) for t in TABLES} != row["row_counts"]:
        raise APIError(409, "VALIDATED_PAYLOAD_CHANGED")
    candidate = Submission.model_validate(receipt["payload"]).manifest
    if current_id:
        current = session.execute(select(head).where(head.c.batch_id == current_id)).mappings().one()
        old = Submission.model_validate(
            session.scalar(select(receipts.c.payload).where(receipts.c.batch_id == current_id))
        ).manifest
        if (
            candidate.windows.window_end < old.windows.window_end
            or candidate.source_as_of < old.source_as_of
            or (
                candidate.windows.window_end == old.windows.window_end
                and candidate.source_as_of == old.source_as_of
            )
        ):
            raise APIError(409, "BATCH_NOT_NEWER")
        session.execute(update(head).where(head.c.batch_id == current["batch_id"]).values(is_current=False))
    session.execute(
        update(head)
        .where(head.c.batch_id == batch_id)
        .values(status="SUCCEEDED", is_current=True, published_at=utcnow())
    )
    session.execute(update(pointer).where(pointer.c.singleton_id == 1).values(batch_id=batch_id))
    event(session, identity, "ANALYTICS_PUBLISHED", batch_id)
    return status(session, batch_id)
