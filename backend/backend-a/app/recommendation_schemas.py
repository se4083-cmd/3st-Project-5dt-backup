from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.workload_schemas import AgentWorkload, WorkloadOutput

Reason = Literal[
    "HUMAN_HANDOFF_PENDING",
    "DEADLINE_OVERDUE",
    "DEADLINE_DUE_SOON",
    "DEADLINE_ON_TIME",
    "NO_DUE_DATE",
    "WAITING_START_UNRECORDED",
    "FAILED_AUTO_HISTORY_PRESERVED",
    "PHYSICAL_ASSIGNMENT_RECONCILIATION_REQUIRED",
    "UNROUTED_NO_RECOMMENDATION",
    "NOT_HUMAN_PATH",
    "STATE_NOT_ASSIGNABLE",
    "ALREADY_VALIDLY_ASSIGNED",
    "CATEGORY_UNKNOWN",
    "ROUTE_CATEGORY_UNSUPPORTED",
    "NO_ELIGIBLE_AGENT",
]
CandidateReason = Literal[
    "ACTIVE_AGENT",
    "ROUTE_TEAM_MATCH",
    "CATEGORY_SUPPORTED",
    "NORMALIZED_SCOPE_PRESENT",
    "ORDERED_BY_ACTIVE_TICKET_COUNT",
    "ORDERED_BY_OVERDUE_COUNT",
    "STABLE_USER_ID_TIEBREAK",
]


class RecommendationCandidate(AgentWorkload):
    rank: int
    reason_codes: list[CandidateReason]


class RecommendationItem(WorkloadOutput):
    ticket_id: UUID
    cycle_no: int
    ticket_revision: int
    route_revision: int | None
    route_team_id: UUID | None
    route_recorded_at: datetime | None
    category: str | None
    deadline_state: Literal["overdue", "due_soon", "on_time", "no_due_date"]
    due_at: datetime | None
    waiting_since: None = None
    waiting_basis: Literal["NOT_RECORDED_NOT_INFERRED"] = "NOT_RECORDED_NOT_INFERRED"
    recommendation_state: Literal["AVAILABLE", "CONDITIONAL", "UNAVAILABLE"]
    reason_codes: list[Reason]
    invalid_active_assignment_present: bool
    eligible_candidate_count: int
    candidates_truncated: bool
    candidates: list[RecommendationCandidate]


class RecommendationPage(WorkloadOutput):
    as_of: datetime
    expires_at: datetime
    rule_version: Literal["WORKLOAD_PRIORITY_V1"] = "WORKLOAD_PRIORITY_V1"
    freshness_seconds: Literal[30] = 30
    deadline_basis: Literal["STORED_DEADLINES_NOT_SLA_COMPLIANCE"] = "STORED_DEADLINES_NOT_SLA_COMPLIANCE"
    waiting_time_basis: Literal["UNAVAILABLE_NO_HUMAN_WAIT_START_HISTORY"] = (
        "UNAVAILABLE_NO_HUMAN_WAIT_START_HISTORY"
    )
    execution_authority: Literal["READ_ONLY_HINT_NOT_RESERVATION_OR_ASSIGNMENT"] = (
        "READ_ONLY_HINT_NOT_RESERVATION_OR_ASSIGNMENT"
    )
    team_ids: list[UUID]
    ticket_filter: UUID | None
    total: int
    items: list[RecommendationItem]
    next_cursor: str | None
    limitations: list[str] = Field(
        default_factory=lambda: [
            "NO_ATTENDANCE_LEAVE_ONLINE_SKILL_OR_CAPACITY_SOURCE",
            "FIXED_ID_TIEBREAK_CAN_BIAS",
            "NO_CONCURRENT_ASSIGNMENT_OR_LOAD_BALANCING_GUARANTEE",
            "EACH_PAGE_IS_A_FRESH_SNAPSHOT",
            "B_MUST_REVALIDATE_BEFORE_EXECUTION",
        ]
    )
