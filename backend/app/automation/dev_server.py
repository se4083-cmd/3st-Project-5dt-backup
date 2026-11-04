from fastapi import FastAPI

from backend.app.automation.mock_context import router as mock_router
from backend.app.automation.mock_jobs import router as jobs_router
from backend.app.automation.job_create import router as create_router
from backend.app.automation.job_lease import router as lease_router
from backend.app.automation.job_complete import router as complete_router
from backend.app.automation.job_fail import router as fail_router
from backend.app.automation import job_recovery

app = FastAPI(title="CS Flow AI - Backend B Dev")

app.include_router(mock_router)
app.include_router(jobs_router)
app.include_router(create_router)
app.include_router(lease_router)
app.include_router(complete_router)
app.include_router(fail_router)
app.include_router(job_recovery.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "backend-b"}
