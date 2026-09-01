"""
state.py — Run-state management helpers (Lab 4).

RunState is the short-term memory for one workflow execution. It is created
fresh for every run and is NEVER written to the long-term ChromaDB store.
"""

from __future__ import annotations

import uuid
from app.models.schemas import RunState


def new_run_state(original_request: str) -> RunState:
    """Create a blank RunState for a new workflow execution."""
    return RunState(
        run_id=f"run_{uuid.uuid4().hex[:8]}",
        original_request=original_request,
    )
