"""Versioned allowlist: no arbitrary metric dictionaries, paths, URLs or free text."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator

Count = Annotated[StrictInt, Field(ge=0, le=10**12)]
Code = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_+\-]{0,63}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Category = Literal["ACCOUNT", "DELIVERY", "PAYMENT", "PRODUCT", "REFUND", "RETURN", "FAQ", "UNCLASSIFIED"]
Issue = Literal[
    "DELIVERY_DELAY", "RETURN_PROCESS", "REFUND_DELAY", "DAMAGED", "PAYMENT_ERROR", "ACCOUNT_ERROR"
]
TABLES = (
    "analytics_daily",
    "analytics_product_daily",
    "analytics_product_voc_daily",
    "analytics_product_risk",
)
KEYS = {
    TABLES[0]: ("day", "team_key", "category"),
    TABLES[1]: ("day", "product_id", "category", "issue_tag"),
    TABLES[2]: ("scope_key", "product_id", "day", "primary_issue"),
    TABLES[3]: ("scope_key", "product_id"),
}


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc) if isinstance(value, datetime) else value


class Windows(Model):
    history_start: AwareDatetime
    operational_start: AwareDatetime
    sales_start: AwareDatetime
    prior_start: AwareDatetime
    recent_start: AwareDatetime
    window_end: AwareDatetime


class Scope(Model):
    scope_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_+\-]{0,63}$")]
    team_ids: list[UUID] = Field(min_length=1, max_length=8)


class RowCounts(Model):
    analytics_daily: Count
    analytics_product_daily: Count
    analytics_product_voc_daily: Count
    analytics_product_risk: Count


class PayloadHashes(Model):
    analytics_daily: Hash
    analytics_product_daily: Hash
    analytics_product_voc_daily: Hash
    analytics_product_risk: Hash


class SourceHashes(Model):
    orders: Hash | None = None
    tickets: Hash | None = None
    customer_contacts: Hash | None = None
    followup_actions: Hash | None = None
    coverage: Hash | None = None


class Manifest(Model):
    batch_id: UUID
    schema_version: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
    rule_version: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
    source: Literal["LOCAL_SYNTHETIC", "FABRIC"]
    source_as_of: AwareDatetime
    generated_at: AwareDatetime
    windows: Windows
    calendar_timezone: Literal["Asia/Seoul"] = "Asia/Seoul"
    team_ids: list[UUID] = Field(min_length=1, max_length=8)
    product_ids: list[UUID] = Field(min_length=1, max_length=1000)
    scopes: list[Scope] = Field(min_length=1, max_length=255)
    row_counts: RowCounts
    payload_checksums: PayloadHashes
    source_input_hashes: SourceHashes
    kpi_definition: Literal["fixture-ticket-v1", "ticket-cohort-v1"]
    product_kpi_definition: Literal["issue-tag-grain-v1"]
    sales_denominator_scope: Literal["GLOBAL_PRODUCT_PAID_28D"]


class Daily(Model):
    day: date
    team_key: str = Field(min_length=1, max_length=36)
    category: Category
    ticket_count: Count
    auto_closed_count: Count
    handoff_count: Count
    reopened_count: Count
    sla_breach_count: Count
    duration_sum_seconds: Annotated[float, Field(ge=0, le=10**15)]
    duration_n: Count
    approval_count: Count
    review_count: Count


class ProductDaily(Model):
    day: date
    product_id: UUID
    category: Category
    issue_tag: Issue | Literal["NONE"]
    ticket_count: Count
    return_refund_count: Count
    auto_count: Count
    handoff_count: Count
    paid_order_count: Count | None
    inquiry_order_count: Count | None
    prior_count: Count | None


class VocDaily(Model):
    scope_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_+\-]*$")
    product_id: UUID
    day: date
    primary_issue: Issue
    episode_count: Count
    unresolved_count: Count


class Metrics(Model):
    C: Count
    P: Count
    S: Count
    N: Count
    M: Count
    U: Count
    K: Count
    raw_rate: Annotated[float, Field(ge=0, le=1)] | None
    smoothed_rate: Annotated[float, Field(ge=0, le=1)]
    growth: Annotated[float, Field(ge=-1, le=10**12)] | None
    top_issue: Issue | None
    outside_cohort: Count
    excluded_count: Count
    sales_complete: bool
    quality_ok: bool
    complaints_complete: bool
    episode_state_complete: bool


class Component(Model):
    normalized: Annotated[float, Field(ge=0, le=1)]
    weight: Annotated[float, Field(ge=0, le=1)]
    contribution: Annotated[float, Field(ge=0, le=100)]


class Components(Model):
    volume: Component
    rate: Component
    growth: Component
    repeat: Component
    unresolved: Component


class Risk(Model):
    scope_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_+\-]*$")
    product_id: UUID
    rule_version: str = Field(min_length=1, max_length=64)
    data_status: Literal["ELIGIBLE", "LOW_SAMPLE", "DATA_MISSING", "QUALITY_BLOCKED"]
    score: Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=6)] | None
    rank: Annotated[StrictInt, Field(ge=1, le=1000)] | None
    risk_band: Literal["NORMAL", "WATCH", "HIGH"] | None
    metrics: Metrics
    components: Components
    source_as_of: AwareDatetime
    window_end: AwareDatetime


class Payload(Model):
    analytics_daily: list[Daily] = Field(max_length=20000)
    analytics_product_daily: list[ProductDaily] = Field(max_length=20000)
    analytics_product_voc_daily: list[VocDaily] = Field(max_length=20000)
    analytics_product_risk: list[Risk] = Field(min_length=1, max_length=20000)


class Submission(Model):
    manifest: Manifest
    payload: Payload


class BatchStatus(Model):
    batch_id: UUID
    status: str
    content_hash: str | None
    is_current: bool
    validation_passed: bool
    validated_at: datetime | None
    published_at: datetime | None
    validation_result: dict


class SnapshotMeta(Model):
    batch_id: UUID
    schema_version: str
    rule_version: str
    source: Literal["LOCAL_SYNTHETIC", "FABRIC"]
    source_as_of: AwareDatetime
    generated_at: AwareDatetime
    window_end: AwareDatetime
    windows: Windows
    published_at: AwareDatetime
    is_current: bool
    scope_key: str
    team_ids: list[UUID]
    stale: bool
    origin_verification: Literal["SERVICE_DECLARED_NOT_INDEPENDENTLY_VERIFIED"]
    cache_fingerprint: str
    sales_denominator_scope: Literal["GLOBAL_PRODUCT_PAID_28D"]


class SnapshotEnvelope(Model):
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    reason: str | None
    meta: SnapshotMeta | None


class VocList(SnapshotEnvelope):
    items: list[Risk]


class ProductKpi(Model):
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    reason: str | None
    grain: str
    unique_ticket_totals: str
    items: list[ProductDaily]


class ProductDetail(SnapshotEnvelope):
    product: Risk | None
    trend: list[VocDaily] = []
    product_kpi: ProductKpi | None = None
    score_meaning: str | None = None


class UnavailableMetric(Model):
    availability: Literal["UNAVAILABLE"]
    reason: str


class KpiMetrics(Model):
    ticket_count: int
    category_counts: dict[str, int]
    auto_closed_count: int
    handoff_count: int
    auto_closed_ratio: float | None
    handoff_ratio: float | None
    ratio_denominator: int
    duration_sum_seconds: float
    duration_n: int
    mean_duration_seconds: float | None
    reopened: UnavailableMetric
    approval: UnavailableMetric
    review: UnavailableMetric
    sla: UnavailableMetric


class KpiResponse(SnapshotEnvelope):
    metrics: KpiMetrics | None
    definition: str | None = None
    quality: str | None = None
    coverage: str | None = None
    grain: str | None = None
    rows: list[Daily] = []
