"""
budget.py — Lab 6: Budget tracker for bounded execution.

Enforces configurable limits on retries, agent calls, and execution time.
Prevents unbounded loops and resource exhaustion.
"""

from __future__ import annotations

import time

from app.models.schemas import BudgetConfig


class BudgetExhaustedError(Exception):
    """Raised when a budget limit is exceeded."""

    def __init__(self, limit_name: str, limit_value: float, current_value: float) -> None:
        self.limit_name = limit_name
        self.limit_value = limit_value
        self.current_value = current_value
        super().__init__(
            f"Budget exhausted: {limit_name} limit={limit_value}, current={current_value}"
        )


class BudgetTracker:
    """
    Tracks resource consumption against configurable limits.

    Usage::

        budget = BudgetTracker(BudgetConfig(max_retries=3))
        budget.record_agent_call()
        budget.record_retry()
        budget.check_limits()  # raises BudgetExhaustedError if exceeded
    """

    def __init__(self, config: BudgetConfig | None = None) -> None:
        self._config = config or BudgetConfig()
        self._agent_calls = 0
        self._retries = 0
        self._validation_attempts = 0
        self._start_time = time.monotonic()

    @property
    def config(self) -> BudgetConfig:
        return self._config

    @property
    def agent_calls(self) -> int:
        return self._agent_calls

    @property
    def retries(self) -> int:
        return self._retries

    @property
    def validation_attempts(self) -> int:
        return self._validation_attempts

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def record_agent_call(self) -> None:
        """Record an agent/tool invocation."""
        self._agent_calls += 1

    def record_retry(self) -> None:
        """Record a validation retry."""
        self._retries += 1

    def record_validation_attempt(self) -> None:
        """Record a validation attempt."""
        self._validation_attempts += 1

    def check_limits(self) -> None:
        """
        Check all budget limits. Raises BudgetExhaustedError if any is exceeded.
        """
        if self._retries > self._config.max_retries:
            raise BudgetExhaustedError("max_retries", self._config.max_retries, self._retries)

        if self._agent_calls > self._config.max_agent_calls:
            raise BudgetExhaustedError("max_agent_calls", self._config.max_agent_calls, self._agent_calls)

        if self._validation_attempts > self._config.max_validation_attempts:
            raise BudgetExhaustedError(
                "max_validation_attempts", self._config.max_validation_attempts, self._validation_attempts
            )

        elapsed = self.elapsed_seconds
        if elapsed > self._config.max_execution_seconds:
            raise BudgetExhaustedError("max_execution_seconds", self._config.max_execution_seconds, elapsed)

    def can_retry(self) -> bool:
        """Check if another retry is allowed without raising."""
        return self._retries < self._config.max_retries

    def summary(self) -> dict:
        """Return a budget consumption summary."""
        return {
            "agent_calls": self._agent_calls,
            "agent_calls_limit": self._config.max_agent_calls,
            "retries": self._retries,
            "retries_limit": self._config.max_retries,
            "validation_attempts": self._validation_attempts,
            "validation_limit": self._config.max_validation_attempts,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "time_limit_seconds": self._config.max_execution_seconds,
        }

    def reset(self) -> None:
        """Reset all counters. For testing."""
        self._agent_calls = 0
        self._retries = 0
        self._validation_attempts = 0
        self._start_time = time.monotonic()
