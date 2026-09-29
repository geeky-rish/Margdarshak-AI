"""
checkpoint.py — Lab 6: Checkpoint manager for run state persistence.

Checkpoints are taken after meaningful state transitions so that a
crashed run can resume from the latest valid checkpoint instead of
restarting from zero.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timezone

from app.models.schemas import CheckpointData, GraphState

_CHECKPOINT_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "checkpoints"


class CheckpointManager:
    """
    Manages checkpoint creation and restoration for pipeline runs.

    Checkpoints are stored as JSON files on disk, keyed by run_id.
    """

    def __init__(self) -> None:
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        self._checkpoints: dict[str, list[CheckpointData]] = {}

    def create_checkpoint(
        self,
        state: GraphState,
        node: str,
    ) -> CheckpointData:
        """Create a checkpoint from the current graph state."""
        # Serialise state but strip large/sensitive objects for storage efficiency
        state_dict = state.model_dump()
        # Remove report_text from final_report to save space
        if state_dict.get("final_report") and state_dict["final_report"].get("report_text"):
            state_dict["final_report"]["report_text"] = "[truncated]"

        cp = CheckpointData(
            checkpoint_id=f"cp_{uuid.uuid4().hex[:12]}",
            run_id=state.run_id,
            batch_id=state.batch_id,
            student_id=state.student_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            node=node,
            state_snapshot=state_dict,
            completed_nodes=list(state.completed_nodes),
        )

        # Store in-memory
        self._checkpoints.setdefault(state.run_id, []).append(cp)

        # Persist to disk
        self._persist_checkpoint(cp)

        return cp

    def get_latest_checkpoint(self, run_id: str) -> CheckpointData | None:
        """Return the most recent valid checkpoint for a run."""
        # Try in-memory first
        checkpoints = self._checkpoints.get(run_id, [])
        if not checkpoints:
            # Try loading from disk
            checkpoints = self._load_from_disk(run_id)
            if checkpoints:
                self._checkpoints[run_id] = checkpoints

        valid = [cp for cp in checkpoints if cp.status == "valid"]
        return valid[-1] if valid else None

    def get_all_checkpoints(self, run_id: str) -> list[CheckpointData]:
        """Return all checkpoints for a run."""
        checkpoints = self._checkpoints.get(run_id, [])
        if not checkpoints:
            checkpoints = self._load_from_disk(run_id)
            if checkpoints:
                self._checkpoints[run_id] = checkpoints
        return checkpoints

    def restore_state(self, run_id: str) -> GraphState | None:
        """Restore a GraphState from the latest valid checkpoint."""
        cp = self.get_latest_checkpoint(run_id)
        if cp is None:
            return None
        try:
            return GraphState(**cp.state_snapshot)
        except Exception:
            return None

    def invalidate_checkpoints(self, run_id: str) -> None:
        """Mark all checkpoints for a run as invalidated."""
        for cp in self._checkpoints.get(run_id, []):
            cp.status = "invalidated"

    def clear(self) -> None:
        """Clear all in-memory checkpoints. For testing."""
        self._checkpoints.clear()

    def _persist_checkpoint(self, cp: CheckpointData) -> None:
        """Write checkpoint to disk."""
        try:
            run_dir = _CHECKPOINT_DIR / cp.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            path = run_dir / f"{cp.checkpoint_id}.json"
            with path.open("w", encoding="utf-8") as fh:
                json.dump(cp.model_dump(), fh, indent=2, default=str)
        except Exception:
            pass  # Never crash the pipeline for checkpoint persistence

    def _load_from_disk(self, run_id: str) -> list[CheckpointData]:
        """Load checkpoints from disk for a run."""
        run_dir = _CHECKPOINT_DIR / run_id
        if not run_dir.exists():
            return []
        checkpoints = []
        for path in sorted(run_dir.glob("cp_*.json")):
            try:
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                checkpoints.append(CheckpointData(**data))
            except Exception:
                continue
        return checkpoints
