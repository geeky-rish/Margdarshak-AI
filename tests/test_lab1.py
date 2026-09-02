"""
test_lab1.py — Tests for Lab 1: Agent Loop (Clarify → Plan → Revise).

Acceptance criteria:
    ✓ Vague request triggers >= 2 clarifying questions.
    ✓ Complete request produces a ClarifiedRequest (no questions).
    ✓ Plan is created from a ClarifiedRequest.
    ✓ Plan can be revised (target_role change, focus_areas change).
    ✓ Locked plan cannot be revised.
    ✓ Revision produces a NEW plan object — original is not mutated.
"""

import pytest

from app.agents.planner_agent import PlannerAgent
from app.models.schemas import (
    ClarificationResponse,
    ClarifiedRequest,
    ReadinessPlan,
)
from app.skills.plan_skill import PlanSkill, PlanSkillInput


@pytest.fixture
def agent() -> PlannerAgent:
    return PlannerAgent()


@pytest.fixture
def skill() -> PlanSkill:
    return PlanSkill()


# ---------------------------------------------------------------------------
# Clarification tests
# ---------------------------------------------------------------------------


class TestClarification:
    def test_vague_request_triggers_at_least_two_questions(self, agent: PlannerAgent):
        """A completely vague request must produce >= 2 clarifying questions."""
        result = agent.clarify("I want to know if I am ready for placements.")
        assert isinstance(result, ClarificationResponse), (
            "Expected ClarificationResponse for a vague request"
        )
        assert len(result.questions) >= 2, (
            f"Expected >= 2 questions but got {len(result.questions)}"
        )

    def test_vague_request_questions_cover_student_id(self, agent: PlannerAgent):
        """Questions must include student_id clarification."""
        result = agent.clarify("I want to know if I am ready for placements.")
        assert isinstance(result, ClarificationResponse)
        fields = [q.field for q in result.questions]
        assert "student_id" in fields, "Missing student_id clarification question"

    def test_vague_request_questions_cover_role(self, agent: PlannerAgent):
        """Questions must include target_role clarification."""
        result = agent.clarify("Tell me about my placement readiness.")
        assert isinstance(result, ClarificationResponse)
        fields = [q.field for q in result.questions]
        assert "target_role" in fields, "Missing target_role clarification question"

    def test_complete_request_returns_clarified(self, agent: PlannerAgent):
        """A request specifying student_id, role, and company returns ClarifiedRequest."""
        request = (
            "Analyse student_001 for Software Engineer role. "
            "Target companies: TCS, Infosys. Focus on DSA."
        )
        result = agent.clarify(request)
        assert isinstance(result, ClarifiedRequest), (
            "Expected ClarifiedRequest for a complete request"
        )
        assert result.student_id == "student_001"

    def test_partial_request_with_student_id_still_asks_for_role(self, agent: PlannerAgent):
        """If student_id is present but role is missing, agent still asks."""
        result = agent.clarify("student_001 wants placement help.")
        assert isinstance(result, ClarificationResponse)


# ---------------------------------------------------------------------------
# Plan creation tests
# ---------------------------------------------------------------------------


class TestPlanCreation:
    def test_plan_created_from_clarified_request(self, agent: PlannerAgent):
        """PlannerAgent creates a ReadinessPlan from a ClarifiedRequest."""
        clarified = ClarifiedRequest(
            student_id="student_001",
            target_role="Software Engineer",
        )
        plan = agent.create_plan(clarified)
        assert isinstance(plan, ReadinessPlan)
        assert plan.student_id == "student_001"
        assert plan.target_role == "Software Engineer"
        assert plan.status == "draft"
        assert len(plan.steps) >= 5, "Plan should have at least 5 workflow steps"

    def test_plan_skill_creates_plan(self, skill: PlanSkill):
        """PlanSkill wraps plan creation correctly."""
        plan = skill.create_readiness_plan(
            PlanSkillInput(student_id="student_002", target_role="Data Analyst")
        )
        assert plan.student_id == "student_002"
        assert plan.target_role == "Data Analyst"
        assert plan.status == "draft"

    def test_plan_has_unique_id(self, agent: PlannerAgent):
        """Each plan gets a unique plan_id."""
        c = ClarifiedRequest(student_id="student_001", target_role="Software Engineer")
        plan1 = agent.create_plan(c)
        plan2 = agent.create_plan(c)
        assert plan1.plan_id != plan2.plan_id


