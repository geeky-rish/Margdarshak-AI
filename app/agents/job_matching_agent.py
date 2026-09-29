"""
job_matching_agent.py — Lab 7: Job/company matching agent.

Combines skill gap output and coding analytics with company/role requirements
to produce placement readiness scores, company matches, and confidence.

Uses the EXISTING Lab 2 scoring formula — does NOT invent a new one.
Routes low-confidence matches for human review.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import GraphState
from app.tools.readiness_tools import calculate_readiness, validate_inputs


class JobMatchingAgent:
    """
    Matches students to roles/companies using the existing deterministic
    scoring system from Lab 2.

    Scoring logic is explicit and traceable to the Lab 2 formula.
    """

    LOW_CONFIDENCE_THRESHOLD = 0.5  # Below this, flag for human review

    def process(self, state: GraphState, connector: PlacementConnector) -> GraphState:
        """
        Run job matching.

        Args:
            state:     GraphState with profile, skill_gap, and coding_analytics.
            connector: Lab 5 governed connector.

        Returns:
            Updated GraphState with placement_score, company_matches, etc.
        """
        if state.profile is None:
            raise ValueError("Cannot run job matching: profile not loaded.")

        # Fetch role and assessment through connector
        role = connector.get_role_requirements(state.target_role)
        assessment = connector.get_skill_assessment(state.student_id)

        # Use EXISTING Lab 2 formula for the readiness score
        validate_inputs(state.profile, role)
        analysis = calculate_readiness(state.profile, role, assessment)

        state.readiness_analysis = analysis
        state.placement_score = analysis.overall_readiness_score

        # Calculate confidence based on data completeness and score margin
        score_margin = abs(analysis.overall_readiness_score - role.minimum_readiness_score)
        skill_data_completeness = (
            len([g for g in (state.skill_gap.get("current_skills", []))]) /
            max(len(role.required_skills), 1)
        )
        confidence = min(
            round((score_margin / 30.0) * 0.5 + skill_data_completeness * 0.5, 2),
            1.0
        )
        state.match_confidence = confidence

        # Build company matches from role's typical_companies
        company_matches = []
        for company in role.typical_companies:
            match = {
                "company": company,
                "role": role.role,
                "readiness_score": analysis.overall_readiness_score,
                "meets_threshold": analysis.meets_minimum_threshold,
                "gaps_to_close": analysis.skill_gaps[:3],
            }
            company_matches.append(match)

        # Filter: only include companies where threshold is met, or flag for review
        state.company_matches = company_matches

        # Build reasoning
        reasoning_parts = []
        if analysis.meets_minimum_threshold:
            reasoning_parts.append(
                f"Score {analysis.overall_readiness_score:.1f} meets "
                f"minimum threshold {role.minimum_readiness_score} for {role.role}."
            )
        else:
            reasoning_parts.append(
                f"Score {analysis.overall_readiness_score:.1f} is below "
                f"minimum threshold {role.minimum_readiness_score} for {role.role}."
            )

        if analysis.strengths:
            reasoning_parts.append(f"Strengths: {', '.join(analysis.strengths[:3])}.")
        if analysis.skill_gaps:
            reasoning_parts.append(f"Gaps: {', '.join(analysis.skill_gaps[:3])}.")
        if confidence < self.LOW_CONFIDENCE_THRESHOLD:
            reasoning_parts.append(
                "LOW CONFIDENCE — routing for human review."
            )

        state.match_reasoning = " ".join(reasoning_parts)

        state.evidence.append(
            f"Job matching: score={analysis.overall_readiness_score:.1f}, "
            f"confidence={confidence:.2f}, "
            f"threshold_met={analysis.meets_minimum_threshold}"
        )

        return state
