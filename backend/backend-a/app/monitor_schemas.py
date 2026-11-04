from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SafeAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: Literal["UNAVAILABLE"]
    reason: Literal["OPERATIONAL_RULE_AND_B_OBSERVATION_NOT_AGREED"]
    rate: None
    rule_version: Literal["DEV_SAFE_V1"]
    rubric_version: Literal["DEV_QUALITY_V1"]
    observation_seconds: Literal[604800]
    rule_status: Literal["DEVELOPMENT_PROPOSAL"]
    coverage: Literal["A_COMMANDS_RECORDED_B_REPORTING_COMPLETENESS_UNKNOWN"]


class AutomationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: datetime
    recording_since: datetime
    response_start: datetime
    response_end: datetime
    origin: Literal["APPLICATION", "SYNTHETIC", "UNKNOWN"]
    team_ids: list[str]
    period_basis: Literal["PROSPECTIVE_AUTO_CYCLE_STARTED_AT_[START,END)_CURRENT_SNAPSHOT"]
    attribution_basis: Literal["FIRST_EXPLICIT_NON_NULL_TEAM_FACT_CURRENT_SCOPE"]
    auto_cycle_count: int
    human_entry_count_excluded: int
    automatic_completed_count: int
    automatic_completed_rate: float | None
    automatic_reply_committed_count: int
    transferred_count: int
    transferred_rate: float | None
    failed_fact_count: int
    statuses: dict[str, int]
    transfer_reasons: dict[str, int]
    safe_observation_states: dict[str, int]
    legacy_current_auto_mode_untracked_count: int | None
    legacy_count_basis: Literal["CURRENT_MODE_SNAPSHOT_NOT_A_HISTORICAL_COHORT"]
    recording_completeness: Literal["PARTIAL_OBSERVED_FACTS_B_REPORTING_NOT_ATTESTED"]
    unreported_current_terminal_state_count: int
    unreported_current_human_state_count: int
    excluded_unattributed_count: None
    excluded_count_reason: Literal["NOT_EXPOSED_OUTSIDE_SELECTED_SCOPE; HUMAN_ENTRIES_EXPLICITLY_SEPARATED"]
    safe_completion: SafeAvailability
