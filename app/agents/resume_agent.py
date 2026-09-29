"""
resume_agent.py — Lab 7: Resume/Profile intake and structuring agent.

Extracts and validates student profile data through the Lab 5 connector.
Never invents resume information — only structures what exists.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import AccessContext, GraphState


class ResumeAgent:
    """
    Processes student resume/profile through the governed connector.

    Responsibilities:
      - Validate consent
      - Fetch structured profile via connector
      - Build resume summary
      - Flag incomplete information
      - Never invent data
    """

    def process(self, state: GraphState, connector: PlacementConnector) -> GraphState:
        """
        Process student profile intake.

        Args:
            state:     Current graph state with student_id set.
            connector: Lab 5 governed connector for data access.

        Returns:
            Updated GraphState with profile and resume_summary populated.

        Raises:
            ValueError: If consent is missing.
            KeyError:   If student not found.
        """
        # Fetch profile through connector (Lab 5 governs access)
        profile = connector.get_student_profile(state.student_id)

        # Validate consent
        if not profile.consent:
            raise ValueError(
                f"Student '{state.student_id}' has not given consent for analysis. "
                "Cannot proceed without explicit consent."
            )

        state.consent = True
        state.profile = profile

        # Build resume summary (no sensitive data exposed)
        top_skills = [
            f"{k} ({v})" for k, v in profile.skills.items()
            if v in ("intermediate", "advanced")
        ]
        weak_skills = [
            k for k, v in profile.skills.items()
            if v == "beginner"
        ]

        state.resume_summary = {
            "name": profile.name,
            "branch": profile.branch,
            "cgpa": profile.cgpa,
            "top_skills": top_skills,
            "weak_skills": weak_skills,
            "projects_count": len(profile.projects),
            "projects": profile.projects,
            "problems_solved": profile.coding_stats.get("problems_solved", 0),
            "contest_rating": profile.coding_stats.get("contest_rating", 0),
            "completeness": "complete" if profile.skills and profile.projects else "incomplete",
        }

        # Add evidence
        state.evidence.append(f"Profile loaded for {profile.name} ({state.student_id})")

        return state
