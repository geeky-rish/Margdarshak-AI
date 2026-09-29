"""
validation_agent.py — Lab 7: Hard validation gate.

Verifies that all pipeline outputs meet quality and completeness
requirements before allowing approval. Validation failure triggers
targeted regeneration (bounded by budget).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import GraphState, ValidationReport, ValidationFailure


class ValidationAgent:
    """
    Hard validation gate that checks all pipeline outputs.

    Checks include:
      - Required fields exist
      - Consent exists
      - Evidence is attached
      - Skill-gap recommendations correspond to actual gaps
      - Score is within defined bounds
      - Low-confidence results are flagged
      - No unsupported recommendations
    """

    def validate(self, state: GraphState) -> tuple[GraphState, ValidationReport]:
        """
        Run validation checks on the completed pipeline state.

        Returns:
            (updated_state, ValidationReport)
        """
        failures: list[ValidationFailure] = []
        warnings: list[ValidationFailure] = []

        # Check 1: Consent
        if not state.consent:
            failures.append(ValidationFailure(
                check="consent_check",
                severity="error",
                message="Student consent not recorded.",
                affected_node="resume_agent",
            ))

        # Check 2: Profile exists
        if state.profile is None:
            failures.append(ValidationFailure(
                check="profile_exists",
                severity="error",
                message="Student profile not loaded.",
                affected_node="resume_agent",
            ))

        # Check 3: Skill gap analysis exists
        if not state.skill_gap:
            failures.append(ValidationFailure(
                check="skill_gap_exists",
                severity="error",
                message="Skill gap analysis not completed.",
                affected_node="skill_gap_agent",
            ))

        # Check 4: Coding analytics exists
        if not state.coding_analytics:
            failures.append(ValidationFailure(
                check="coding_analytics_exists",
                severity="error",
                message="Coding analytics not completed.",
                affected_node="coding_analytics_agent",
            ))

        # Check 5: Readiness analysis exists
        if state.readiness_analysis is None:
            failures.append(ValidationFailure(
                check="readiness_analysis_exists",
                severity="error",
                message="Readiness analysis not computed.",
                affected_node="job_matching_agent",
            ))

        # Check 6: Score within bounds
        if state.readiness_analysis is not None:
            score = state.readiness_analysis.overall_readiness_score
            if score < 0 or score > 100:
                failures.append(ValidationFailure(
                    check="score_bounds",
                    severity="error",
                    message=f"Readiness score {score} is out of bounds [0, 100].",
                    affected_node="job_matching_agent",
                ))

        # Check 7: Evidence is attached
        if not state.evidence:
            warnings.append(ValidationFailure(
                check="evidence_exists",
                severity="warning",
                message="No evidence trail recorded.",
                affected_node="pipeline",
            ))

        # Check 8: Learning roadmap corresponds to actual gaps
        if state.learning_roadmap and state.skill_gap:
            gap_skills = set(
                g.get("skill", "").lower()
                for g in state.skill_gap.get("skill_gaps", [])
            )
            missing = set(
                s.lower() for s in state.skill_gap.get("missing_skills", [])
            )
            all_gap_skills = gap_skills | missing
            if all_gap_skills and not any(
                any(gs in item.lower() for gs in all_gap_skills)
                for item in state.learning_roadmap
                if "CRITICAL" in item or "IMPROVE" in item
            ):
                warnings.append(ValidationFailure(
                    check="roadmap_gap_alignment",
                    severity="warning",
                    message="Learning roadmap may not address all identified gaps.",
                    affected_node="interview_agent",
                ))

        # Check 9: Low confidence flag
        if state.match_confidence < 0.5:
            warnings.append(ValidationFailure(
                check="low_confidence",
                severity="warning",
                message=f"Match confidence {state.match_confidence:.2f} is low. "
                        f"Routing for human review.",
                affected_node="job_matching_agent",
            ))

        # Check 10: Interview results exist
        if not state.interview_results:
            failures.append(ValidationFailure(
                check="interview_results_exist",
                severity="error",
                message="Interview results/roadmap not generated.",
                affected_node="interview_agent",
            ))

        passed = len(failures) == 0

        diagnosis = ""
        if not passed:
            failing_nodes = list(set(f.affected_node for f in failures))
            diagnosis = (
                f"Validation failed: {len(failures)} error(s), "
                f"{len(warnings)} warning(s). "
                f"Affected nodes: {', '.join(failing_nodes)}. "
                f"Targeted regeneration needed for: {', '.join(failing_nodes)}."
            )

        report = ValidationReport(
            passed=passed,
            failures=failures,
            warnings=warnings,
            diagnosis=diagnosis,
            validated_at=datetime.now(timezone.utc).isoformat(),
        )

        state.validation_report = report
        if passed:
            state.approval_status = "validated"

        return state, report
