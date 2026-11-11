"""Typed errors. Nothing in the engine converts one of these into a success."""

from __future__ import annotations


class MindmapError(Exception):
    """Base class for all engine errors."""


class ConfigError(MindmapError):
    """Missing credentials or invalid configuration. Raised before any request."""


class InputError(MindmapError):
    """User-supplied document or map is unusable. Raised before any request."""


class ProviderError(MindmapError):
    """The LLM provider failed. `retryable` says whether one more attempt may help."""

    retryable: bool = False

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ProviderTimeout(ProviderError):
    retryable = True


class ProviderRateLimited(ProviderError):
    retryable = True


class ProviderUnavailable(ProviderError):
    """5xx, overloaded, or a connection failure."""

    retryable = True


class ProviderAuthError(ProviderError):
    retryable = False


class ProviderRequestRejected(ProviderError):
    """4xx other than auth/rate-limit: the request itself is wrong; retrying will not help."""

    retryable = False


class ModelOutputError(MindmapError):
    """Every allowed attempt produced unusable output. No map is returned."""

    def __init__(self, message: str, failures: list[str]) -> None:
        super().__init__(message)
        self.failures = failures


class CallBudgetExceeded(MindmapError):
    """A code path tried to exceed its LLM request budget. Always a bug."""


class InvariantViolation(MindmapError):
    """A post-condition failed (e.g. an existing node changed during grow). Always a bug."""
