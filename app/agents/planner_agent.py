"""
planner_agent.py — Lab 1: The Clarify → Plan → Revise agent loop.

This module implements the core agent behaviour that distinguishes an agentic
system from a simple chatbot:

    1. Clarify  — detect missing information and ask targeted questions.
    2. Plan     — produce a structured, editable ReadinessPlan.
    3. Revise   — update the plan in response to user feedback without
                  rewriting the agent.

LLM Integration (optional):
    When GEMINI_API_KEY is set, the agent uses Gemini to intelligently parse
    natural language requests and generate better clarification questions.
    When the key is absent/disabled, the agent falls back to fast deterministic
    heuristics — the system works correctly in both modes.
"""

from __future__ import annotations

import uuid
import logging

logger = logging.getLogger(__name__)
from typing import Union

from app.models.schemas import (
    ClarificationQuestion,
    ClarificationResponse,
    ClarifiedRequest,
    ReadinessPlan,
)

# LLM service — imported lazily to avoid circular imports and startup failures
try:
    from app.services.llm_service import get_llm_service
    _LLM_IMPORT_OK = True
except Exception:
    _LLM_IMPORT_OK = False

# ---------------------------------------------------------------------------
# Known valid roles — used for loose validation during clarification.
# In a production system this list comes from the connector.
# ---------------------------------------------------------------------------
_KNOWN_ROLES = {
    "software engineer",
    "data analyst",
    "ml engineer",
    "machine learning engineer",
}

# ---------------------------------------------------------------------------
# Standard workflow steps that form the body of every ReadinessPlan.
# Adding a step here propagates it to ALL plans without touching agent logic.
# ---------------------------------------------------------------------------
_STANDARD_STEPS = [
    "Retrieve student profile via PlacementConnector.",
    "Retrieve target role requirements via PlacementConnector.",
    "Retrieve student skill assessment via PlacementConnector.",
    "Validate profile and role inputs.",
    "Calculate deterministic readiness scores (skill coverage, coding, projects).",
    "Identify skill gaps and strengths.",
    "Retrieve historically similar student cases from long-term memory.",
    "Construct a structured ReadinessPlan.",
    "Format the final placement readiness report via FormatSkill.",
]


