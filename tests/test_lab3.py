"""
test_lab3.py — Tests for Lab 3: Reusable Skills.

Acceptance criteria:
    ✓ Same PlanSkill works for student_001 → Software Engineer.
    ✓ Same PlanSkill works for student_002 → Data Analyst.
    ✓ Same PlanSkill works for student_003 → ML Engineer.
    ✓ Same FormatSkill works for each combination above.
    ✓ FormatSkill output contains all required report sections.
    ✓ ReadinessReport is a typed Pydantic model.
    ✓ report.to_text() returns a non-empty string.
"""

import pytest

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import AccessContext, ReadinessReport
from app.skills.format_skill import FormatSkill
from app.skills.plan_skill import PlanSkill, PlanSkillInput
from app.tools.profile_tools import get_student_profile
from app.tools.readiness_tools import calculate_readiness, get_skill_assessment
from app.tools.role_tools import get_role_requirements


@pytest.fixture
def system_ctx() -> AccessContext:
    return AccessContext(actor_id="system", actor_role="system")


@pytest.fixture
def connector(system_ctx: AccessContext) -> PlacementConnector:
    return PlacementConnector(system_ctx)


@pytest.fixture
def plan_skill() -> PlanSkill:
    return PlanSkill()


@pytest.fixture
def format_skill() -> FormatSkill:
    return FormatSkill()


# ---------------------------------------------------------------------------
# PlanSkill reusability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "student_id,role",
    [
        ("student_001", "Software Engineer"),
        ("student_002", "Data Analyst"),
        ("student_003", "ML Engineer"),
    ],
)
class TestPlanSkillReusability:
    def test_plan_skill_works_for_any_combination(
        self, student_id: str, role: str, plan_skill: PlanSkill
    ):
        """Same PlanSkill instance creates plans for different student/role combos."""
        plan = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        assert plan.student_id == student_id
        assert plan.target_role == role
        assert plan.status == "draft"
        assert len(plan.steps) >= 5

    def test_plan_ids_are_unique_across_combinations(
        self, student_id: str, role: str, plan_skill: PlanSkill
    ):
        """Each plan gets its own unique ID."""
        plan1 = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        plan2 = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        assert plan1.plan_id != plan2.plan_id


# ---------------------------------------------------------------------------
# FormatSkill reusability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "student_id,role",
    [
        ("student_001", "Software Engineer"),
        ("student_002", "Data Analyst"),
        ("student_003", "ML Engineer"),
    ],
)
class TestFormatSkillReusability:
    def test_format_skill_produces_report(
        self,
        student_id: str,
        role: str,
        connector: PlacementConnector,
        plan_skill: PlanSkill,
        format_skill: FormatSkill,
    ):
        """FormatSkill produces a ReadinessReport for each student/role combination."""
        profile = get_student_profile(student_id, connector)
        role_req = get_role_requirements(role, connector)
        assessment = get_skill_assessment(student_id, connector)

        analysis = calculate_readiness(profile, role_req, assessment)
        plan = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )

        report = format_skill.format_readiness_report(
            analysis=analysis,
            plan=plan,
            student_name=profile.name,
        )

        assert isinstance(report, ReadinessReport)
        assert report.student_id == student_id
        assert report.target_role == role
        assert 0 <= report.overall_readiness_score <= 100

    def test_report_to_text_is_non_empty(
        self,
        student_id: str,
        role: str,
        connector: PlacementConnector,
        plan_skill: PlanSkill,
        format_skill: FormatSkill,
    ):
        """report.to_text() returns a printable non-empty string."""
        profile = get_student_profile(student_id, connector)
        role_req = get_role_requirements(role, connector)
        assessment = get_skill_assessment(student_id, connector)

        analysis = calculate_readiness(profile, role_req, assessment)
        plan = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        report = format_skill.format_readiness_report(
            analysis=analysis, plan=plan, student_name=profile.name
        )

        text = report.to_text()
        assert isinstance(text, str)
        assert len(text) > 100

    def test_report_contains_required_sections(
        self,
        student_id: str,
        role: str,
        connector: PlacementConnector,
        plan_skill: PlanSkill,
        format_skill: FormatSkill,
    ):
        """The rendered report text contains all required section headers."""
        profile = get_student_profile(student_id, connector)
        role_req = get_role_requirements(role, connector)
        assessment = get_skill_assessment(student_id, connector)

        analysis = calculate_readiness(profile, role_req, assessment)
        plan = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        report = format_skill.format_readiness_report(
            analysis=analysis, plan=plan, student_name=profile.name
        )

        text = report.to_text()
        for section in [
            "PLACEMENT READINESS REPORT",
            "Strengths",
            "Skill Gaps",
            "Coding Signals",
            "Recommended Next Steps",
            "Historical Similar Cases",
        ]:
            assert section in text, f"Section '{section}' missing from report"

    def test_report_contains_recommended_steps(
        self,
        student_id: str,
        role: str,
        connector: PlacementConnector,
        plan_skill: PlanSkill,
        format_skill: FormatSkill,
    ):
        """Report must always include at least one recommended step."""
        profile = get_student_profile(student_id, connector)
        role_req = get_role_requirements(role, connector)
        assessment = get_skill_assessment(student_id, connector)

        analysis = calculate_readiness(profile, role_req, assessment)
        plan = plan_skill.create_readiness_plan(
            PlanSkillInput(student_id=student_id, target_role=role)
        )
        report = format_skill.format_readiness_report(
            analysis=analysis, plan=plan, student_name=profile.name
        )
        assert len(report.recommended_steps) >= 1
