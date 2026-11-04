from backend.app.automation.job_store import get_connection

job_id = "f51d20c2-d498-41fd-bd80-8446f5e05481"

with get_connection() as connection:
    cursor = connection.execute(
        """
        UPDATE automation_jobs
        SET lease_until = ?
        WHERE job_id = ?
          AND status = ?
        """,
        (
            "2020-01-01T00:00:00+00:00",
            job_id,
            "RUNNING",
        ),
    )

    print("updated:", cursor.rowcount)
