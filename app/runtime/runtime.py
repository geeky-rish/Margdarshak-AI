"""
runtime.py — Lab 6: Governed Runtime that wraps the entire agent pipeline.

The Runtime binds:
  - Existing skills, tools, memory (Labs 2-4)
  - Existing connector (Lab 5)
  - Audit logging
  - Checkpoints
  - Budgets
  - Approval gates

All execution flows through the Runtime. No agent may bypass it.
"""

from __future__ import annotations

import time
import uuid
import logging
from datetime import datetime, timezone

from app.models.schemas import (
    AccessContext,
    BudgetConfig,
    GraphState,
    ReadinessPlan,
)
from app.connector.placement_connector import PlacementConnector
from app.memory.retrieval_store import RetrievalStore
from app.memory.session_memory import SessionMemory
from app.runtime.audit import AuditLogger
from app.runtime.budget import BudgetTracker, BudgetExhaustedError
from app.runtime.checkpoint import CheckpointManager
from app.runtime.approval import ApprovalGate
from app.skills.plan_skill import PlanSkill, PlanSkillInput

logger = logging.getLogger(__name__)


class Runtime:
    """
    Lab 6 Governed Runtime: wraps all agent execution with audit,
    checkpoints, budgets, and approval gates.

    Usage::

        runtime = Runtime(budget=BudgetConfig(max_retries=3))
        state = runtime.create_run(
            student_id="student_001",
            target_role="Software Engineer",
            context=AccessContext(actor_id="system", actor_role="system"),
        )
    """

    def __init__(
        self,
        budget: BudgetConfig | None = None,
        gates: list[str] | None = None,
        audit_persist: bool = True,
    ) -> None:
        self.audit = AuditLogger(persist=audit_persist)
        self.checkpoint_mgr = CheckpointManager()
        self.budget = BudgetTracker(budget)
        self.approval_gate = ApprovalGate()
        self._gates = gates or ["publish"]

        # Shared infrastructure from Labs 2-5
        self._session = SessionMemory()
        self._retrieval = RetrievalStore()
        self._plan_skill = PlanSkill()

        # Active runs
        self._runs: dict[str, GraphState] = {}

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        student_id: str,
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        batch_id: str | None = None,
        api_key: str | None = None,
    ) -> GraphState:
        """
        Create a new governed run.

        All data access goes through the Lab 5 PlacementConnector.
        """
        run_id = f"run_{uuid.uuid4().hex[:8]}"

        state = GraphState(
            run_id=run_id,
            batch_id=batch_id,
            student_id=student_id,
            target_role=target_role,
            target_companies=target_companies or [],
            focus_areas=focus_areas or [],
        )

        self._runs[run_id] = state

        self.audit.log(
            run_id=run_id,
            node="runtime",
            action="run_created",
            agent="Runtime",
            batch_id=batch_id,
            student_id=student_id,
            input_summary={"target_role": target_role, "student_id": student_id},
            status="started",
        )

        # Checkpoint: run initialization
        cp = self.checkpoint_mgr.create_checkpoint(state, "run_init")
        state.checkpoint_id = cp.checkpoint_id

        return state

    def get_run(self, run_id: str) -> GraphState | None:
        """Retrieve a run's current state."""
        return self._runs.get(run_id)

    def get_all_runs(self) -> dict[str, GraphState]:
        """Return all active runs."""
        return dict(self._runs)

    def resume_run(self, run_id: str) -> GraphState | None:
        """
        Resume a run from its latest checkpoint.

        Returns the restored GraphState, or None if no checkpoint exists.
        """
        state = self.checkpoint_mgr.restore_state(run_id)
        if state is not None:
            self._runs[run_id] = state
            self.audit.log(
                run_id=run_id,
                node="runtime",
                action="run_resumed",
                agent="Runtime",
                student_id=state.student_id,
                input_summary={"resumed_from": state.checkpoint_id, "completed_nodes": state.completed_nodes},
                status="started",
            )
        return state

    # ------------------------------------------------------------------
    # Step execution wrapper
    # ------------------------------------------------------------------

    def execute_step(
        self,
        state: GraphState,
        node: str,
        agent: str,
        action: str,
        step_fn,
        *,
        input_summary: dict | None = None,
        checkpoint: bool = True,
    ) -> GraphState:
        """
        Execute a single pipeline step with full audit, budget checking,
        and checkpointing.

        Args:
            state:         Current graph state.
            node:          Node name (e.g. 'resume_agent').
            agent:         Agent name performing the step.
            action:        Action description.
            step_fn:       Callable(state) -> state that performs the work.
            input_summary: Optional metadata about inputs.
            checkpoint:    Whether to create a checkpoint after this step.

        Returns:
            Updated GraphState.
        """
        # Budget check
        self.budget.check_limits()
        self.budget.record_agent_call()

        # Audit: step started
        self.audit.log(
            run_id=state.run_id,
            node=node,
            action=action,
            agent=agent,
            batch_id=state.batch_id,
            student_id=state.student_id,
            input_summary=input_summary or {},
            status="started",
        )

        start = time.monotonic()
        try:
            state.current_node = node
            state = step_fn(state)
            duration = (time.monotonic() - start) * 1000

            if node not in state.completed_nodes:
                state.completed_nodes.append(node)

            # Audit: step completed
            self.audit.log(
                run_id=state.run_id,
                node=node,
                action=f"{action}_completed",
                agent=agent,
                batch_id=state.batch_id,
                student_id=state.student_id,
                status="completed",
                duration_ms=duration,
            )

            # Checkpoint
            if checkpoint:
                cp = self.checkpoint_mgr.create_checkpoint(state, node)
                state.checkpoint_id = cp.checkpoint_id

            # Update stored state
            self._runs[state.run_id] = state
            return state

        except BudgetExhaustedError:
            raise  # Let budget errors propagate

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            error_msg = f"{type(e).__name__}: {e}"
            state.errors.append(error_msg)

            self.audit.log(
                run_id=state.run_id,
                node=node,
                action=f"{action}_failed",
                agent=agent,
                batch_id=state.batch_id,
                student_id=state.student_id,
                status="failed",
                error=error_msg,
                duration_ms=duration,
            )
            raise

    # ------------------------------------------------------------------
    # Approval integration
    # ------------------------------------------------------------------

    def submit_for_approval(self, state: GraphState) -> GraphState:
        """Submit a validated run for human approval."""
        state = self.approval_gate.submit_for_approval(state)
        self._runs[state.run_id] = state
        self.audit.log(
            run_id=state.run_id,
            node="approval_gate",
            action="submitted_for_approval",
            agent="Runtime",
            student_id=state.student_id,
            status="completed",
            approval_state="pending_approval",
        )
        return state

    def process_approval(
        self,
        run_id: str,
        reviewer_id: str,
        decision: str,
        comments: str = "",
    ) -> GraphState:
        """Process a human approval decision."""
        state = self._runs.get(run_id)
        if state is None:
            raise KeyError(f"Run '{run_id}' not found.")

        state, record = self.approval_gate.process_decision(
            state, reviewer_id, decision, comments
        )
        self._runs[run_id] = state

        self.audit.log(
            run_id=run_id,
            node="approval_gate",
            action=f"approval_{decision}",
            agent="Runtime",
            student_id=state.student_id,
            status="completed",
            approval_state=decision,
            output_summary={"reviewer": reviewer_id, "decision": decision},
        )

        # Checkpoint after approval
        self.checkpoint_mgr.create_checkpoint(state, "approval_processed")

        return state

    def publish(self, state: GraphState) -> GraphState:
        """Publish approved results. ONLY works if approval_status == 'approved'."""
        if not self.approval_gate.can_publish(state):
            raise ValueError(
                f"Cannot publish: approval_status is '{state.approval_status}', "
                f"expected 'approved'. Human approval is required."
            )

        state.approval_status = "published"
        state.status = "published"
        self._runs[state.run_id] = state

        self.audit.log(
            run_id=state.run_id,
            node="governed_publish",
            action="results_published",
            agent="Runtime",
            student_id=state.student_id,
            status="completed",
            approval_state="published",
        )

        self.checkpoint_mgr.create_checkpoint(state, "published")
        return state

    # ------------------------------------------------------------------
    # Accessors for Lab 2-5 infrastructure
    # ------------------------------------------------------------------

    def get_connector(self, context: AccessContext) -> PlacementConnector:
        """Get a governed connector. All data access MUST go through this."""
        return PlacementConnector(context)

    def get_retrieval_store(self) -> RetrievalStore:
        """Access Lab 4 long-term memory."""
        return self._retrieval

    def get_session_memory(self) -> SessionMemory:
        """Access Lab 4 short-term memory."""
        return self._session

    def get_plan_skill(self) -> PlanSkill:
        """Access Lab 3 plan skill."""
        return self._plan_skill
