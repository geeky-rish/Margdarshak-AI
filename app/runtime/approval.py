"""
approval.py — Lab 6: Approval gate for human-in-the-loop review.

The approval gate enforces that AI-generated readiness scores and
recommendations remain DRAFT until a human placement officer/mentor
explicitly approves, edits, or rejects them.

AI must NEVER silently publish final results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.schemas import ApprovalRecord, GraphState


class ApprovalGate:
    """
    Human-in-the-loop approval gate.

    State machine:
        DRAFT → VALIDATED → PENDING_APPROVAL → APPROVED → PUBLISHED
                                             → EDIT_REQUESTED → (revise) → VALIDATED
                                             → REJECTED
    """

    def __init__(self) -> None:
        self._records: dict[str, list[ApprovalRecord]] = {}

    def submit_for_approval(self, state: GraphState) -> GraphState:
        """
        Move a validated run to PENDING_APPROVAL status.

        Raises:
            ValueError: if state is not in 'validated' status.
        """
        if state.approval_status != "validated":
            raise ValueError(
                f"Cannot submit for approval: current status is '{state.approval_status}', "
                f"expected 'validated'."
            )
        state.approval_status = "pending_approval"
        state.status = "pending_approval"
        return state

    def process_decision(
        self,
        state: GraphState,
        reviewer_id: str,
        decision: str,
        comments: str = "",
    ) -> tuple[GraphState, ApprovalRecord]:
        """
        Process a human reviewer's decision.

        Args:
            state:       Current graph state (must be pending_approval).
            reviewer_id: ID of the placement officer/mentor.
            decision:    One of 'approved', 'rejected', 'edit_requested', 'override'.
            comments:    Optional reviewer comments.

        Returns:
            (updated_state, approval_record)

        Raises:
            ValueError: if state is not pending_approval or decision is invalid.
        """
        if state.approval_status != "pending_approval":
            raise ValueError(
                f"Cannot process approval: current status is '{state.approval_status}', "
                f"expected 'pending_approval'."
            )

        valid_decisions = {"approved", "rejected", "edit_requested", "override"}
        if decision not in valid_decisions:
            raise ValueError(f"Invalid decision '{decision}'. Must be one of {valid_decisions}.")

        previous = state.approval_status

        status_map = {
            "approved": "approved",
            "rejected": "rejected",
            "edit_requested": "edit_requested",
            "override": "approved",  # override = force approve
        }
        state.approval_status = status_map[decision]
        state.reviewer_feedback = comments

        if decision in ("approved", "override"):
            state.status = "approved"
        elif decision == "rejected":
            state.status = "failed"

        record = ApprovalRecord(
            approval_id=f"appr_{uuid.uuid4().hex[:8]}",
            run_id=state.run_id,
            student_id=state.student_id,
            reviewer_id=reviewer_id,
            decision=decision,
            timestamp=datetime.now(timezone.utc).isoformat(),
            comments=comments,
            previous_status=previous,
            resulting_status=state.approval_status,
        )

        state.approval_record = record
        self._records.setdefault(state.run_id, []).append(record)

        return state, record

    def get_records(self, run_id: str) -> list[ApprovalRecord]:
        """Return all approval records for a run."""
        return self._records.get(run_id, [])

    def can_publish(self, state: GraphState) -> bool:
        """Check if a run is approved and ready for publication."""
        return state.approval_status == "approved"

    def clear(self) -> None:
        """Clear all records. For testing."""
        self._records.clear()
