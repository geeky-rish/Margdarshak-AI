"""
placement_connector.py — Lab 5: Governed data access layer.

ALL agents and tools must go through PlacementConnector to access student,
role, and assessment data. No module outside connector/ may directly read
the JSON data files.

Design goals:
    1. Single entry point for all data (MCP-style connector pattern).
    2. Authorization via AccessContext — enforced on every call.
    3. Data-source agnostic: swap JSON → PostgreSQL → REST API without
       touching any agent or tool code.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from app.models.schemas import (
    AccessContext,
    RoleRequirements,
    SkillAssessment,
    StudentProfile,
)

# Path resolution: connector knows where data lives so nothing else needs to.
_DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"


def _load_json(filename: str) -> list[dict[str, Any]]:
    """Load a JSON data file from the data directory."""
    path = _DATA_DIR / filename
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class UnauthorizedAccessError(Exception):
    """Raised when an actor tries to access data they are not permitted to see."""


def _check_student_access(ctx: AccessContext, target_student_id: str) -> None:
    """
    Enforce authorization for student-scoped data.

    Rules:
        - 'system' and 'placement_officer' may access any student.
        - 'student' may only access their own record.
    """
    if ctx.actor_role in ("system", "placement_officer"):
        return
    if ctx.actor_role == "student" and ctx.actor_id == target_student_id:
        return
    raise UnauthorizedAccessError(
        f"Actor '{ctx.actor_id}' (role={ctx.actor_role}) is not authorised "
        f"to access data for student '{target_student_id}'."
    )


class PlacementConnector:
    """
    Governed connector for all placement data sources.

    Usage example::

        ctx = AccessContext(actor_id="system", actor_role="system")
        connector = PlacementConnector(ctx)
        profile = connector.get_student_profile("student_001")

    To swap the data source (e.g., from JSON to a REST API), sub-class this
    connector and override the relevant methods. Agent code does not change.
    """

    def __init__(self, context: AccessContext) -> None:
        self._ctx = context

    # ------------------------------------------------------------------
    # Student data
    # ------------------------------------------------------------------

    def get_student_profile(self, student_id: str) -> StudentProfile:
        """
        Retrieve a student's profile.

        Authorization: students may only access their own profile.
        """
        _check_student_access(self._ctx, student_id)
        students = _load_json("students.json")
        for raw in students:
            if raw["student_id"] == student_id:
                return StudentProfile(**raw)
        raise KeyError(f"Student '{student_id}' not found.")

    def get_resume(self, student_id: str) -> dict[str, Any]:
        """
        Return a basic resume summary derived from the student profile.

        Authorization: same as get_student_profile.
        Note: In future labs this will query a dedicated resume store.
        """
        _check_student_access(self._ctx, student_id)
        profile = self.get_student_profile(student_id)
        return {
            "student_id": profile.student_id,
            "name": profile.name,
            "branch": profile.branch,
            "cgpa": profile.cgpa,
            "top_skills": [k for k, v in profile.skills.items() if v in ("intermediate", "advanced")],
            "projects": profile.projects,
        }

    def search_students(self, tags: list[str]) -> list[StudentProfile]:
        """
        Return all students whose skill set contains at least one of the tags.

        Authorization: only 'placement_officer' and 'system' roles may call this.
        """
        if self._ctx.actor_role == "student":
            raise UnauthorizedAccessError(
                "Students are not authorised to search all profiles."
            )
        students = _load_json("students.json")
        results: list[StudentProfile] = []
        for raw in students:
            skill_keys = {k.lower() for k in raw.get("skills", {}).keys()}
            if any(t.lower() in skill_keys for t in tags):
                results.append(StudentProfile(**raw))
        return results

    def list_all_student_ids(self) -> list[str]:
        """
        Return all student IDs. Restricted to placement_officer / system.
        """
        if self._ctx.actor_role == "student":
            raise UnauthorizedAccessError(
                "Students are not authorised to list all student IDs."
            )
        students = _load_json("students.json")
        return [s["student_id"] for s in students]

    def add_student_profile(
        self,
        student_id: str,
        name: str,
        branch: str,
        cgpa: float,
        skills: dict[str, str],
        projects: list[str],
        coding_stats: dict[str, float | int],
        dsa_score: float = 75.0,
        aptitude_score: float = 80.0,
        communication_score: float = 85.0,
        mock_interview_score: float = 78.0,
    ) -> StudentProfile:
        """Register or update a student profile and skill assessment."""
        students = _load_json("students.json")
        new_profile = {
            "student_id": student_id,
            "name": name,
            "consent": True,
            "branch": branch,
            "cgpa": cgpa,
            "skills": skills,
            "projects": projects,
            "coding_stats": coding_stats,
        }
        updated = False
        for idx, s in enumerate(students):
            if s["student_id"] == student_id:
                students[idx] = new_profile
                updated = True
                break
        if not updated:
            students.append(new_profile)

        path = _DATA_DIR / "students.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(students, fh, indent=2)

        assessments = _load_json("skill_assessments.json")
        new_assessment = {
            "student_id": student_id,
            "assessment_date": "2026-09-01",
            "dsa_score": dsa_score,
            "aptitude_score": aptitude_score,
            "communication_score": communication_score,
            "mock_interview_score": mock_interview_score,
            "notes": "Self-registered profile.",
        }
        updated_ass = False
        for idx, a in enumerate(assessments):
            if a["student_id"] == student_id:
                assessments[idx] = new_assessment
                updated_ass = True
                break
        if not updated_ass:
            assessments.append(new_assessment)

        path_ass = _DATA_DIR / "skill_assessments.json"
        with path_ass.open("w", encoding="utf-8") as fh:
            json.dump(assessments, fh, indent=2)

        return StudentProfile(**new_profile)

    # ------------------------------------------------------------------
    # Role data
    # ------------------------------------------------------------------

    def get_role_requirements(self, role_name: str) -> RoleRequirements:
        """
        Retrieve requirements for a given role. No access restrictions.
        Role data is considered public information.
        """
        roles = _load_json("roles.json")
        # Case-insensitive match
        target = role_name.lower().strip()
        for raw in roles:
            if raw["role"].lower().strip() == target:
                return RoleRequirements(**raw)
        raise KeyError(f"Role '{role_name}' not found.")

    def list_all_roles(self) -> list[str]:
        """Return the names of all available roles."""
        roles = _load_json("roles.json")
        return [r["role"] for r in roles]

    # ------------------------------------------------------------------
    # Skill assessments
    # ------------------------------------------------------------------

    def get_skill_assessment(self, student_id: str) -> SkillAssessment:
        """
        Retrieve the skill assessment for a student.

        Authorization: students may only access their own assessment.
        """
        _check_student_access(self._ctx, student_id)
        assessments = _load_json("skill_assessments.json")
        for raw in assessments:
            if raw["student_id"] == student_id:
                return SkillAssessment(**raw)
        raise KeyError(f"Skill assessment for '{student_id}' not found.")

    # ------------------------------------------------------------------
    # Move to RetrievalStore (read-only; write happens via retrieval_store)
    # ------------------------------------------------------------------

    def get_placement_history(self) -> list[dict[str, Any]]:
        """
        Return all historical placement cases.

        Authorization: placement_officer and system only.
        """
        if self._ctx.actor_role == "student":
            raise UnauthorizedAccessError(
                "Students are not authorised to view full Move to RetrievalStore."
            )
        return _load_json("placement_history.json")
