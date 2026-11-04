from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.extensions.p1.schemas import Output
from app.schemas import Input


class GenerateVOC(Input):
    product_id: UUID
    team_ids: list[UUID] = Field(min_length=1, max_length=8)


class ReviewVOC(Input):
    expected_revision: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Review reason cannot be blank")
        return value.strip()


class Recommendation(Output):
    title: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[Literal["risk", "repeat", "rate", "trend"]] = Field(min_length=1, max_length=4)

    @field_validator("title", "action")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Empty recommendation")
        return value.strip()


class Proposal(Output):
    recommendations: list[Recommendation] = Field(min_length=1, max_length=5)


class ReviewView(Output):
    review_id: UUID
    reviewed_by: UUID
    decision: Literal["APPROVED", "REJECTED"]
    reason: str
    created_at: datetime


class VOCView(Output):
    request_id: UUID
    product_id: UUID
    batch_id: UUID | None
    created_by: UUID
    team_ids: list[UUID]
    status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED", "INSUFFICIENT_DATA", "FAILED"]
    revision: int
    provider: Literal["MOCK", "AZURE_OPENAI"]
    model_deployment: str | None
    evidence: dict
    evidence_hash: str
    proposal: Proposal | None
    reason_code: str | None
    created_at: datetime
    updated_at: datetime
    reviews: list[ReviewView]


class VOCPage(Output):
    items: list[VOCView]
    next_cursor: str | None
