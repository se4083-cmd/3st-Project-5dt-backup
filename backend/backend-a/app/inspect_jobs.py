"""Local handoff inspection only. No processing or network calls."""

import json

from sqlalchemy import select

from app.config import get_settings
from app.db import build_engine
from app.models import automation_jobs


def main():
    engine = build_engine(get_settings())
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    automation_jobs.c.job_id,
                    automation_jobs.c.ticket_id,
                    automation_jobs.c.cycle_no,
                    automation_jobs.c.expected_ticket_version,
                    automation_jobs.c.status,
                    automation_jobs.c.job_kind,
                    automation_jobs.c.reason_code,
                    automation_jobs.c.source_message_id,
                    automation_jobs.c.next_attempt_at,
                )
                .where(automation_jobs.c.status.in_(["PENDING", "RETRY"]))
                .order_by(automation_jobs.c.next_attempt_at, automation_jobs.c.job_id)
                .limit(100)
            )
            .mappings()
            .all()
        )
        print(json.dumps([dict(r) for r in rows], default=str, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