class PlannerAgent:
    """
    Lab 1 agent: clarifies vague requests, produces plans, and revises them.

    Lab 1 loop structure:
        goal: Data dict tracking missing requirements and completion state.
        satisfied(): Declared stopping condition (goal["plan_generated"] is True).
        next_step(): Planner deciding whether to ask or generate plan.
        run(): Loop processing steps and building iteration log.
        revise_plan(): Mutates plan and appends revision steps to iteration log.
    """

    def __init__(self) -> None:
        # Goal modeled as data — checkable predicate, not prose
        self.goal: dict[str, Any] = {
            "student_id": None,
            "target_role": None,
            "focus_areas": None,
            "plan_generated": False,
        }
        self.plan: ReadinessPlan | None = None
        self.log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Goal check & Planner Loop
    # ------------------------------------------------------------------

    def satisfied(self) -> bool:
        """Stopping condition declared before the loop runs."""
        return self.goal["plan_generated"] is True

    def next_step(self) -> tuple[str, str | None]:
        """Planner: inspect goal and decide next step."""
        for field in ("student_id", "target_role"):
            if self.goal[field] is None:
                return ("ask", field)
        if self.goal["focus_areas"] is None:
            return ("ask", "focus_areas")
        return ("generate_plan", None)

    def run(
        self,
        answers: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> ReadinessPlan:
        """
        Execute the full Goal → Plan → Act → Observe → Revise loop.
        """
        simulated = {
            "student_id": "student_001",
            "target_role": "Software Engineer",
            "focus_areas": ["DSA", "Operating Systems"],
        }
        answers = answers or simulated

        while not self.satisfied():
            step, arg = self.next_step()

            if step == "ask":
                answer = answers.get(arg)
                self.goal[arg] = answer
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": f"ask for {arg}",
                    "action": f"asked user for {arg}",
                    "observed": answer,
                    "stopped": False,
                })

            elif step == "generate_plan":
                clarified = ClarifiedRequest(
                    student_id=self.goal["student_id"],
                    target_role=self.goal["target_role"],
                    focus_areas=self.goal["focus_areas"] or [],
                )
                self.plan = self.create_plan(clarified, api_key=api_key)
                self.goal["plan_generated"] = True
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": "generate schedule from gathered requirements",
                    "action": "built ReadinessPlan",
                    "observed": {
                        "plan_id": self.plan.plan_id,
                        "student_id": self.plan.student_id,
                        "target_role": self.plan.target_role,
                    },
                    "stopped": True,
                    "stop_reason": "goal['plan_generated'] is now True",
                })

        return self.plan

    # ------------------------------------------------------------------
    # Step 1 — Clarify
    # ------------------------------------------------------------------

    def _try_llm_clarify(
        self, raw: str, api_key: str | None = None
    ) -> Union[ClarificationResponse, ClarifiedRequest, None]:
        """
        Attempt to use Gemini to parse the request.

        Returns None if LLM is unavailable or parsing fails, so the caller
        can seamlessly fall back to deterministic heuristics.
        """
        if not _LLM_IMPORT_OK:
            return None

        llm = get_llm_service(api_key=api_key)
        if not llm.is_available():
            return None

        extracted = llm.clarify_request(raw)
        if not extracted:
            return None

        missing = extracted.get("missing_fields", [])

        # If LLM found all required fields, return a ClarifiedRequest
        if "student_id" not in missing and "target_role" not in missing:
            student_id = extracted.get("student_id") or "student_001"
            target_role = extracted.get("target_role") or "Software Engineer"
            logger.info(
                f"[LLM] Parsed request: student={student_id}, role={target_role}"
            )
            return ClarifiedRequest(
                student_id=student_id,
                target_role=target_role,
                target_companies=extracted.get("target_companies", []),
                focus_areas=extracted.get("focus_areas", []),
            )

        # LLM found missing fields — try to get better questions from it
        enhanced = llm.enhance_clarification_questions(raw, missing)
        if enhanced:
            questions = [
                ClarificationQuestion(
                    field=q.get("field", "unknown"),
                    question=q.get("question", ""),
                )
                for q in enhanced
                if q.get("question")
            ]
            if questions:
                logger.info(f"[LLM] Generated {len(questions)} clarification questions")
                return ClarificationResponse(questions=questions)

        return None  # Fall back to deterministic

    def _detect_missing(self, raw: str) -> list[ClarificationQuestion]:
        """
        Inspect a raw request string and return questions for missing fields.

        Heuristic rules (deterministic, no LLM needed):
            • If no student ID pattern found   → ask for student ID.
            • If no recognisable role name found → ask for target role.
            • If no company mentioned           → ask about company preferences.
        """
        questions: list[ClarificationQuestion] = []
        lower = raw.lower()

        # Detect student ID
        has_student_id = any(
            kw in lower for kw in ["student_", "id:", "student id", "my id"]
        )
        if not has_student_id:
            questions.append(
                ClarificationQuestion(
                    field="student_id",
                    question=(
                        "Which student profile should be analysed? "
                        "Please provide the student ID (e.g., 'student_001')."
                    ),
                )
            )

        # Detect target role
        has_role = any(role in lower for role in _KNOWN_ROLES) or any(
            kw in lower for kw in ["role", "position", "job", "engineer", "analyst"]
        )
        if not has_role:
            questions.append(
                ClarificationQuestion(
                    field="target_role",
                    question=(
                        "What target role are you preparing for? "
                        "Available roles: Software Engineer, Data Analyst, ML Engineer."
                    ),
                )
            )

        # Detect company / focus preferences (always ask if not specified)
        has_company = any(
            kw in lower
            for kw in [
                "company",
                "companies",
                "tcs",
                "infosys",
                "google",
                "amazon",
                "deloitte",
                "focus",
                "priorit",
            ]
        )
        if not has_company:
            questions.append(
                ClarificationQuestion(
                    field="focus_areas",
                    question=(
                        "Are there specific companies or skill areas you would like "
                        "to prioritise (e.g., 'focus on DSA' or 'target TCS and Infosys')? "
                        "Leave blank to use defaults."
                    ),
                )
            )

        return questions

    def clarify(
        self, raw_request: str, api_key: str | None = None
    ) -> Union[ClarificationResponse, ClarifiedRequest]:
        """
        Attempt to clarify a potentially vague request.

        Strategy:
            1. Try Gemini LLM for intelligent parsing (if API key set).
            2. If LLM unavailable/fails, use deterministic heuristics.

        Returns:
            ClarificationResponse — if information is missing (ask questions).
            ClarifiedRequest      — if the request is already fully specified.
        """
        # ── Try LLM-powered clarification first ──────────────────────────
        llm_result = self._try_llm_clarify(raw_request, api_key=api_key)
        if llm_result is not None:
            return llm_result

        # ── Deterministic fallback ────────────────────────────────────────
        logger.debug("[Deterministic] Using heuristic clarification")
        questions = self._detect_missing(raw_request)
        if questions:
            return ClarificationResponse(questions=questions)

        # Request is fully specified — parse it
        return self._parse_complete_request(raw_request)

    def _parse_complete_request(self, raw: str) -> ClarifiedRequest:
        """
        Parse a fully specified request string into a ClarifiedRequest.
        Used only when clarify() determines all fields are present.
        """
        lower = raw.lower()

        # Extract student_id
        student_id = "student_001"  # default fallback
        for token in raw.split():
            if token.startswith("student_"):
                student_id = token.strip(".,;:")
                break

        # Extract role
        target_role = "Software Engineer"  # default
        if "data analyst" in lower:
            target_role = "Data Analyst"
        elif "ml engineer" in lower or "machine learning" in lower:
            target_role = "ML Engineer"
        elif "software engineer" in lower or "software" in lower:
            target_role = "Software Engineer"

        return ClarifiedRequest(
            student_id=student_id,
            target_role=target_role,
        )

    # ------------------------------------------------------------------
    # Step 2 — Plan
    # ------------------------------------------------------------------

    def create_plan(
        self, clarified: ClarifiedRequest, api_key: str | None = None
    ) -> ReadinessPlan:
        """
        Create a structured ReadinessPlan from a ClarifiedRequest.

        The plan always starts as a 'draft' so it can be revised before
        execution.

        Args:
            clarified: A fully specified ClarifiedRequest.
            api_key: Optional custom user API key.

        Returns:
            A ReadinessPlan in 'draft' status.
        """
        steps = list(_STANDARD_STEPS)
        if _LLM_IMPORT_OK:
            try:
                llm = get_llm_service(api_key=api_key)
                if llm.is_available():
                    ai_steps = llm.generate_plan_steps(
                        student_id=clarified.student_id,
                        target_role=clarified.target_role,
                        focus_areas=clarified.focus_areas,
                        target_companies=clarified.target_companies,
                    )
                    if ai_steps:
                        steps = ai_steps
            except Exception as e:
                logger.warning(f"Failed to generate AI plan steps: {e}", exc_info=True)

        return ReadinessPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            student_id=clarified.student_id,
            target_role=clarified.target_role,
            target_companies=clarified.target_companies,
            focus_areas=clarified.focus_areas,
            steps=steps,
            status="draft",
        )

    # ------------------------------------------------------------------
    # Step 3 — Revise
    # ------------------------------------------------------------------

    def revise_plan(self, plan: ReadinessPlan, feedback: dict) -> ReadinessPlan:
        """
        Revise an existing plan based on user feedback.

        Supported feedback keys:
            target_role      (str)  — change the target role.
            target_companies (list) — update company preferences.
            focus_areas      (list) — update skill focus areas.
            lock             (bool) — if True, lock the plan for execution.

        The plan ID is preserved. A new ReadinessPlan is returned (immutable
        update — original plan is NOT mutated).

        Args:
            plan:     The existing ReadinessPlan to revise.
            feedback: A dict containing only the fields to change.

        Returns:
            A revised ReadinessPlan (status resets to 'draft' unless locked).

        Raises:
            ValueError: If the plan is already locked.
        """
        if plan.status == "locked":
            raise ValueError(
                f"Plan '{plan.plan_id}' is locked and cannot be revised. "
                "Create a new plan if changes are needed."
            )

        self.log.append({
            "iteration": len(self.log) + 1,
            "planned": "apply user feedback to existing plan",
            "action": f"feedback received: '{feedback}'",
            "observed": None,
            "stopped": False,
        })

        updated = plan.model_copy(deep=True)

        if "target_role" in feedback:
            updated.target_role = feedback["target_role"]

        if "target_companies" in feedback:
            updated.target_companies = list(feedback["target_companies"])

        if "focus_areas" in feedback:
            updated.focus_areas = list(feedback["focus_areas"])

        if feedback.get("lock"):
            updated.status = "locked"

        self.log.append({
            "iteration": len(self.log) + 1,
            "planned": "confirm revised plan",
            "action": "mutated existing plan (not regenerated from scratch)",
            "observed": {
                "plan_id": updated.plan_id,
                "target_role": updated.target_role,
            },
            "stopped": True,
            "stop_reason": "revision applied without restarting the loop",
        })

        return updated

    def lock_plan(self, plan: ReadinessPlan) -> ReadinessPlan:
        """Convenience method to lock a draft plan for execution."""
        return plan.model_copy(update={"status": "locked"})
