"""
test_lab6.py — Tests for Lab 6: Governed Runtime.

Acceptance criteria:
    ✓ Runtime initializes correctly.
    ✓ Budget enforcement works.
    ✓ Audit logging captures step events.
    ✓ Checkpoints are created at meaningful transitions.
    ✓ A run can resume from a checkpoint.
    ✓ Retry limits are enforced.
    ✓ Approval is required before publish.
    ✓ Connector remains the only governed data-access surface.
    ✓ Existing Lab 1–5 tests continue to pass.
"""

import pytest
from datetime import datetime, timezone

from app.models.schemas import (
    AccessContext,
    BudgetConfig,
    GraphState,
    CheckpointData,
)
from app.runtime.audit import AuditLogger
from app.runtime.budget import BudgetTracker, BudgetExhaustedError
from app.runtime.checkpoint import CheckpointManager
from app.runtime.approval import ApprovalGate
from app.runtime.runtime import Runtime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def system_ctx() -> AccessContext:
    return AccessContext(actor_id="system", actor_role="system")


@pytest.fixture
def audit() -> AuditLogger:
    return AuditLogger(persist=False)


@pytest.fixture
def budget() -> BudgetTracker:
    return BudgetTracker(BudgetConfig(max_retries=2, max_agent_calls=10))


@pytest.fixture
def checkpoint_mgr() -> CheckpointManager:
    mgr = CheckpointManager()
    yield mgr
    mgr.clear()


@pytest.fixture
def runtime() -> Runtime:
    return Runtime(
        budget=BudgetConfig(max_retries=2, max_agent_calls=20),
        audit_persist=False,
    )


def _make_test_state(run_id: str = "test_run_001") -> GraphState:
    return GraphState(
        run_id=run_id,
        student_id="student_001",
        target_role="Software Engineer",
    )


# ---------------------------------------------------------------------------
# Audit Logger Tests
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_log_creates_event(self, audit: AuditLogger):
        """Logging creates a structured AuditEvent."""
        event = audit.log(
            run_id="run_001",
            node="test_node",
            action="test_action",
            status="completed",
        )
        assert event.run_id == "run_001"
        assert event.node == "test_node"
        assert event.action == "test_action"
        assert event.status == "completed"
        assert event.event_id.startswith("evt_")

    def test_log_captures_input_output(self, audit: AuditLogger):
        """Audit events capture input and output summaries."""
        event = audit.log(
            run_id="run_001",
            node="resume_agent",
            action="profile_intake",
            input_summary={"student_id": "student_001"},
            output_summary={"profile_loaded": True},
            status="completed",
        )
        assert event.input_summary["student_id"] == "student_001"
        assert event.output_summary["profile_loaded"] is True

    def test_get_events_filters_by_run(self, audit: AuditLogger):
        """Events can be filtered by run_id."""
        audit.log(run_id="run_A", node="n1", action="a1")
        audit.log(run_id="run_B", node="n2", action="a2")
        audit.log(run_id="run_A", node="n3", action="a3")

        events_a = audit.get_events("run_A")
        assert len(events_a) == 2
        assert all(e.run_id == "run_A" for e in events_a)

    def test_failed_step_recorded(self, audit: AuditLogger):
        """Failed/error steps are properly recorded."""
        event = audit.log(
            run_id="run_001",
            node="job_matching",
            action="matching_failed",
            status="failed",
            error="KeyError: role not found",
        )
        assert event.status == "failed"
        assert "KeyError" in event.error


# ---------------------------------------------------------------------------
# Budget Tracker Tests
# ---------------------------------------------------------------------------


