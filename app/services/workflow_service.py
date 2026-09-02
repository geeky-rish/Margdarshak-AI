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

    Lab 2 tool calling discipline:
        - Central choke-point: call_tool() logs tool, reason, input, output.
        - Error checking: raises RuntimeError if tool result dict contains an 'error' key.
        - Trace log: preserved in self.trace and state.tool_results.
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
        self.trace: list[dict[str, Any]] = []

    def call_tool(self, tool_name: str, reason: str, func, **kwargs) -> Any:
        """
        Single choke point through which every tool call passes (Lab 2 discipline).

        Logs: tool_name, reason, input, output.
        Raises: RuntimeError if output dict contains an 'error' key.
        """
        raw_result = func(**kwargs)

        # Normalise output for trace logging & contract check
        if hasattr(raw_result, "model_dump"):
            result_dict = {"result": raw_result.model_dump()}
        elif isinstance(raw_result, dict):
            result_dict = raw_result
        else:
            result_dict = {"result": str(raw_result)}

        entry = {
            "tool": tool_name,
            "reason": reason,
            "input": {k: str(v) if not isinstance(v, (int, float, bool, str)) else v for k, v in kwargs.items()},
            "output": result_dict,
        }
        self.trace.append(entry)

        if isinstance(result_dict, dict) and "error" in result_dict:
            raise RuntimeError(f"Tool {tool_name} failed: {result_dict['error']}")

        return raw_result

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

        # ── Step 1: Fetch data via central tool choke-point (Lab 2 & Lab 5) ──
        profile = self.call_tool(
            "get_student_profile",
            "Fetch student profile data via PlacementConnector",
            get_student_profile,
            student_id=clarified.student_id,
            connector=connector,
        )

        role = self.call_tool(
            "get_role_requirements",
            "Fetch role requirements data via PlacementConnector",
            get_role_requirements,
            role_name=clarified.target_role,
            connector=connector,
        )

        assessment = self.call_tool(
            "get_skill_assessment",
            "Fetch formal skill assessment via PlacementConnector",
            get_skill_assessment,
            student_id=clarified.student_id,
            connector=connector,
        )

        state.tool_results["profile"] = profile.model_dump()
        state.tool_results["role"] = role.model_dump()
        state.tool_results["assessment"] = assessment.model_dump()
        state.tool_results["trace"] = self.trace
        self._session.save(state)

        # ── Step 2: Calculate readiness (Lab 2 deterministic tools) ───────
        analysis = self.call_tool(
            "calculate_readiness",
            "Compute deterministic readiness scores across skill coverage, coding stats, and projects",
            calculate_readiness,
            profile=profile,
            role=role,
            assessment=assessment,
        )
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
