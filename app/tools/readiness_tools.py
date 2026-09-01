"""
readiness_tools.py — Lab 2: Deterministic readiness calculator and validator.

Formula (transparent and easy to modify):

    skill_coverage_score (weight = 0.50)
    ─────────────────────────────────────
    For each required skill of the role:
        • advanced   → 1.0 point
        • intermediate → 0.75 point
        • beginner   → 0.40 point
        • missing    → 0.0  point
    score = (sum / max_possible) * 100

    coding_score (weight = 0.30)
    ─────────────────────────────────────
    Based on normalised mix of:
        • problems_solved / 500  (capped at 1.0)  → 60%
        • (contest_rating - 1000) / 1000 (capped at 1.0) → 40%
    score = normalised_value * 100

    project_score (weight = 0.20)
    ─────────────────────────────────────
    score = min(num_projects / 3, 1.0) * 100

    overall = skill_coverage * 0.50 + coding * 0.30 + project * 0.20
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import (
    RoleRequirements,
    SkillAssessment,
    StudentProfile,
    ReadinessAnalysis,
)

# Proficiency-level weights used in skill coverage scoring
_PROFICIENCY_WEIGHTS: dict[str, float] = {
    "advanced": 1.0,
    "intermediate": 0.75,
    "beginner": 0.40,
}


def validate_inputs(
    profile: StudentProfile,
    role: RoleRequirements,
) -> None:
    """
    Validate that a profile and role are compatible for analysis.

    Raises:
        ValueError: If the profile has no consent or the role has no required skills.
    """
    if not profile.consent:
        raise ValueError(
            f"Student '{profile.student_id}' has not given consent for analysis."
        )
    if not role.required_skills:
        raise ValueError(
            f"Role '{role.role}' has no required skills defined."
        )


def _compute_skill_coverage(
    profile: StudentProfile, role: RoleRequirements
) -> tuple[float, list[str], list[str]]:
    """
    Internal: compute skill coverage score, strengths, and gaps.

    Returns:
        (score_0_to_100, strengths, skill_gaps)
    """
    student_skills = {k.lower(): v.lower() for k, v in profile.skills.items()}
    strengths: list[str] = []
    skill_gaps: list[str] = []
    total_points = 0.0

    for required in role.required_skills:
        level = student_skills.get(required.lower(), "missing")
        weight = _PROFICIENCY_WEIGHTS.get(level, 0.0)
        total_points += weight
        if level in ("intermediate", "advanced"):
            strengths.append(f"{required} ({level})")
        else:
            skill_gaps.append(required)

    max_possible = float(len(role.required_skills))
    if max_possible == 0:
        return 0.0, strengths, skill_gaps

    score = (total_points / max_possible) * 100.0
    return round(score, 2), strengths, skill_gaps


def _compute_coding_score(profile: StudentProfile) -> float:
    """
    Internal: compute a normalised coding score from coding_stats.
    """
    stats = profile.coding_stats
    problems_solved = float(stats.get("problems_solved", 0))
    contest_rating = float(stats.get("contest_rating", 1000))

    # Normalise each component and cap at 1.0
    problems_component = min(problems_solved / 500.0, 1.0)
    rating_component = min(max(contest_rating - 1000.0, 0.0) / 1000.0, 1.0)

    normalised = problems_component * 0.60 + rating_component * 0.40
    return round(normalised * 100.0, 2)


def _compute_project_score(profile: StudentProfile) -> float:
    """
    Internal: compute a project relevance score.
    """
    count = len(profile.projects)
    return round(min(count / 3.0, 1.0) * 100.0, 2)


def calculate_readiness(
    profile: StudentProfile,
    role: RoleRequirements,
    assessment: SkillAssessment,
) -> ReadinessAnalysis:
    """
    Compute a deterministic readiness analysis for the given student and role.

    Args:
        profile:    StudentProfile from PlacementConnector.
        role:       RoleRequirements from PlacementConnector.
        assessment: SkillAssessment from PlacementConnector.

    Returns:
        A ReadinessAnalysis model with scores and qualitative signals.
    """
    validate_inputs(profile, role)

    skill_score, strengths, gaps = _compute_skill_coverage(profile, role)
    coding_score = _compute_coding_score(profile)
    project_score = _compute_project_score(profile)

    overall = round(
        skill_score * 0.50 + coding_score * 0.30 + project_score * 0.20, 2
    )

    return ReadinessAnalysis(
        student_id=profile.student_id,
        target_role=role.role,
        skill_coverage_score=skill_score,
        coding_score=coding_score,
        project_score=project_score,
        overall_readiness_score=overall,
        strengths=strengths,
        skill_gaps=gaps,
        meets_minimum_threshold=overall >= role.minimum_readiness_score,
    )


def get_skill_assessment(
    student_id: str,
    connector: PlacementConnector,
) -> SkillAssessment:
    """
    Retrieve the skill assessment for a student through the connector.

    Args:
        student_id: The unique identifier of the student.
        connector:  An initialised PlacementConnector instance.
    """
    return connector.get_skill_assessment(student_id)
