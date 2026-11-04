from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.analytics_schemas import Issue
from app.followup_schemas import FollowupCreate, FollowupStaff
from app.schemas import Input


class PlanValues(Input):
    issue_code: Issue
    improvement_text: str = Field(min_length=1, max_length=4000)
    implemented_at: AwareDatetime | None = None
    before_start: AwareDatetime | None = None
    before_end: AwareDatetime | None = None
    after_start: AwareDatetime | None = None
    after_end: AwareDatetime | None = None
    comparison_team_ids: list[UUID] = Field(min_length=1, max_length=64)
    source_batch_id: UUID | None = None
    source_scope_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_+\-]{0,63}$")
    change_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("improvement_text", "change_reason")
    @classmethod
    def text(cls, value):
        if not value.strip():
            raise ValueError("Blank text")
        return value.strip()

    @field_validator("implemented_at", "before_start", "before_end", "after_start", "after_end")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc) if value else None

    @field_validator("comparison_team_ids")
    @classmethod
    def unique_teams(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate teams")
        return sorted(value, key=str)

    @model_validator(mode="after")
    def windows(self):
        bounds = (self.before_start, self.before_end, self.after_start, self.after_end)
        if any(v is not None for v in bounds):
            if any(v is None for v in bounds) or self.implemented_at is None:
                raise ValueError("All boundaries and implementation time required")
            bs, be, ass, ae = bounds
            if not (bs < be <= self.implemented_at <= ass < ae) or be - bs != ae - ass:
                raise ValueError("Equal, disjoint windows around implementation required")
        if (self.source_batch_id is None) != (self.source_scope_key is None):
            raise ValueError("Batch and scope must be supplied together")
        return self


class ImprovementCreate(Input):
    followup: FollowupCreate | None = None
    existing_action_id: UUID | None = None
    expected_action_revision: int | None = Field(default=None, ge=1)
    plan: PlanValues

    @model_validator(mode="after")
    def target(self):
        if (self.followup is None) == (self.existing_action_id is None):
            raise ValueError("Choose new followup or existing action")
        if self.followup and (self.followup.product_id is None or self.expected_action_revision is not None):
            raise ValueError("New product followup required")
        if self.existing_action_id and self.expected_action_revision is None:
            raise ValueError("Existing action revision required")
        return self


class PlanCreate(PlanValues):
    expected_action_revision: int = Field(ge=1)
    expected_plan_revision: int = Field(ge=1)
    correction: bool = False


class TicketLink(Input):
    ticket_id: UUID
    expected_action_revision: int = Field(ge=1)
    expected_plan_revision: int = Field(ge=1)


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImprovementReceipt(Output):
    action_id: UUID
    action_revision: int
    plan_revision: int
    ticket_id: UUID | None = None


class PlanView(PlanValues):
    revision: int
    owner_team_id_snapshot: UUID
    change_kind: Literal["INITIAL", "PLAN", "CORRECTION"]
    created_by: UUID
    created_at: datetime


class EffectAvailability(Output):
    availability: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    reason: Literal["EFFECT_INTEGRATION_NOT_IMPLEMENTED"] = "EFFECT_INTEGRATION_NOT_IMPLEMENTED"
    metrics: None = None


class ImprovementView(Output):
    action_id: UUID
    product_id: UUID
    followup: FollowupStaff
    current_plan_revision: int
    current_plan: PlanView | None
    plan_access: Literal["AVAILABLE", "COMPARISON_SCOPE_DENIED"]
    plan_refresh_required: bool
    analysis: EffectAvailability = Field(default_factory=EffectAvailability)


class LinkView(Output):
    ticket_id: UUID
    linked_at: datetime


class ImprovementDetail(ImprovementView):
    plans: list[PlanView]
    next_plan_before_revision: int | None
    tickets: list[LinkView]
    next_ticket_cursor: str | None
