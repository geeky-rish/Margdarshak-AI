"""
session_memory.py — Lab 4: Short-term in-process run state store.

RunState lives only for the duration of a single workflow execution. This
module provides a lightweight in-process dictionary that maps run_id →
RunState. It is intentionally NOT backed by any database so that there is
zero risk of accidentally persisting run-scoped data into the long-term store.

The store is reset whenever the process restarts — by design.
"""

from __future__ import annotations

from app.models.schemas import RunState


class SessionMemory:
    """
    In-process, ephemeral store for RunState objects.

    One SessionMemory instance is shared per application lifetime (injected
    via dependency injection in workflow_service and coordinator). It never
    touches ChromaDB or any disk-based storage.
    """

    def __init__(self) -> None:
        self._store: dict[str, RunState] = {}

    def save(self, state: RunState) -> None:
        """Persist a RunState in memory for the current process lifetime."""
        self._store[state.run_id] = state

    def get(self, run_id: str) -> RunState | None:
        """Retrieve a RunState by run_id. Returns None if not found."""
        return self._store.get(run_id)

    def delete(self, run_id: str) -> None:
        """Remove a RunState. Called at the end of a completed workflow."""
        self._store.pop(run_id, None)

    def all_run_ids(self) -> list[str]:
        """Return all active run IDs (useful for debugging)."""
        return list(self._store.keys())

    def clear(self) -> None:
        """Clear all run states. Intended for tests only."""
        self._store.clear()