# ---------------------------------------------------------------------------
# Plan revision tests
# ---------------------------------------------------------------------------


class TestPlanRevision:
    def test_revise_target_role(self, agent: PlannerAgent):
        """User can change the target role and the plan updates accordingly."""
        clarified = ClarifiedRequest(
            student_id="student_001", target_role="Software Engineer"
        )
        plan = agent.create_plan(clarified)
        assert plan.target_role == "Software Engineer"

        revised = agent.revise_plan(plan, {"target_role": "Data Analyst"})
        assert revised.target_role == "Data Analyst"

    def test_revise_does_not_mutate_original(self, agent: PlannerAgent):
        """Revision returns a new plan — the original must not change."""
        clarified = ClarifiedRequest(
            student_id="student_001", target_role="Software Engineer"
        )
        original = agent.create_plan(clarified)
        _ = agent.revise_plan(original, {"target_role": "ML Engineer"})
        # Original must be unchanged
        assert original.target_role == "Software Engineer"

    def test_revise_focus_areas(self, agent: PlannerAgent):
        """Focus areas can be updated via revision."""
        clarified = ClarifiedRequest(
            student_id="student_001", target_role="Software Engineer"
        )
        plan = agent.create_plan(clarified)
        revised = agent.revise_plan(plan, {"focus_areas": ["DSA", "OS"]})
        assert "DSA" in revised.focus_areas
        assert "OS" in revised.focus_areas

    def test_locked_plan_cannot_be_revised(self, agent: PlannerAgent, skill: PlanSkill):
        """A locked plan raises ValueError when revision is attempted."""
        clarified = ClarifiedRequest(
            student_id="student_001", target_role="Software Engineer"
        )
        plan = agent.create_plan(clarified)
        locked = skill.lock_plan(plan)
        assert locked.status == "locked"

        with pytest.raises(ValueError, match="locked"):
            agent.revise_plan(locked, {"target_role": "Data Analyst"})


# ---------------------------------------------------------------------------
# Loop Compliance Tests (Lab 1 Rubric)
# ---------------------------------------------------------------------------


class TestAgentLoopCompliance:
    def test_goal_is_modeled_as_data(self, agent: PlannerAgent):
        """Goal must be a checkable data structure (dict with fields)."""
        assert isinstance(agent.goal, dict)
        assert "student_id" in agent.goal
        assert "target_role" in agent.goal
        assert "plan_generated" in agent.goal

    def test_stopping_condition_declared(self, agent: PlannerAgent):
        """satisfied() must evaluate stopping condition goal['plan_generated']."""
        assert agent.satisfied() is False
        agent.goal["plan_generated"] = True
        assert agent.satisfied() is True

    def test_run_populates_iteration_log(self, agent: PlannerAgent):
        """run() must execute loop and populate iteration log with step data."""
        plan = agent.run()
        assert plan.student_id == "student_001"
        assert len(agent.log) >= 3
        for entry in agent.log:
            assert "iteration" in entry
            assert "planned" in entry
            assert "action" in entry
            assert "stopped" in entry

    def test_revise_appends_to_log_without_restarting(self, agent: PlannerAgent):
        """revise_plan() must append revision entries to existing log."""
        plan = agent.run()
        initial_log_count = len(agent.log)
        _ = agent.revise_plan(plan, {"target_role": "Data Analyst"})
        assert len(agent.log) == initial_log_count + 2
        assert agent.log[-1]["stopped"] is True

