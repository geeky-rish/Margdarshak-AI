"""
workflow_service.py — Orchestrates the complete Labs 1–5 workflow.

This service is the single executable sequence for a full placement readiness
run. It connects every lab component in the correct order:

    Clarify (Lab 1)
        → Plan (Lab 1)
        → Connector data access (Lab 5)
        → Tool calls: readiness calculation (Lab 2)
        → PlanSkill (Lab 3)
        → Memory retrieval (Lab 4)
        → FormatSkill (Lab 3)
        → Structured report

WorkflowService is stateless — all run state is carried in a RunState object
that is passed explicitly and stored in SessionMemory.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.memory.retrieval_store import RetrievalStore
from app.memory.session_memory import SessionMemory
from app.models.schemas import (
    AccessContext,
    ClarifiedRequest,
    ReadinessReport,
    RunState,
)
from app.models.state import new_run_state
from app.skills.format_skill import FormatSkill
from app.skills.plan_skill import PlanSkill, PlanSkillInput
from app.tools.readiness_tools import calculate_readiness, get_skill_assessment
from app.tools.profile_tools import get_student_profile
from app.tools.role_tools import get_role_requirements


class WorkflowService:
    """
    Runs the full Labs 1–5 placement readiness workflow for a given
    ClarifiedRequest.

    Dependencies are injected so they can be swapped in tests.
    """

    def __init__(
        self,
        session_memory: SessionMemory,
        retrieval_store: RetrievalStore,
    ) -> None:
        self._session = session_memory
        self._retrieval = retrieval_store
        self._plan_skill = PlanSkill()
        self._format_skill = FormatSkill()

    def execute(
        self,
        clarified: ClarifiedRequest,
        context: AccessContext,
        api_key: str | None = None,
    ) -> tuple[RunState, ReadinessReport]:
        """
        Execute the full workflow for a clarified placement readiness request.

        Args:
            clarified: A fully specified ClarifiedRequest (from Lab 1 clarification).
            context:   AccessContext for PlacementConnector authorization.
            api_key:   Optional custom user API key.

        Returns:
            (RunState, ReadinessReport) — the final run state and formatted report.
        """
        # ── Initialize run state (Lab 4: short-term memory) ──────────────
        state = new_run_state(
            original_request=(
                f"student_id={clarified.student_id} "
                f"target_role={clarified.target_role}"
            )
        )
        state.clarified_request = clarified
        self._session.save(state)

        # ── Create connector (Lab 5) ──────────────────────────────────────
        connector = PlacementConnector(context)

        # ── Step 1: Fetch data via connector (Lab 5 governs all access) ───
        profile = get_student_profile(clarified.student_id, connector)
        role = get_role_requirements(clarified.target_role, connector)
        assessment = get_skill_assessment(clarified.student_id, connector)

        state.tool_results["profile"] = profile.model_dump()
        state.tool_results["role"] = role.model_dump()
        state.tool_results["assessment"] = assessment.model_dump()
        self._session.save(state)

        # ── Step 2: Calculate readiness (Lab 2 deterministic tools) ───────
        analysis = calculate_readiness(profile, role, assessment)
        state.current_analysis = analysis
        self._session.save(state)

        # ── Step 3: Build plan via PlanSkill (Lab 3) ──────────────────────
        plan = self._plan_skill.create_readiness_plan(
            PlanSkillInput(
                student_id=clarified.student_id,
                target_role=clarified.target_role,
                target_companies=clarified.target_companies,
                focus_areas=clarified.focus_areas,
            ),
            api_key=api_key
        )
        plan = self._plan_skill.lock_plan(plan)
        state.current_plan = plan
        self._session.save(state)

        # ── Step 4: Retrieve similar historical cases (Lab 4 long-term) ───
        query = self._build_retrieval_query(profile, role, analysis)
        historical_cases = self._retrieval.retrieve_similar_students(query, k=3)

        # ── Step 5: Format report via FormatSkill (Lab 3) ─────────────────
        report = self._format_skill.format_readiness_report(
            analysis=analysis,
            plan=plan,
            student_name=profile.name,
            historical_cases=historical_cases,
            api_key=api_key,
        )

        return state, report

    @staticmethod
    def _build_retrieval_query(profile, role, analysis) -> str:
        """
        Build a natural language retrieval query from the current student's
        profile and analysis results for similarity search.
        """
        skill_text = ", ".join(
            f"{skill} {level}"
            for skill, level in list(profile.skills.items())[:5]
        )
        gap_text = (
            ", ".join(f"missing {g}" for g in analysis.skill_gaps[:3])
            if analysis.skill_gaps
            else "no major gaps"
        )
        return (
            f"Student targeting {role.role}. "
            f"Skills: {skill_text}. "
            f"Gaps: {gap_text}. "
            f"Readiness score: {analysis.overall_readiness_score:.1f}."
        )
