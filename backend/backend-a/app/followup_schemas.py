from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.schemas import Input

FollowupStatus = Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]
CancelReason = Literal["CUSTOMER_WITHDREW", "NO_LONGER_NEEDED", "DUPLICATE", "OTHER"]


class FollowupCreate(Input):
    ticket_id: UUID | None = None
    product_id: UUID | None = None
    owner_team_id: UUID
    owner_user_id: UUID | None = None
    kind: str = Field(min_length=1, max_length=64)
    public_note: str | None = Field(default=None, max_length=4000)
    internal_note: str | None = Field(default=None, max_length=10000)
    blocks_resolution: bool = False
    due_at: AwareDatetime | None = None

    @field_validator("kind", "public_note", "internal_note")
    @classmethod
    def trim_text(cls, value):
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def target(self):
        if (self.ticket_id is None) == (self.product_id is None) or not self.kind:
            raise ValueError("Specify exactly one target and a nonblank kind")
        if self.product_id and self.blocks_resolution:
            raise ValueError("Product actions cannot block a ticket resolution")
        return self


class FollowupPatch(Input):
    expected_revision: int = Field(ge=1)
    owner_team_id: UUID | None = None
    owner_user_id: UUID | None = None
    kind: str | None = Field(default=None, min_length=1, max_length=64)
    public_note: str | None = Field(default=None, max_length=4000)
    internal_note: str | None = Field(default=None, max_length=10000)
    blocks_resolution: bool | None = None
    due_at: AwareDatetime | None = None
    _text = field_validator("kind", "public_note", "internal_note")(FollowupCreate.trim_text.__func__)

    @model_validator(mode="after")
    def changes(self):
        changed = self.model_fields_set - {"expected_revision"}
        if not changed:
            raise ValueError("No changes specified")
        for name in ("owner_team_id", "kind", "blocks_resolution"):
            if name in changed and getattr(self, name) is None:
                raise ValueError("Field cannot be cleared")
        if self.kind == "":
            raise ValueError("Blank kind")
        return self


class FollowupState(Input):
    expected_revision: int = Field(ge=1)
    status: FollowupStatus
    cancellation_reason: CancelReason | None = None

    @model_validator(mode="after")
    def cancellation(self):
        if (self.status == "CANCELLED") != (self.cancellation_reason is not None):
            raise ValueError("Cancellation reason is required only for CANCELLED")
        return self


class FollowupCancel(Input):
    expected_revision: int = Field(ge=1)
    cancellation_reason: CancelReason


class FollowupReceipt(BaseModel):
    action_id: UUID
    revision: int
    created_at: datetime


class FollowupPublic(BaseModel):
    action_id: UUID
    ticket_id: UUID
    cycle_no: int
    status: FollowupStatus
    public_note: str
    due_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class FollowupStaff(BaseModel):
    action_id: UUID
    ticket_id: UUID | None
    product_id: UUID | None
    cycle_no: int | None
    responsibility_cycle_no: int | None
    origin_team_id: UUID
    owner_team_id: UUID
    owner_user_id: UUID | None
    kind: str
    status: FollowupStatus
    public_note: str | None
    internal_note: str | None
    blocks_resolution: bool
    due_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    revision: int
    created_at: datetime
    updated_at: datetime
    needs_handover: bool