class TestBudgetTracker:
    def test_budget_tracks_calls(self, budget: BudgetTracker):
        """Budget tracker records agent calls."""
        budget.record_agent_call()
        budget.record_agent_call()
        assert budget.agent_calls == 2

    def test_budget_enforces_retry_limit(self):
        """Budget raises when retry limit is exceeded."""
        b = BudgetTracker(BudgetConfig(max_retries=1))
        b.record_retry()
        b.check_limits()  # Should pass (1 <= 1)
        b.record_retry()
        with pytest.raises(BudgetExhaustedError, match="max_retries"):
            b.check_limits()

    def test_budget_enforces_agent_call_limit(self):
        """Budget raises when agent call limit is exceeded."""
        b = BudgetTracker(BudgetConfig(max_agent_calls=2))
        b.record_agent_call()
        b.record_agent_call()
        b.check_limits()  # 2 <= 2
        b.record_agent_call()
        with pytest.raises(BudgetExhaustedError, match="max_agent_calls"):
            b.check_limits()

    def test_can_retry_returns_false_when_exhausted(self):
        """can_retry() returns False when limit reached."""
        b = BudgetTracker(BudgetConfig(max_retries=1))
        assert b.can_retry() is True
        b.record_retry()
        assert b.can_retry() is False

    def test_budget_summary(self, budget: BudgetTracker):
        """Budget summary returns correct structure."""
        summary = budget.summary()
        assert "agent_calls" in summary
        assert "retries" in summary
        assert "elapsed_seconds" in summary


# ---------------------------------------------------------------------------
# Checkpoint Tests
# ---------------------------------------------------------------------------


class TestCheckpointManager:
    def test_create_checkpoint(self, checkpoint_mgr: CheckpointManager):
        """Checkpoint is created with correct metadata."""
        state = _make_test_state()
        cp = checkpoint_mgr.create_checkpoint(state, "resume_agent")
        assert cp.checkpoint_id.startswith("cp_")
        assert cp.run_id == state.run_id
        assert cp.node == "resume_agent"
        assert cp.status == "valid"

    def test_get_latest_checkpoint(self, checkpoint_mgr: CheckpointManager):
        """Latest checkpoint is returned."""
        state = _make_test_state()
        checkpoint_mgr.create_checkpoint(state, "node_1")
        cp2 = checkpoint_mgr.create_checkpoint(state, "node_2")
        latest = checkpoint_mgr.get_latest_checkpoint(state.run_id)
        assert latest is not None
        assert latest.checkpoint_id == cp2.checkpoint_id

    def test_restore_state_from_checkpoint(self, checkpoint_mgr: CheckpointManager):
        """State can be restored from a checkpoint."""
        state = _make_test_state()
        state.completed_nodes = ["resume_agent", "skill_gap_agent"]
        state.placement_score = 72.5
        checkpoint_mgr.create_checkpoint(state, "skill_gap_agent")

        restored = checkpoint_mgr.restore_state(state.run_id)
        assert restored is not None
        assert restored.run_id == state.run_id
        assert restored.student_id == "student_001"
        assert "resume_agent" in restored.completed_nodes
        assert "skill_gap_agent" in restored.completed_nodes
        assert restored.placement_score == 72.5

    def test_restore_skips_completed_work(self, checkpoint_mgr: CheckpointManager):
        """Restored state preserves completed_nodes so work is not duplicated."""
        state = _make_test_state()
        state.completed_nodes = ["resume_agent"]
        checkpoint_mgr.create_checkpoint(state, "resume_agent")

        restored = checkpoint_mgr.restore_state(state.run_id)
        assert "resume_agent" in restored.completed_nodes

    def test_no_checkpoint_returns_none(self, checkpoint_mgr: CheckpointManager):
        """Restoring a non-existent run returns None."""
        assert checkpoint_mgr.restore_state("nonexistent") is None


# ---------------------------------------------------------------------------
# Approval Gate Tests
# ---------------------------------------------------------------------------


