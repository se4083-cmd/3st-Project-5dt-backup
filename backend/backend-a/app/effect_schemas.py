from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.analytics_schemas import Count, Hash, Model

Number = Annotated[Decimal, Field(ge=0, le=10**12)]
Change = Annotated[Decimal, Field(ge=-(10**12), le=10**12)]
Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")]


class Period(Model):
    inquiry_count: Count | None
    inquiry_coverage: Annotated[Decimal, Field(ge=0, le=1)]
    sales_count: Count | None
    sales_coverage: Annotated[Decimal, Field(ge=0, le=1)]
    inquiries_per_sale: Number | None


class EffectPayload(Model):
    schema_version: Literal["voc-effect-v1"] = "voc-effect-v1"
    action_id: UUID
    plan_revision: int = Field(ge=1)
    product_id: UUID
    issue_code: str = Field(pattern=r"^[A-Z_]{1,32}$")
    scope_team_ids: list[UUID] = Field(min_length=1, max_length=64)
    origin: Literal["OPERATIONAL", "SYNTHETIC"]
    implemented_at: AwareDatetime
    before_start: AwareDatetime
    before_end: AwareDatetime
    after_start: AwareDatetime
    after_end: AwareDatetime
    source_as_of: AwareDatetime
    generated_at: AwareDatetime
    before_definition: Code
    after_definition: Code
    overlap: Literal["NONE_REPORTED", "POSSIBLE", "UNKNOWN"]
    before: Period
    after: Period
    count_absolute_change: Annotated[int, Field(strict=True, ge=-(10**12), le=10**12)] | None
    count_relative_change: Change | None
    rate_absolute_change: Change | None
    rate_relative_change: Change | None

    @model_validator(mode="after")
    def windows(self):
        if not (
            self.before_start < self.before_end <= self.implemented_at <= self.after_start < self.after_end
        ):
            raise ValueError("Disjoint windows around implementation required")
        if self.before_end - self.before_start != self.after_end - self.after_start:
            raise ValueError("Equal windows required")
        if len(set(self.scope_team_ids)) != len(self.scope_team_ids):
            raise ValueError("Duplicate teams")
        self.scope_team_ids = sorted(self.scope_team_ids, key=str)
        return self


class EffectSubmission(Model):
    batch_id: UUID
    payload: EffectPayload
    payload_sha256: Hash


class EffectStatus(Model):
    batch_id: UUID
    status: Literal["RECEIVED", "VALIDATED", "FAILED", "SUCCEEDED"]
    validation: dict


class EffectResult(Model):
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    reason: str
    as_of: AwareDatetime
    batch_id: UUID | None = None
    origin: Literal["OPERATIONAL", "SYNTHETIC"]
    plan_is_current: bool
    status_codes: list[str] = Field(default_factory=list)
    payload: EffectPayload | None = None
    causal_effect: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    validation_scope: Literal["STRUCTURE_HASH_ARITHMETIC_NOT_SOURCE_TRUTH"] = (
        "STRUCTURE_HASH_ARITHMETIC_NOT_SOURCE_TRUTH"
    )
