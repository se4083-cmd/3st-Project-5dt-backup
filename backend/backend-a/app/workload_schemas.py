"""Aggregate-only staff workload contract; no ticket/customer/message payloads."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkloadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeadlineCounts(WorkloadOutput):
    total: int = 0
    overdue: int = 0
    due_soon: int = 0
    on_time: int = 0
    no_due_date: int = 0


class TicketCounts(DeadlineCounts):
    waiting_customer: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)


class HandlingPathCounts(WorkloadOutput):
    automatic_path: int = 0
    human_assignment_waiting: int = 0
    unknown: int = 0


class UnassignedCounts(TicketCounts):
    invalid_assignment_count: int = 0
    by_handling_path: HandlingPathCounts = Field(default_factory=HandlingPathCounts)


class AgentWorkload(WorkloadOutput):
    agent_id: UUID
    team_id: UUID
    tickets: TicketCounts
    followups: DeadlineCounts


class WorkloadTotals(WorkloadOutput):
    tickets: TicketCounts = Field(default_factory=TicketCounts)
    followups: DeadlineCounts = Field(default_factory=DeadlineCounts)


class WorkloadTeamQueue(WorkloadOutput):
    unassigned: UnassignedCounts
    waiting_followups: DeadlineCounts
    admin_owned_followups: DeadlineCounts


class WorkloadPage(WorkloadOutput):
    as_of: datetime
    view: Literal["SELF", "TEAM"]
    deadline_basis: Literal["STORED_DEADLINES_NOT_SLA_COMPLIANCE"] = "STORED_DEADLINES_NOT_SLA_COMPLIANCE"
    ticket_deadline_policy: Literal["LEGACY_24H_CONTINUOUS"] = "LEGACY_24H_CONTINUOUS"
    due_soon_seconds: Literal[7200] = 7200
    team_ids: list[UUID]
    agent_filter: UUID | None
    total_agents: int
    matching_agents: int
    items: list[AgentWorkload]
    next_cursor: str | None
    scope_totals: WorkloadTotals
    page_totals: WorkloadTotals
    team_queue: WorkloadTeamQueue | None
    unrouted: UnassignedCounts | None