class TestApprovalGate:
    def test_submit_requires_validated_status(self):
        """Cannot submit for approval unless status is 'validated'."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "draft"
        with pytest.raises(ValueError, match="validated"):
            gate.submit_for_approval(state)

    def test_submit_for_approval_works(self):
        """Validated state can be submitted for approval."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "validated"
        state = gate.submit_for_approval(state)
        assert state.approval_status == "pending_approval"

    def test_approve_decision(self):
        """Approved decision sets correct status."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "pending_approval"
        state, record = gate.process_decision(
            state, "officer_001", "approved", "Looks good."
        )
        assert state.approval_status == "approved"
        assert record.decision == "approved"
        assert record.reviewer_id == "officer_001"

    def test_reject_decision(self):
        """Rejected decision sets failed status."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "pending_approval"
        state, record = gate.process_decision(
            state, "officer_001", "rejected", "Score too low."
        )
        assert state.approval_status == "rejected"
        assert state.status == "failed"

    def test_edit_requested_decision(self):
        """Edit requested sets edit_requested status."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "pending_approval"
        state, record = gate.process_decision(
            state, "officer_001", "edit_requested", "Fix gaps."
        )
        assert state.approval_status == "edit_requested"

    def test_cannot_publish_without_approval(self):
        """can_publish returns False without approval."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "pending_approval"
        assert gate.can_publish(state) is False

    def test_can_publish_after_approval(self):
        """can_publish returns True after approval."""
        gate = ApprovalGate()
        state = _make_test_state()
        state.approval_status = "approved"
        assert gate.can_publish(state) is True


# ---------------------------------------------------------------------------
# Runtime Integration Tests
# ---------------------------------------------------------------------------


class TestRuntime:
    def test_create_run(self, runtime: Runtime, system_ctx: AccessContext):
        """Runtime creates a run with proper state."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        assert state.run_id.startswith("run_")
        assert state.student_id == "student_001"
        assert state.status == "running"

    def test_create_run_audits_event(self, runtime: Runtime, system_ctx: AccessContext):
        """Run creation is audited."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        events = runtime.audit.get_events(state.run_id)
        assert len(events) >= 1
        assert events[0].action == "run_created"

    def test_create_run_creates_checkpoint(self, runtime: Runtime, system_ctx: AccessContext):
        """Run creation creates an initial checkpoint."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        assert state.checkpoint_id is not None
        cp = runtime.checkpoint_mgr.get_latest_checkpoint(state.run_id)
        assert cp is not None

    def test_execute_step_audits_and_checkpoints(self, runtime: Runtime, system_ctx: AccessContext):
        """Steps are audited and checkpointed."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )

        def dummy_step(s):
            s.placement_score = 75.0
            return s

        state = runtime.execute_step(
            state,
            node="test_node",
            agent="TestAgent",
            action="test_action",
            step_fn=dummy_step,
        )

        assert state.placement_score == 75.0
        assert "test_node" in state.completed_nodes

        events = runtime.audit.get_events(state.run_id)
        actions = [e.action for e in events]
        assert "test_action" in actions
        assert "test_action_completed" in actions

    def test_execute_step_records_failure(self, runtime: Runtime, system_ctx: AccessContext):
        """Failed steps are audited with error info."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )

        def failing_step(s):
            raise ValueError("Something went wrong")

        with pytest.raises(ValueError):
            runtime.execute_step(
                state,
                node="failing_node",
                agent="FailAgent",
                action="fail_action",
                step_fn=failing_step,
            )

        events = runtime.audit.get_events(state.run_id)
        fail_events = [e for e in events if e.status == "failed"]
        assert len(fail_events) >= 1

    def test_publish_requires_approval(self, runtime: Runtime, system_ctx: AccessContext):
        """Cannot publish without approval."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        with pytest.raises(ValueError, match="approval"):
            runtime.publish(state)

    def test_resume_from_checkpoint(self, runtime: Runtime, system_ctx: AccessContext):
        """A run can be resumed from its checkpoint."""
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        run_id = state.run_id

        def step1(s):
            s.placement_score = 80.0
            return s

        state = runtime.execute_step(
            state,
            node="step1",
            agent="TestAgent",
            action="step1_action",
            step_fn=step1,
        )

        # Simulate crash and resume
        del runtime._runs[run_id]
        restored = runtime.resume_run(run_id)
        assert restored is not None
        assert restored.run_id == run_id
        assert "step1" in restored.completed_nodes
        assert restored.placement_score == 80.0

    def test_connector_access_through_runtime(self, runtime: Runtime, system_ctx: AccessContext):
        """Connector is accessed through runtime, not directly."""
        connector = runtime.get_connector(system_ctx)
        profile = connector.get_student_profile("student_001")
        assert profile.student_id == "student_001"
