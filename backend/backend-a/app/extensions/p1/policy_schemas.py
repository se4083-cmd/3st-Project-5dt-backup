from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas import Input

from .schemas import Output
from .voc_schemas import ReviewVOC


class PolicyContent(Input):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    source_document_id: UUID | None = None

    @field_validator("title", "body")
    @classmethod
    def text(cls, value):
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if not value.strip() or "\x00" in value or len(value.splitlines()) > 500:
            raise ValueError("Nonblank text, no NUL, at most 500 lines")
        return value


class RegisterPolicy(PolicyContent):
    policy_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    team_ids: list[UUID] = Field(min_length=1, max_length=8)


class AppendVersion(PolicyContent):
    expected_previous_version: int = Field(ge=1)


class ComparePolicy(Input):
    from_version_id: UUID | None = None
    to_version_id: UUID


class PolicyDecision(ReviewVOC):
    """Same nonblank reason, revision and decision contract as VOC; different permission."""


class PolicyVersion(Output):
    version_id: UUID
    policy_id: UUID
    version_no: int
    title: str
    body: str
    content_hash: str
    source_document_id: UUID | None
    source_snapshot: dict
    status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED"]
    revision: int
    created_by: UUID
    created_at: datetime


class PolicyView(Output):
    policy_id: UUID
    policy_key: str
    scope_hash: str
    latest_version: int
    created_by: UUID
    created_at: datetime
    team_ids: list[UUID]
    versions: list[PolicyVersion]
    versions_truncated: bool
    activation: Literal["NOT_SUPPORTED"] = "NOT_SUPPORTED"


class PolicyPage(Output):
    items: list[PolicyView]
    next_cursor: str | None


class LineChange(Output):
    operation: Literal["replace", "delete", "insert"]
    old_start: int
    old_end: int
    new_start: int
    new_end: int
    before: list[str]
    after: list[str]


class PolicyDiff(Output):
    kind: Literal["INITIAL_VERSION", "NO_CHANGE", "METADATA_ONLY", "CONTENT_CHANGED"]
    title_before: str | None
    title_after: str
    body_changed: bool
    changes: list[LineChange]
    from_hash: str | None
    to_hash: str


class ReferenceLink(Output):
    suggestion_id: UUID
    document_id: UUID
    document_version: int
    source_active_at_analysis: bool
    rule_id: UUID | None
    rule_version: int | None
    rule_origin: str | None = None
    rule_active: bool | None = None
    category: str
    origin: str
    document_origin: str
    relation: Literal["RECORDED_POLICY_CITATION", "RULE_CO_USED_WITH_POLICY_CITATION"]


class ImpactDomain(Output):
    status: Literal["RECORDED_LINKS", "UNCONFIRMED"]
    reason: str
    observed_reference_count: int
    links: list[ReferenceLink]
    actual_affected_count: None = None
    runtime_effect: Literal["UNCONFIRMED"] = "UNCONFIRMED"


class PolicyImpact(Output):
    as_of: datetime
    coverage: Literal["SCOPED_LOCAL_RECORDED_SUGGESTIONS"] = "SCOPED_LOCAL_RECORDED_SUGGESTIONS"
    source_validation: Literal["VERIFIED_SNAPSHOT", "UNCONFIRMED"]
    source_reason: str
    scanned_count: int
    truncated: bool
    faq: ImpactDomain
    auto_replies: ImpactDomain
    automation_rules: ImpactDomain
    faq_catalog: Literal["UNCONFIRMED"] = "UNCONFIRMED"
    rule_condition_dependency: Literal["UNCONFIRMED"] = "UNCONFIRMED"
    backend_b_runtime: Literal["UNCONFIRMED"] = "UNCONFIRMED"
    rag_index: Literal["UNCONFIRMED"] = "UNCONFIRMED"
    azure_ai_search: Literal["UNCONFIRMED"] = "UNCONFIRMED"


class PolicyReviewView(Output):
    review_id: UUID
    comparison_id: UUID
    version_id: UUID
    reviewed_by: UUID
    decision: Literal["APPROVED", "REJECTED"]
    reason: str
    created_at: datetime


class ComparisonView(Output):
    comparison_id: UUID
    policy_id: UUID
    from_version_id: UUID | None
    to_version_id: UUID
    diff: PolicyDiff
    impact: PolicyImpact
    analysis_hash: str
    status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED"]
    revision: int
    created_by: UUID
    created_at: datetime
    reviews: list[PolicyReviewView]
    candidate_status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED"]
    reviewable: bool
    activation: Literal["NOT_SUPPORTED"] = "NOT_SUPPORTED"


class ComparisonPage(Output):
    items: list[ComparisonView]
    next_cursor: str | None


class VersionPage(Output):
    items: list[PolicyVersion]
    next_before_version: int | None
