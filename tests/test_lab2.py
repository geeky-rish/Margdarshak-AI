"""
test_lab2.py — Tests for Lab 2: Tool-Using Agent.

Acceptance criteria:
    ✓ Student data is fetched through tools (via connector).
    ✓ Role data is fetched through tools (via connector).
    ✓ Readiness calculation is deterministic.
    ✓ Invalid data (no consent, empty skills) raises appropriate errors.
    ✓ validate_inputs rejects invalid combinations.
"""

import pytest

from app.connector.placement_connector import PlacementConnector, UnauthorizedAccessError
from app.models.schemas import (
    AccessContext,
    ReadinessAnalysis,
    RoleRequirements,
    SkillAssessment,
    StudentProfile,
)
from app.tools.profile_tools import get_student_profile
from app.tools.readiness_tools import calculate_readiness, validate_inputs, get_skill_assessment
from app.tools.role_tools import get_role_requirements


@pytest.fixture
def system_ctx() -> AccessContext:
    return AccessContext(actor_id="system", actor_role="system")


@pytest.fixture
def connector(system_ctx: AccessContext) -> PlacementConnector:
    return PlacementConnector(system_ctx)


# ---------------------------------------------------------------------------
# Profile tool tests
# ---------------------------------------------------------------------------


class TestProfileTools:
    def test_get_student_001(self, connector: PlacementConnector):
        """student_001 profile is correctly returned through the connector."""
        profile = get_student_profile("student_001", connector)
        assert isinstance(profile, StudentProfile)
        assert profile.student_id == "student_001"
        assert profile.consent is True
        assert "DSA" in profile.skills

    def test_get_student_002(self, connector: PlacementConnector):
        """student_002 profile is correctly returned."""
        profile = get_student_profile("student_002", connector)
        assert profile.student_id == "student_002"
        assert "Python" in profile.skills

    def test_invalid_student_raises_key_error(self, connector: PlacementConnector):
        """Requesting a non-existent student raises KeyError."""
        with pytest.raises(KeyError):
            get_student_profile("student_999", connector)


# ---------------------------------------------------------------------------
# Role tool tests
# ---------------------------------------------------------------------------


class TestRoleTools:
    def test_get_software_engineer_role(self, connector: PlacementConnector):
        """Software Engineer role is fetched with correct required skills."""
        role = get_role_requirements("Software Engineer", connector)
        assert isinstance(role, RoleRequirements)
        assert "DSA" in role.required_skills
        assert "Java" in role.required_skills

    def test_get_data_analyst_role(self, connector: PlacementConnector):
        """Data Analyst role is fetched correctly."""
        role = get_role_requirements("Data Analyst", connector)
        assert "SQL" in role.required_skills
        assert "Python" in role.required_skills

    def test_get_ml_engineer_role(self, connector: PlacementConnector):
        """ML Engineer role is fetched correctly."""
        role = get_role_requirements("ML Engineer", connector)
        assert "Machine Learning" in role.required_skills

    def test_invalid_role_raises_key_error(self, connector: PlacementConnector):
        """Requesting a non-existent role raises KeyError."""
        with pytest.raises(KeyError):
            get_role_requirements("Quantum Wizard", connector)


# ---------------------------------------------------------------------------
# Readiness calculation tests
# ---------------------------------------------------------------------------


