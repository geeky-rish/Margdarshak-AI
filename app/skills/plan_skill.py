"""
plan_skill.py — Lab 3: Reusable PlanSkill.

PlanSkill wraps the PlannerAgent's plan creation in a typed, reusable interface.
It works for any valid (student_id, target_role) combination without modification.

Usage::

    skill = PlanSkill()
    plan = skill.create_readiness_plan(PlanSkillInput(
        student_id="student_001",
        target_role="Software Engineer",
    ))
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.agents.planner_agent import PlannerAgent
from app.models.schemas import ClarifiedRequest, ReadinessPlan


class PlanSkillInput(BaseModel):
    """Typed input for PlanSkill."""

    student_id: str
    target_role: str
    target_companies: list[str] = []
    focus_areas: list[str] = []


class PlanSkill:
    """
    Lab 3 reusable skill: creates a ReadinessPlan for any student/role pair.

    The skill is stateless — it delegates plan creation to PlannerAgent and
    returns a typed ReadinessPlan. Calling code never needs to know about
    the internal agent.
    """

    def __init__(self) -> None:
        self._agent = PlannerAgent()

    def create_readiness_plan(
        self, inputs: PlanSkillInput, api_key: str | None = None
    ) -> ReadinessPlan:
        """
        Create a ReadinessPlan for the given student and target role.

        Args:
            inputs: PlanSkillInput specifying student_id and target_role.
            api_key: Optional custom user API key.

        Returns:
            A ReadinessPlan in 'draft' status, ready for execution or revision.
        """
        clarified = ClarifiedRequest(
            student_id=inputs.student_id,
            target_role=inputs.target_role,
            target_companies=inputs.target_companies,
            focus_areas=inputs.focus_areas,
        )
        return self._agent.create_plan(clarified, api_key=api_key)

    def lock_plan(self, plan: ReadinessPlan) -> ReadinessPlan:
        """Lock a draft plan so it is committed for execution."""
        return self._agent.lock_plan(plan)
