"""
skill_gap_agent.py — Lab 7: Skill gap analysis agent.

Compares student skills against approved role benchmarks from the connector.
Uses deterministic logic from Lab 2 readiness tools.
Does not make unsupported claims.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import GraphState
from app.tools.readiness_tools import _PROFICIENCY_WEIGHTS


class SkillGapAgent:
    """
    Analyses skill gaps between a student's profile and target role requirements.

    Uses the existing Lab 2 benchmark data accessed through the Lab 5 connector.
    All findings cite the benchmark source (role requirements from connector).
    """

    def process(self, state: GraphState, connector: PlacementConnector) -> GraphState:
        """
        Run skill gap analysis.

        Args:
            state:     GraphState with profile populated.
            connector: Lab 5 governed connector.

        Returns:
            Updated GraphState with skill_gap populated.
        """
        if state.profile is None:
            raise ValueError("Cannot run skill gap analysis: profile not loaded.")

        # Fetch role requirements through connector
        role = connector.get_role_requirements(state.target_role)

        student_skills = {k.lower(): v.lower() for k, v in state.profile.skills.items()}

        current_skills = []
        required_skills = list(role.required_skills)
        missing_skills = []
        skill_gaps = []
        skill_coverage_points = 0.0

        for req_skill in role.required_skills:
            level = student_skills.get(req_skill.lower(), "missing")
            weight = _PROFICIENCY_WEIGHTS.get(level, 0.0)
            skill_coverage_points += weight

            if level in ("intermediate", "advanced"):
                current_skills.append({"skill": req_skill, "level": level, "status": "met"})
            elif level == "beginner":
                skill_gaps.append({
                    "skill": req_skill,
                    "current_level": level,
                    "required_level": "intermediate+",
                    "gap_severity": "moderate",
                })
            else:
                missing_skills.append(req_skill)
                skill_gaps.append({
                    "skill": req_skill,
                    "current_level": "missing",
                    "required_level": "intermediate+",
                    "gap_severity": "critical",
                })

        max_possible = float(len(role.required_skills)) if role.required_skills else 1.0
        coverage_score = round((skill_coverage_points / max_possible) * 100, 2)

        state.skill_gap = {
            "current_skills": current_skills,
            "required_skills": required_skills,
            "missing_skills": missing_skills,
            "skill_gaps": skill_gaps,
            "coverage_score": coverage_score,
            "benchmark_source": f"Role requirements: {role.role}",
            "preferred_skills": role.preferred_skills,
        }

        state.evidence.append(
            f"Skill gap analysis: {len(current_skills)} met, "
            f"{len(skill_gaps)} gaps, coverage={coverage_score}%"
        )

        return state
