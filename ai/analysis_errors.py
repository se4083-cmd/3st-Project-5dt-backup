"""Specific validation failures, compatible with existing ValueError callers."""


class AnalysisResponseError(ValueError):
    """An explicitly checked model/provider response violates the contract."""


class JobContextError(ValueError):
    """Explicitly checked job input is invalid."""


class StaleJobContextError(ValueError):
    """Job identity changed during analysis or before caller handoff."""
