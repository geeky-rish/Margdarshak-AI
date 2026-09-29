"""
test_lab7.py — Tests for Lab 7: Agentic Node Graph.

Acceptance criteria:
    ✓ Graph executes the complete pipeline.
    ✓ Each agent node produces correct output.
    ✓ State transitions are explicit and typed.
    ✓ Validation gate works.
    ✓ Validation failure triggers bounded regeneration.
    ✓ Approval gate blocks publish.
    ✓ Publish only after approval.
    ✓ Audit trail is complete.
    ✓ Connector is the only data access surface.
"""

import pytest

from app.models.schemas import (
    AccessContext,
    BudgetConfig,
    GraphState,
    StudentProfile,
)
from app.graph.graph import PlacementGraph
from app.agents.resume_agent import ResumeAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.coding_analytics_agent import CodingAnalyticsAgent
from app.agents.job_matching_agent import JobMatchingAgent
from app.agents.interview_agent import InterviewAgent
from app.agents.validation_agent import ValidationAgent
from app.connector.placement_connector import PlacementConnector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def system_ctx() -> AccessContext:
    return AccessContext(actor_id="system", actor_role="system")


@pytest.fixture
def connector(system_ctx: AccessContext) -> PlacementConnector:
    return PlacementConnector(system_ctx)


@pytest.fixture
def graph() -> PlacementGraph:
    return PlacementGraph(
        budget=BudgetConfig(max_retries=2, max_agent_calls=50),
    )


def _make_state(student_id: str = "student_001") -> GraphState:
    return GraphState(
        run_id="test_run",
        student_id=student_id,
        target_role="Software Engineer",
    )


# ---------------------------------------------------------------------------
# Individual Agent Tests
# ---------------------------------------------------------------------------


class TestResumeAgent:
    def test_process_loads_profile(self, connector: PlacementConnector):
        """Resume agent loads profile and validates consent."""
        agent = ResumeAgent()
        state = _make_state()
        state = agent.process(state, connector)

        assert state.profile is not None
        assert state.profile.student_id == "student_001"
        assert state.consent is True
        assert state.resume_summary["name"] == "Arjun Mehta"

    def test_process_builds_resume_summary(self, connector: PlacementConnector):
        """Resume agent builds a structured summary."""
        agent = ResumeAgent()
        state = _make_state()
        state = agent.process(state, connector)

        assert "top_skills" in state.resume_summary
        assert "projects_count" in state.resume_summary
        assert state.resume_summary["projects_count"] >= 1


class TestSkillGapAgent:
    def test_skill_gap_analysis(self, connector: PlacementConnector):
        """Skill gap agent identifies gaps against role requirements."""
        resume_agent = ResumeAgent()
        state = _make_state()
        state = resume_agent.process(state, connector)

        agent = SkillGapAgent()
        state = agent.process(state, connector)

        assert "current_skills" in state.skill_gap
        assert "missing_skills" in state.skill_gap
        assert "coverage_score" in state.skill_gap
        assert "benchmark_source" in state.skill_gap

    def test_skill_gap_requires_profile(self, connector: PlacementConnector):
        """Skill gap agent raises if profile not loaded."""
        agent = SkillGapAgent()
        state = _make_state()
        with pytest.raises(ValueError, match="profile"):
            agent.process(state, connector)


class TestCodingAnalyticsAgent:
    def test_coding_analytics(self, connector: PlacementConnector):
        """Coding analytics agent produces scores and trends."""
        resume_agent = ResumeAgent()
        state = _make_state()
        state = resume_agent.process(state, connector)

        agent = CodingAnalyticsAgent()
        state = agent.process(state, connector)

        assert "coding_score" in state.coding_analytics
        assert "project_score" in state.coding_analytics
        assert "problem_solving_trend" in state.coding_analytics


class TestJobMatchingAgent:
    def test_job_matching(self, connector: PlacementConnector):
        """Job matching agent calculates readiness using Lab 2 formula."""
        state = _make_state()
        state = ResumeAgent().process(state, connector)
        state = SkillGapAgent().process(state, connector)
        state = CodingAnalyticsAgent().process(state, connector)

        agent = JobMatchingAgent()
        state = agent.process(state, connector)

        assert state.readiness_analysis is not None
        assert state.placement_score > 0
        assert 0 <= state.match_confidence <= 1.0
        assert len(state.company_matches) > 0
        assert state.match_reasoning != ""

    def test_scoring_uses_lab2_formula(self, connector: PlacementConnector):
        """Job matching preserves the existing Lab 2 scoring formula."""
        from app.tools.readiness_tools import calculate_readiness

        state = _make_state()
        state = ResumeAgent().process(state, connector)

        role = connector.get_role_requirements("Software Engineer")
        assessment = connector.get_skill_assessment("student_001")
        expected = calculate_readiness(state.profile, role, assessment)

        state = SkillGapAgent().process(state, connector)
        state = CodingAnalyticsAgent().process(state, connector)
        state = JobMatchingAgent().process(state, connector)

        assert state.readiness_analysis.overall_readiness_score == expected.overall_readiness_score


