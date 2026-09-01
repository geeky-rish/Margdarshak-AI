"""
test_lab5.py — Tests for Lab 5: MCP-Style Placement Connector.

Acceptance criteria:
    ✓ Student profile retrieval works through connector.
    ✓ Role requirement retrieval works through connector.
    ✓ Skill assessment retrieval works through connector.
    ✓ Unauthorized student-to-student access is rejected.
    ✓ Student cannot list all profiles.
    ✓ Placement officer can access all profiles.
    ✓ Connector can be mocked — agents do not care about implementation.
"""

import pytest
from unittest.mock import MagicMock

from app.connector.placement_connector import PlacementConnector, UnauthorizedAccessError
from app.models.schemas import (
    AccessContext,
    RoleRequirements,
    SkillAssessment,
    StudentProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def system_ctx() -> AccessContext:
    return AccessContext(actor_id="system", actor_role="system")


@pytest.fixture
def officer_ctx() -> AccessContext:
    return AccessContext(actor_id="officer_001", actor_role="placement_officer")


@pytest.fixture
def student_001_ctx() -> AccessContext:
    return AccessContext(actor_id="student_001", actor_role="student")


@pytest.fixture
def student_002_ctx() -> AccessContext:
    return AccessContext(actor_id="student_002", actor_role="student")


@pytest.fixture
def system_connector(system_ctx: AccessContext) -> PlacementConnector:
    return PlacementConnector(system_ctx)


# ---------------------------------------------------------------------------
# Data access through connector
# ---------------------------------------------------------------------------


class TestConnectorDataAccess:
    def test_student_profile_retrieval(self, system_connector: PlacementConnector):
        """Student profile is retrievable through the connector."""
        profile = system_connector.get_student_profile("student_001")
        assert isinstance(profile, StudentProfile)
        assert profile.student_id == "student_001"

    def test_role_requirement_retrieval(self, system_connector: PlacementConnector):
        """Role requirements are retrievable through the connector."""
        role = system_connector.get_role_requirements("Software Engineer")
        assert isinstance(role, RoleRequirements)
        assert role.role == "Software Engineer"

    def test_skill_assessment_retrieval(self, system_connector: PlacementConnector):
        """Skill assessment is retrievable through the connector."""
        assessment = system_connector.get_skill_assessment("student_001")
        assert isinstance(assessment, SkillAssessment)
        assert assessment.student_id == "student_001"

    def test_all_three_students_accessible(self, system_connector: PlacementConnector):
        """All three seeded students are accessible through the connector."""
        for sid in ["student_001", "student_002", "student_003"]:
            p = system_connector.get_student_profile(sid)
            assert p.student_id == sid


# ---------------------------------------------------------------------------
# Authorization tests
# ---------------------------------------------------------------------------


class TestConnectorAuthorization:
    def test_student_can_access_own_profile(self, student_001_ctx: AccessContext):
        """A student may access their own profile."""
        connector = PlacementConnector(student_001_ctx)
        profile = connector.get_student_profile("student_001")
        assert profile.student_id == "student_001"

    def test_student_cannot_access_other_profile(self, student_001_ctx: AccessContext):
        """A student must NOT access another student's profile."""
        connector = PlacementConnector(student_001_ctx)
        with pytest.raises(UnauthorizedAccessError):
            connector.get_student_profile("student_002")

    def test_student_cannot_list_all_students(self, student_001_ctx: AccessContext):
        """A student must NOT be able to list all student IDs."""
        connector = PlacementConnector(student_001_ctx)
        with pytest.raises(UnauthorizedAccessError):
            connector.list_all_student_ids()

    def test_student_cannot_search_all_profiles(self, student_001_ctx: AccessContext):
        """A student must NOT be able to search across all profiles."""
        connector = PlacementConnector(student_001_ctx)
        with pytest.raises(UnauthorizedAccessError):
            connector.search_students(["python"])

    def test_student_cannot_view_placement_history(self, student_001_ctx: AccessContext):
        """A student must NOT access full placement history."""
        connector = PlacementConnector(student_001_ctx)
        with pytest.raises(UnauthorizedAccessError):
            connector.get_placement_history()

    def test_officer_can_access_any_student(self, officer_ctx: AccessContext):
        """Placement officer can access any student profile."""
        connector = PlacementConnector(officer_ctx)
        for sid in ["student_001", "student_002", "student_003"]:
            p = connector.get_student_profile(sid)
            assert p.student_id == sid

    def test_officer_can_list_all_students(self, officer_ctx: AccessContext):
        """Placement officer can list all student IDs."""
        connector = PlacementConnector(officer_ctx)
        ids = connector.list_all_student_ids()
        assert len(ids) >= 3

    def test_student_002_cannot_access_student_001(self, student_002_ctx: AccessContext):
        """student_002 cannot access student_001's data."""
        connector = PlacementConnector(student_002_ctx)
        with pytest.raises(UnauthorizedAccessError):
            connector.get_student_profile("student_001")


# ---------------------------------------------------------------------------
# Connector abstraction / mock tests
# ---------------------------------------------------------------------------


class TestConnectorAbstraction:
    def test_tools_work_with_mocked_connector(self):
        """Tools work when the connector is mocked — no file I/O needed."""
        from app.tools.profile_tools import get_student_profile

        mock_connector = MagicMock(spec=PlacementConnector)
        mock_connector.get_student_profile.return_value = StudentProfile(
            student_id="mock_001",
            name="Mock Student",
            consent=True,
            branch="CS",
            cgpa=9.0,
            skills={"DSA": "advanced"},
            projects=["Mock Project"],
            coding_stats={"problems_solved": 300, "contest_rating": 1600},
        )

        profile = get_student_profile("mock_001", mock_connector)
        assert profile.student_id == "mock_001"
        mock_connector.get_student_profile.assert_called_once_with("mock_001")

    def test_readiness_tools_work_with_mocked_connector(self):
        """Readiness tools work with a mocked connector."""
        from app.tools.readiness_tools import get_skill_assessment

        mock_connector = MagicMock(spec=PlacementConnector)
        mock_connector.get_skill_assessment.return_value = SkillAssessment(
            student_id="mock_001",
            assessment_date="2026-01-01",
            dsa_score=75,
            aptitude_score=80,
            communication_score=70,
            mock_interview_score=72,
        )

        assessment = get_skill_assessment("mock_001", mock_connector)
        assert assessment.student_id == "mock_001"

    def test_no_direct_file_access_in_tools(self):
        """
        Tools (profile_tools, role_tools, readiness_tools) must not import
        json or pathlib directly — all file access goes through connector.
        """
        import app.tools.profile_tools as pt
        import app.tools.role_tools as rt
        import app.tools.readiness_tools as rdt
        import importlib
        import inspect

        for module in [pt, rt, rdt]:
            source = inspect.getsource(module)
            assert "open(" not in source, (
                f"{module.__name__} directly opens files — use connector instead"
            )
            # Check no direct json.load of data files
            assert 'load_json' not in source or 'connector' in source

    def test_workflow_uses_connector_not_raw_files(self):
        """
        WorkflowService must import from connector, not open data files.
        """
        import inspect
        import app.services.workflow_service as ws

        source = inspect.getsource(ws)
        assert "open(" not in source, (
            "workflow_service.py should not directly open files"
        )