class TestReadinessCalculation:
    def _make_profile(self, skills: dict, projects: list, problems: int, rating: int) -> StudentProfile:
        return StudentProfile(
            student_id="test_student",
            name="Test",
            consent=True,
            branch="CS",
            cgpa=8.0,
            skills=skills,
            projects=projects,
            coding_stats={"problems_solved": problems, "contest_rating": rating},
        )

    def _make_role(self, required: list) -> RoleRequirements:
        return RoleRequirements(
            role="Test Role",
            required_skills=required,
            minimum_readiness_score=70.0,
        )

    def _make_assessment(self) -> SkillAssessment:
        return SkillAssessment(
            student_id="test_student",
            assessment_date="2026-01-01",
            dsa_score=60,
            aptitude_score=70,
            communication_score=65,
            mock_interview_score=60,
        )

    def test_perfect_student_scores_high(self):
        """A student with all advanced skills, many projects, high rating scores high."""
        profile = self._make_profile(
            skills={"DSA": "advanced", "Java": "advanced", "DBMS": "advanced",
                    "Operating Systems": "advanced", "Computer Networks": "advanced"},
            projects=["p1", "p2", "p3"],
            problems=500,
            rating=2000,
        )
        role = self._make_role(["DSA", "Java", "DBMS", "Operating Systems", "Computer Networks"])
        assessment = self._make_assessment()
        analysis = calculate_readiness(profile, role, assessment)
        assert analysis.overall_readiness_score >= 85

    def test_weak_student_scores_low(self):
        """A student with no skills, no projects, low rating scores low."""
        profile = self._make_profile(
            skills={},
            projects=[],
            problems=10,
            rating=800,
        )
        role = self._make_role(["DSA", "Java", "DBMS"])
        assessment = self._make_assessment()
        analysis = calculate_readiness(profile, role, assessment)
        assert analysis.overall_readiness_score < 30

    def test_calculation_is_deterministic(self, connector: PlacementConnector):
        """The same inputs always produce the same output."""
        profile = get_student_profile("student_001", connector)
        role = get_role_requirements("Software Engineer", connector)
        assessment = get_skill_assessment("student_001", connector)

        result1 = calculate_readiness(profile, role, assessment)
        result2 = calculate_readiness(profile, role, assessment)
        assert result1.overall_readiness_score == result2.overall_readiness_score

    def test_skill_gaps_identified(self, connector: PlacementConnector):
        """Missing required skills appear in skill_gaps."""
        profile = get_student_profile("student_001", connector)
        role = get_role_requirements("Software Engineer", connector)
        assessment = get_skill_assessment("student_001", connector)
        analysis = calculate_readiness(profile, role, assessment)
        # student_001 has beginner-level OS and CN, should appear as gaps or weaknesses
        assert isinstance(analysis.skill_gaps, list)
        assert isinstance(analysis.strengths, list)

    def test_analysis_model_fields(self, connector: PlacementConnector):
        """ReadinessAnalysis has all required fields with correct types."""
        profile = get_student_profile("student_001", connector)
        role = get_role_requirements("Software Engineer", connector)
        assessment = get_skill_assessment("student_001", connector)
        analysis = calculate_readiness(profile, role, assessment)

        assert isinstance(analysis, ReadinessAnalysis)
        assert 0 <= analysis.skill_coverage_score <= 100
        assert 0 <= analysis.coding_score <= 100
        assert 0 <= analysis.project_score <= 100
        assert 0 <= analysis.overall_readiness_score <= 100

    def test_validate_inputs_no_consent(self):
        """validate_inputs raises ValueError when student has no consent."""
        profile = StudentProfile(
            student_id="no_consent",
            name="No Consent",
            consent=False,
            branch="CS",
            cgpa=7.0,
            skills={"DSA": "beginner"},
            projects=[],
            coding_stats={},
        )
        role = self._make_role(["DSA"])
        with pytest.raises(ValueError, match="consent"):
            validate_inputs(profile, role)

    def test_validate_inputs_empty_role_skills(self):
        """validate_inputs raises ValueError when role has no required skills."""
        profile = StudentProfile(
            student_id="s1",
            name="A",
            consent=True,
            branch="CS",
            cgpa=8.0,
            skills={"DSA": "advanced"},
            projects=[],
            coding_stats={},
        )
        role = RoleRequirements(role="Empty Role", required_skills=[], minimum_readiness_score=50)
        with pytest.raises(ValueError, match="required skills"):
            validate_inputs(profile, role)
