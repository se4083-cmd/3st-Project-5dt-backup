from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas import Input

Version = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Origin = Literal["APPLICATION", "SYNTHETIC", "UNKNOWN"]
Accuracy = Literal["CORRECT", "INCORRECT", "UNDETERMINABLE"]
Alignment = Literal["MATCH", "MISMATCH", "UNDETERMINABLE", "NOT_APPLICABLE"]


class EvidenceReference(Input):
    document_id: UUID
    version: int = Field(ge=1)
    content_hash: Hash
    chunk_ref: Version | None = None


class ReplyProvenance(Input):
    source_message_id: UUID | None = None
    suggestion_id: UUID | None = None
    suggestion_revision: int | None = Field(default=None, ge=1)
    suggestion_content_hash: Hash | None = None
    approval_id: UUID | None = None
    model_version: Version | None = None
    prompt_version: Version | None = None
    retrieval_ref: Version | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def linked(self):
        triplet = (self.suggestion_id, self.suggestion_revision, self.suggestion_content_hash)
        if any(x is not None for x in triplet) and not all(x is not None for x in triplet):
            raise ValueError("Suggestion id/revision/hash required together")
        if self.approval_id and not self.suggestion_id:
            raise ValueError("Approval requires explicit suggestion")
        if len({x.document_id for x in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate evidence")
        return self


class SampleCreate(Input):
    message_id: UUID
    rubric_version: str = Field(default="DEV_QUALITY_V1", pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    review_team_id: UUID
    assigned_reviewer_id: UUID


class ReviewCreate(Input):
    expected_revision: int = Field(ge=1)
    accuracy: Accuracy
    policy_alignment: Alignment
    reason_codes: list[
        Literal[
            "VERIFIED_AGAINST_MATERIAL",
            "FACT_ERROR",
            "POLICY_CONTRADICTION",
            "INSUFFICIENT_CONTEXT",
            "POLICY_NOT_APPLICABLE",
            "OTHER",
        ]
    ] = Field(min_length=1, max_length=6)
    change_reason: Literal["INITIAL_REVIEW", "CORRECTION", "NEW_INFORMATION", "OTHER"]


class Reassign(Input):
    expected_revision: int = Field(ge=1)
    assigned_reviewer_id: UUID
    change_reason: Literal["REVIEWER_CHANGED", "WORKLOAD_BALANCE", "OTHER"]


class VoidSample(Input):
    expected_revision: int = Field(ge=1)
    change_reason: Literal["WRONG_TARGET", "DUPLICATE", "INVALID_SAMPLE", "OTHER"]


class MaterialRequest(Input):
    purpose_code: str = Field(pattern=r"^[A-Z_]{1,64}$")


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Receipt(Output):
    sample_id: UUID
    revision: int


class Candidate(Output):
    message_id: UUID
    ticket_id: UUID
    cycle_no: int
    input_ticket_revision: int
    result_ticket_revision: int
    attribution_team_id: UUID | None
    provenance_state: Literal["MISSING", "PARTIAL", "COMPLETE"]
    origin: Origin
    committed_at: datetime


class SampleView(Output):
    sample_id: UUID
    message_id: UUID
    rubric_version: str
    review_team_id: UUID
    assigned_reviewer_id: UUID
    status: Literal["OPEN", "VOID"]
    current_revision: int
    selected_at: datetime


class ReviewView(Output):
    revision: int
    event_kind: Literal["SELECT", "REVIEW", "REASSIGN", "VOID"]
    actor_id: UUID
    assigned_reviewer_id: UUID
    accuracy: Accuracy | None
    policy_alignment: Alignment | None
    reason_codes: list[str]
    change_reason: str
    independent_review: Literal["YES", "NO", "UNKNOWN"]
    recorded_at: datetime


class PolicyMaterial(Output):
    document_id: UUID
    version: int
    content_hash: str
    chunk_ref: str | None
    material_state: Literal["VERIFIED_BODY", "REFERENCES_ONLY", "MATERIAL_CHANGED"]
    body: str | None
    truncated: bool = False


class Material(Output):
    sample_id: UUID
    message_id: UUID
    cycle_no: int
    origin: Origin
    provenance_state: str
    material_state: Literal["RECORDED_MATERIAL", "INSUFFICIENT_MATERIAL", "MATERIAL_CHANGED"]
    reply: str | None
    question: str | None
    policies: list[PolicyMaterial]
    model_version: str | None
    prompt_version: str | None
    rubric_version: str
    rubric_criteria: dict[str, str]
    redaction_state: Literal["PATTERN_MASKED_NOT_PII_FREE_GUARANTEE"] = (
        "PATTERN_MASKED_NOT_PII_FREE_GUARANTEE"
    )
    as_of: datetime
    truncated_fields: list[Literal["REPLY", "QUESTION", "POLICY"]] = Field(default_factory=list)


class MetricCounts(Output):
    confirmed_response_count: int
    active_sample_count: int
    void_count: int
    reviewed_count: int
    unreviewed_sample_count: int
    unreviewed_response_count: int
    unselected_or_void_response_count: int
    correct: int
    incorrect: int
    accuracy_undeterminable: int
    policy_match: int
    policy_mismatch: int
    policy_undeterminable: int
    policy_not_applicable: int
    accuracy_denominator: int
    policy_denominator: int
    accuracy_rate: float | None
    policy_alignment_rate: float | None
    evaluation_coverage: float | None


class ReviewTeamEvaluation(Output):
    basis: Literal["MANUAL_SAMPLE_BY_REVIEW_TEAM_NOT_PROCESSING_ATTRIBUTION"] = (
        "MANUAL_SAMPLE_BY_REVIEW_TEAM_NOT_PROCESSING_ATTRIBUTION"
    )
    correct: int
    incorrect: int
    accuracy_undeterminable: int
    policy_match: int
    policy_mismatch: int
    policy_undeterminable: int
    policy_not_applicable: int
    accuracy_denominator: int
    policy_denominator: int
    accuracy_rate: float | None
    policy_alignment_rate: float | None


class QualityMetrics(Output):
    as_of: datetime
    response_start: AwareDatetime
    response_end: AwareDatetime
    team_ids: list[UUID]
    origin: Origin
    rubric_version: str
    period_basis: Literal["REPLY_COMMITTED_AT_[START,END)_CURRENT_SNAPSHOT"] = (
        "REPLY_COMMITTED_AT_[START,END)_CURRENT_SNAPSHOT"
    )
    sampling_method: Literal["MANUAL_NOT_POPULATION_ACCURACY"] = "MANUAL_NOT_POPULATION_ACCURACY"
    attributed: MetricCounts
    review_team_sample_counts: dict[str, int]
    review_team_evaluation: ReviewTeamEvaluation
    unattributed_confirmed_response_count: int | None
    legacy_auto_unknown_count: int | None
    unknown_counts_scope: Literal["NOT_REQUESTED", "GLOBAL_UNATTRIBUTED_EXPLICIT_PERMISSION"]


class RubricView(Output):
    version: str
    status: Literal["DEVELOPMENT_PROPOSAL"]
    criteria: dict[str, str]


class HistoryPage(Output):
    items: list[ReviewView]
    next_before_revision: int | None
