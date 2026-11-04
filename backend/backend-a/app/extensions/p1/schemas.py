from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.staff_router import ControlState


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class P1Session(Output):
    userId: UUID
    displayName: str
    role: Literal["ADMIN"]
    active: Literal[True]
    permissions: list[str]
    allowedTeamIds: list[UUID]
    scopeKey: str
    capabilities: list[str]


class Automation(Output):
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    state: ControlState | None
    reason: str | None


class JobCounts(Output):
    unit: Literal["job"] = "job"
    raw_counts: dict[str, dict[str, int]]
    eligible_pending: int
    active_running: int
    retry_wait: int
    expired_running: int
    generation_mismatch: int | None
    superseded: int
    current_failed: int


class Unobserved(Output):
    availability: Literal["UNOBSERVED"] = "UNOBSERVED"
    coverage: Literal["NONE"] = "NONE"
    observation_started_at: None = None
    attempts: None = None
    errors: None = None
    retries: None = None
    reason: Literal["NO_INSTRUMENTED_PROVIDER"] = "NO_INSTRUMENTED_PROVIDER"
    unobserved_components: list[str] = [
        "BACKEND_B",
        "P1_VOC",
        "AZURE_OPENAI",
        "AZURE_SEARCH",
        "FABRIC_CONNECTION",
    ]


class AiCallSummary(Unobserved):
    from_time: datetime = Field(alias="from")
    to: datetime
    as_of: datetime
    selected_team_ids: list[UUID]
    attempt_count: None = None
    failed_attempt_count: None = None
    retry_attempt_count: None = None
    error_rate: None = None
    counts_by_code: None = None
    started_count: None = None
    unknown_count: None = None
    sources: dict[Literal["MOCK", "AZURE_OPENAI"], None]


class TaskCounts(Output):
    unit: Literal["task"] = "task"
    availability: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    counts: None = None
    coverage: Literal["NO_TASK_PRODUCER"] = "NO_TASK_PRODUCER"
    reason: Literal["VOC_AND_POLICY_NOT_IMPLEMENTED"] = "VOC_AND_POLICY_NOT_IMPLEMENTED"


class Analytics(Output):
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    reason: str | None
    meta: dict | None
    connection_status: Literal["UNOBSERVED"] = "UNOBSERVED"


class MonitorSummary(Output):
    as_of: datetime
    selected_team_ids: list[UUID]
    coverage: Literal["ROUTED_CURRENT_CYCLE_VERSION"] = "ROUTED_CURRENT_CYCLE_VERSION"
    excluded_definition: str
    automation: Automation
    jobs: JobCounts
    p1_tasks: TaskCounts
    analytics: Analytics
    ai: Unobserved


class JobView(Output):
    job_id: UUID
    ticket_id: UUID
    job_kind: Literal["AUTO", "HANDOFF"]
    status: str
    attempt: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    error_code: str | None
    updated_at: datetime
    cycle_no: int
    expected_ticket_version: int
    scope_status: Literal["CURRENT", "SUPERSEDED"]
    data_origin: str


class JobPage(Output):
    as_of: datetime
    selected_team_ids: list[UUID]
    items: list[JobView]
    next_cursor: str | None