class TestInterviewAgent:
    def test_interview_generates_roadmap(self, connector: PlacementConnector):
        """Interview agent generates roadmap from actual gaps."""
        state = _make_state()
        state = ResumeAgent().process(state, connector)
        state = SkillGapAgent().process(state, connector)
        state = CodingAnalyticsAgent().process(state, connector)
        state = JobMatchingAgent().process(state, connector)

        agent = InterviewAgent()
        state = agent.process(state)

        assert len(state.learning_roadmap) > 0
        assert state.interview_results.get("ai_generated") is True


class TestValidationAgent:
    def test_complete_state_passes_validation(self, connector: PlacementConnector):
        """A fully populated state passes validation."""
        state = _make_state()
        state = ResumeAgent().process(state, connector)
        state = SkillGapAgent().process(state, connector)
        state = CodingAnalyticsAgent().process(state, connector)
        state = JobMatchingAgent().process(state, connector)
        state = InterviewAgent().process(state)

        agent = ValidationAgent()
        state, report = agent.validate(state)

        assert report.passed is True
        assert len(report.failures) == 0
        assert state.approval_status == "validated"

    def test_incomplete_state_fails_validation(self):
        """An incomplete state fails validation with specific failures."""
        state = _make_state()
        # No profile, no analysis, no interview

        agent = ValidationAgent()
        state, report = agent.validate(state)

        assert report.passed is False
        assert len(report.failures) > 0
        failing_checks = [f.check for f in report.failures]
        assert "consent_check" in failing_checks
        assert "profile_exists" in failing_checks


# ---------------------------------------------------------------------------
# Full Graph Pipeline Tests
# ---------------------------------------------------------------------------


class TestPlacementGraph:
    def test_full_pipeline_execution(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Complete pipeline runs from start to pending_approval."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )

        assert state.status == "pending_approval"
        assert state.approval_status == "pending_approval"
        assert state.profile is not None
        assert state.readiness_analysis is not None
        assert state.final_report is not None
        assert len(state.completed_nodes) >= 5
        assert state.placement_score > 0

    def test_pipeline_creates_audit_trail(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Pipeline execution creates a complete audit trail."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )

        events = graph.runtime.audit.get_events(state.run_id)
        assert len(events) >= 10  # At least run_created + 5 node starts + 5 completions

        nodes_audited = set(e.node for e in events)
        assert "resume_agent" in nodes_audited
        assert "skill_gap_agent" in nodes_audited
        assert "coding_analytics_agent" in nodes_audited
        assert "job_matching_agent" in nodes_audited
        assert "interview_agent" in nodes_audited

    def test_approval_then_publish(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Approval followed by publish works correctly."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        assert state.approval_status == "pending_approval"

        # Approve
        state = graph.approve(state.run_id, "officer_001", "approved", "Looks great.")
        assert state.approval_status == "approved"

        # Publish
        state = graph.publish(state.run_id)
        assert state.approval_status == "published"
        assert state.status == "published"

    def test_publish_blocked_without_approval(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Cannot publish without approval."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        with pytest.raises(ValueError, match="approval"):
            graph.publish(state.run_id)

    def test_pipeline_for_different_student_roles(self, system_ctx: AccessContext):
        """Pipeline works for multiple student/role combinations."""
        graph = PlacementGraph(budget=BudgetConfig(max_retries=2, max_agent_calls=50))

        state1 = graph.execute(
            student_id="student_002",
            target_role="Data Analyst",
            context=system_ctx,
        )
        assert state1.status == "pending_approval"
        assert state1.profile.name == "Priya Sharma"

    def test_validation_report_included(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Validation report is included in final state."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        assert state.validation_report is not None
        assert state.validation_report.passed is True

    def test_graph_state_has_evidence(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Graph state accumulates evidence from agents."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        assert len(state.evidence) >= 3  # resume, skill_gap, coding, job_matching, interview

    def test_edit_requested_flow(self, graph: PlacementGraph, system_ctx: AccessContext):
        """Edit requested changes approval_status to edit_requested."""
        state = graph.execute(
            student_id="student_001",
            target_role="Software Engineer",
            context=system_ctx,
        )
        state = graph.approve(state.run_id, "officer_001", "edit_requested", "Fix gaps.")
        assert state.approval_status == "edit_requested"
