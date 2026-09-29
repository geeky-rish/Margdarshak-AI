"""
interview_agent.py — Lab 7: Interview preparation and roadmap agent.

Generates mock interview plans and learning roadmaps based on
identified skill gaps. All feedback is clearly marked as AI-generated.
"""

from __future__ import annotations

from app.models.schemas import GraphState


class InterviewAgent:
    """
    Generates interview preparation plans and learning roadmaps
    based on actual identified gaps from previous agents.

    Keeps interview data private and clearly distinguishes
    AI-generated feedback from factual data.
    """

    def process(self, state: GraphState) -> GraphState:
        """
        Generate interview plan and learning roadmap.

        Args:
            state: GraphState with skill_gap and coding_analytics populated.

        Returns:
            Updated GraphState with interview_results and learning_roadmap.
        """
        if not state.skill_gap:
            raise ValueError("Cannot generate interview plan: skill gap analysis not available.")

        gaps = state.skill_gap.get("skill_gaps", [])
        missing = state.skill_gap.get("missing_skills", [])
        coding = state.coding_analytics or {}

        # Build learning roadmap from actual identified gaps
        roadmap = []

        # Priority 1: Missing skills
        for skill in missing[:3]:
            roadmap.append(
                f"[CRITICAL] Learn {skill} — required for {state.target_role}. "
                f"Recommended: structured course + hands-on projects."
            )

        # Priority 2: Weak skills (beginner level)
        weak_gaps = [g for g in gaps if g.get("gap_severity") == "moderate"]
        for gap in weak_gaps[:3]:
            roadmap.append(
                f"[IMPROVE] Strengthen {gap['skill']} from {gap['current_level']} "
                f"to intermediate+. Practice through targeted exercises."
            )

        # Priority 3: Coding improvement
        if coding.get("problem_solving_trend") == "needs_improvement":
            roadmap.append(
                "[CODING] Increase DSA practice: target 300+ problems solved "
                "and regular contest participation."
            )
        elif coding.get("problem_solving_trend") == "moderate":
            roadmap.append(
                "[CODING] Maintain coding practice; participate in weekly "
                "contests to improve rating above 1500."
            )

        # Priority 4: Projects
        if coding.get("project_trend") == "needs_improvement":
            roadmap.append(
                f"[PROJECT] Build at least one end-to-end project relevant to "
                f"'{state.target_role}' and publish on GitHub."
            )

        if not roadmap:
            roadmap.append(
                "[STRONG] Profile is well-prepared. Focus on mock interviews "
                "and resume polish before applying."
            )

        roadmap.append(
            "[INTERVIEW] Schedule mock interview with Placement Cell for personalised feedback."
        )

        # Interview results
        state.interview_results = {
            "focus_areas": [g.get("skill", "") for g in gaps[:5]],
            "recommended_practice": [
                f"Practice {g.get('skill', '')} problems" for g in gaps[:3]
            ],
            "communication_note": (
                "Strong" if (coding.get("communication_score", 0) or 0) >= 70
                else "Needs improvement — practice structured responses"
            ),
            "ai_generated": True,
            "disclaimer": "This roadmap is AI-generated based on identified gaps. "
                          "Consult with your mentor for personalised guidance.",
        }

        state.learning_roadmap = roadmap

        state.evidence.append(
            f"Interview prep: {len(roadmap)} roadmap items generated from "
            f"{len(gaps)} skill gaps"
        )

        return state
