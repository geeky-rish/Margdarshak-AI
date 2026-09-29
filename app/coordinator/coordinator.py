"""
coordinator.py — PlacementCoordinator: the top-level agent controller.

The coordinator manages the full agent loop:

    receive request
        → clarify (Lab 1)
        → if incomplete: return questions
        → execute full workflow (Labs 2–5, or Labs 6–8 graph)
        → return structured report

It is the only public-facing agent entrypoint. All other components
(tools, skills, memory, connector) are accessed through it.

Labs 6–8 adds:
    - Governed runtime (Lab 6)
    - Agentic node graph (Lab 7)
    - Parallel batch execution (Lab 8)
"""

from __future__ import annotations

from typing import Union

from app.agents.planner_agent import PlannerAgent
from app.memory.retrieval_store import RetrievalStore
from app.memory.session_memory import SessionMemory
from app.models.schemas import (
    AccessContext,
    BatchResult,
    BudgetConfig,
    ClarificationResponse,
    ClarifiedRequest,
    GraphState,
    ReadinessReport,
    RunState,
)
from app.services.workflow_service import WorkflowService
from app.graph.graph import PlacementGraph
from app.swarm.batch_runner import BatchRunner


class PlacementCoordinator:
    """
    Top-level coordinator for the Placement Readiness & Career Intelligence Portal.

    Responsibilities:
        1. Accept raw or structured requests.
        2. Clarify vague requests using PlannerAgent (Lab 1).
        3. Execute the full Labs 1–5 workflow via WorkflowService (backward compat).
        4. Execute the full Labs 6–8 graph pipeline (new).
        5. Execute parallel batch runs for multiple students (Lab 8).
        6. Return either clarification questions or a complete report.

    Usage::

        coordinator = PlacementCoordinator()

        # Labs 1-5 (backward compatible)
        state, report = coordinator.run(
            student_id="student_001",
            target_role="Software Engineer",
            context=AccessContext(actor_id="system", actor_role="system"),
        )

        # Lab 7 full graph
        graph_state = coordinator.run_graph(
            student_id="student_001",
            target_role="Software Engineer",
            context=AccessContext(actor_id="system", actor_role="system"),
        )

        # Lab 8 batch
        batch_result = coordinator.run_batch(
            student_ids=["student_001", "student_002"],
            target_role="Software Engineer",
            context=AccessContext(actor_id="system", actor_role="system"),
        )
    """

    def __init__(self, budget: BudgetConfig | None = None) -> None:
        self._planner = PlannerAgent()
        self._session = SessionMemory()
        self._retrieval = RetrievalStore()
        self._workflow = WorkflowService(
            session_memory=self._session,
            retrieval_store=self._retrieval,
        )
        # Lab 7: placement graph
        self._graph = PlacementGraph(budget=budget)
        # Lab 8: batch runner
        self._batch_runner = BatchRunner(budget=budget)

    # ------------------------------------------------------------------
    # Clarification endpoint (Lab 1)
    # ------------------------------------------------------------------

    def clarify_request(
        self, raw_request: str, api_key: str | None = None
    ) -> Union[ClarificationResponse, ClarifiedRequest]:
        """
        Run the clarification step of the agent loop.

        Args:
            raw_request: Free-text request from the user.
            api_key:     Optional custom user API key.

        Returns:
            ClarificationResponse — if questions are needed.
            ClarifiedRequest      — if the request is already complete.
        """
        return self._planner.clarify(raw_request, api_key=api_key)

    # ------------------------------------------------------------------
    # Full run (Labs 1–5 combined) — BACKWARD COMPATIBLE
    # ------------------------------------------------------------------

    def run(
        self,
        student_id: str,
        target_role: str,
        context: AccessContext,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        api_key: str | None = None,
    ) -> tuple[RunState, ReadinessReport]:
        """
        Execute the complete placement readiness workflow (Labs 1–5).

        This method is preserved for backward compatibility. For the full
        Labs 6-8 pipeline, use `run_graph()` instead.

        Args:
            student_id:       Unique student identifier.
            target_role:      Target placement role.
            context:          Access context for authorization.
            target_companies: Optional company preferences.
            focus_areas:      Optional skill focus areas.
            api_key:          Optional custom user API key.

        Returns:
            (RunState, ReadinessReport) — final run state and formatted report.
        """
        clarified = ClarifiedRequest(
            student_id=student_id,
            target_role=target_role,
            target_companies=target_companies or [],
            focus_areas=focus_areas or [],
        )
        return self._workflow.execute(clarified, context, api_key=api_key)

    # ------------------------------------------------------------------
    # Lab 7: Full graph pipeline
    # ------------------------------------------------------------------

    def run_graph(
        self,
        student_id: str,
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        api_key: str | None = None,
        resume_from_run_id: str | None = None,
    ) -> GraphState:
        """
        Execute the complete Labs 6-8 agentic node graph.

        Pipeline:
            Resume Agent → Skill Gap + Coding Analytics → Job Matching
            → Interview → Validation → Approval → Publish

        All execution goes through the Lab 6 Runtime with audit, checkpoints,
        and budgets. All data access goes through the Lab 5 connector.

        Args:
            student_id:         Student to analyse.
            target_role:        Target role.
            context:            Access context.
            target_companies:   Optional company preferences.
            focus_areas:        Optional focus areas.
            api_key:            Optional LLM API key.
            resume_from_run_id: Resume from a checkpointed run.

        Returns:
            Final GraphState with all results.
        """
        return self._graph.execute(
            student_id=student_id,
            target_role=target_role,
            context=context,
            target_companies=target_companies,
            focus_areas=focus_areas,
            api_key=api_key,
            resume_from_run_id=resume_from_run_id,
        )

    # ------------------------------------------------------------------
    # Lab 7: Approval and publish
    # ------------------------------------------------------------------

    def approve_run(
        self,
        run_id: str,
        reviewer_id: str,
        decision: str,
        comments: str = "",
    ) -> GraphState:
        """Process a human approval decision on a graph run."""
        return self._graph.approve(run_id, reviewer_id, decision, comments)

    def publish_run(self, run_id: str) -> GraphState:
        """Publish approved graph run results."""
        return self._graph.publish(run_id)

    def get_graph_run(self, run_id: str) -> GraphState | None:
        """Retrieve a graph run's current state."""
        return self._graph.runtime.get_run(run_id)

    def get_run_audit(self, run_id: str) -> list:
        """Retrieve audit events for a graph run."""
        return self._graph.runtime.audit.get_events(run_id)

    # ------------------------------------------------------------------
    # Lab 8: Batch execution
    # ------------------------------------------------------------------

    def run_batch(
        self,
        student_ids: list[str],
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        api_key: str | None = None,
        max_concurrency: int = 5,
    ) -> BatchResult:
        """
        Execute the placement pipeline for multiple students concurrently.

        Each student gets independent state, audit, and checkpoints.
        One student's failure does not affect others.

        Args:
            student_ids:      List of student IDs.
            target_role:      Target role for all students.
            context:          Access context (must be officer/system).
            target_companies: Optional company preferences.
            focus_areas:      Optional focus areas.
            api_key:          Optional LLM API key.
            max_concurrency:  Max parallel student pipelines.

        Returns:
            BatchResult with per-student results and aggregate metrics.
        """
        return self._batch_runner.run_batch_sync(
            student_ids=student_ids,
            target_role=target_role,
            context=context,
            target_companies=target_companies,
            focus_areas=focus_areas,
            api_key=api_key,
            max_concurrency=max_concurrency,
        )

    def get_batch_result(self, batch_id: str) -> BatchResult | None:
        """Retrieve a batch result by ID."""
        return self._batch_runner.get_batch_result(batch_id)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_session(self) -> SessionMemory:
        """Expose the session memory (for debugging/testing)."""
        return self._session

    def get_retrieval_store(self) -> RetrievalStore:
        """Expose the retrieval store (for testing)."""
        return self._retrieval

    def get_graph(self) -> PlacementGraph:
        """Expose the placement graph (for testing)."""
        return self._graph

