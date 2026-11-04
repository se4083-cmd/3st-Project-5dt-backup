from fastapi import APIRouter, HTTPException

from backend.app.automation.mock_context import load_json

router = APIRouter(
    prefix="/api/mock/automation-jobs",
    tags=["Backend B - Automation Jobs"],
)


@router.get("/{job_id}")
def get_automation_job(job_id: str):
    """자동화 작업 ID로 합성 작업 데이터를 조회한다."""

    jobs = load_json("automation_jobs.json")

    job = next(
        (item for item in jobs if item.get("job_id") == job_id),
        None,
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Automation job not found: {job_id}",
        )

    return job
