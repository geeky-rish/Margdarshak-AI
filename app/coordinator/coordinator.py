"""
coordinator.py — PlacementCoordinator: the top-level agent controller.

The coordinator manages the full agent loop:

    receive request
        → clarify (Lab 1)
        → if incomplete: return questions
        → execute full workflow (Labs 2–5)
        → return structured report

It is the only public-facing agent entrypoint. All other components
(tools, skills, memory, connector) are accessed through it.
"""

from __future__ import annotations

from typing import Union

from app.agents.planner_agent import PlannerAgent
from app.memory.retrieval_store import RetrievalStore
from app.memory.session_memory import SessionMemory
from app.models.schemas import (
    AccessContext,
    ClarificationResponse,
    ClarifiedRequest,
    ReadinessReport,
    RunState,
)
from app.services.workflow_service import WorkflowService


class PlacementCoordinator:
    """
    Top-level coordinator for the Placement Readiness & Career Intelligence Portal.

    Responsibilities:
        1. Accept raw or structured requests.
        2. Clarify vague requests using PlannerAgent (Lab 1).
        3. Execute the full Labs 1–5 workflow via WorkflowService.
        4. Return either clarification questions or a complete ReadinessReport.

    Usage::

        coordinator = PlacementCoordinator()
        result = coordinator.run(
            student_id="student_001",
            target_role="Software Engineer",
            context=AccessContext(actor_id="system", actor_role="system"),
        )
    """

    def __init__(self) -> None:
        self._planner = PlannerAgent()
        self._session = SessionMemory()
        self._retrieval = RetrievalStore()
        self._workflow = WorkflowService(
            session_memory=self._session,
            retrieval_store=self._retrieval,
        )

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
    # Full run (Labs 1–5 combined)
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
        Execute the complete placement readiness workflow.

        Assumes the request has already been clarified (i.e., student_id and
        target_role are known). Use `clarify_request()` first for vague inputs.

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

    def get_session(self) -> SessionMemory:
        """Expose the session memory (for debugging/testing)."""
        return self._session

    def get_retrieval_store(self) -> RetrievalStore:
        """Expose the retrieval store (for testing)."""
        return self._retrieval
