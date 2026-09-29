"""
coding_analytics_agent.py — Lab 7: Coding performance analysis agent.

Analyses coding platform data (problems solved, contest ratings) through
the governed connector. Keeps raw data private; exposes useful trends.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import GraphState
from app.tools.readiness_tools import _compute_coding_score, _compute_project_score


class CodingAnalyticsAgent:
    """
    Analyses coding performance and project portfolio.

    Uses the existing Lab 2 scoring formulas.
    Only uses authorized data from the connector.
    """

    def process(self, state: GraphState, connector: PlacementConnector) -> GraphState:
        """
        Run coding analytics.

        Args:
            state:     GraphState with profile populated.
            connector: Lab 5 governed connector.

        Returns:
            Updated GraphState with coding_analytics populated.
        """
        if state.profile is None:
            raise ValueError("Cannot run coding analytics: profile not loaded.")

        # Fetch skill assessment through connector
        assessment = connector.get_skill_assessment(state.student_id)

        # Use existing Lab 2 scoring
        coding_score = _compute_coding_score(state.profile)
        project_score = _compute_project_score(state.profile)

        stats = state.profile.coding_stats
        problems = int(stats.get("problems_solved", 0))
        rating = int(stats.get("contest_rating", 0))

        # Determine trends (deterministic, no AI needed)
        problem_trend = "strong" if problems >= 300 else "moderate" if problems >= 150 else "needs_improvement"
        rating_trend = "strong" if rating >= 1500 else "moderate" if rating >= 1200 else "needs_improvement"
        project_trend = "strong" if len(state.profile.projects) >= 3 else "moderate" if len(state.profile.projects) >= 2 else "needs_improvement"

        state.coding_analytics = {
            "coding_score": coding_score,
            "project_score": project_score,
            "problem_solving_trend": problem_trend,
            "contest_trend": rating_trend,
            "project_trend": project_trend,
            "dsa_score": assessment.dsa_score,
            "aptitude_score": assessment.aptitude_score,
            "communication_score": assessment.communication_score,
            "mock_interview_score": assessment.mock_interview_score,
            "summary": (
                f"Coding: {coding_score:.1f}/100 | "
                f"Projects: {project_score:.1f}/100 | "
                f"DSA Assessment: {assessment.dsa_score}/100"
            ),
        }

        state.evidence.append(
            f"Coding analytics: score={coding_score:.1f}, "
            f"projects={project_score:.1f}, problems={problems}"
        )

        return state
