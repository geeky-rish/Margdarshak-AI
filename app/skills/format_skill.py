"""
format_skill.py — Lab 3: Reusable FormatSkill.

FormatSkill converts a ReadinessAnalysis + ReadinessPlan + optional historical
cases into a structured ReadinessReport with a human-readable text rendering.

The same skill works for every student/role combination without modification.
When Gemini is available, an AI-generated executive summary is appended.

Usage::

    skill = FormatSkill()
    report = skill.format_readiness_report(
        analysis=analysis,
        plan=plan,
        historical_cases=cases,
        student_name="Arjun Mehta",
    )
    print(report.to_text())
"""

from __future__ import annotations

from app.models.schemas import (
    HistoricalCase,
    ReadinessAnalysis,
    ReadinessPlan,
    ReadinessReport,
)

# LLM service — optional, safe to fail
try:
    from app.services.llm_service import get_llm_service
    _LLM_IMPORT_OK = True
except Exception:
    _LLM_IMPORT_OK = False

_SEPARATOR = "=" * 60


def _build_report_text(
    report: ReadinessReport,
) -> str:
    """
    Render the structured report fields as a human-readable text block.
    """
    threshold_label = (
        "✅ MEETS minimum readiness threshold"
        if report.meets_threshold
        else "⚠️  BELOW minimum readiness threshold — additional preparation recommended"
    )

    strengths_text = (
        "\n".join(f"  • {s}" for s in report.strengths)
        if report.strengths
        else "  (none identified)"
    )

    gaps_text = (
        "\n".join(f"  • {g}" for g in report.skill_gaps)
        if report.skill_gaps
        else "  (none — all required skills present)"
    )

    steps_text = "\n".join(
        f"  {i + 1}. {step}" for i, step in enumerate(report.recommended_steps)
    )

    coding_text = "\n".join(
        f"  {k}: {v}" for k, v in report.coding_signals.items()
    )

    # Historical cases section
    if report.historical_similar_cases:
        cases_lines = []
        for c in report.historical_similar_cases:
            outcome_icon = "✅" if c.outcome == "placed" else "❌"
            cases_lines.append(
                f"  {outcome_icon} [{c.case_id}] {c.target_role} | "
                f"Score: {c.readiness_score:.1f} | {c.outcome.upper()}\n"
                f"     → {c.summary}"
            )
        cases_text = "\n".join(cases_lines)
    else:
        cases_text = "  No similar historical cases found."

    # AI summary section (only when LLM generates one)
    ai_summary_section = ""
    if hasattr(report, 'ai_summary') and report.ai_summary:
        ai_summary_section = (
            "\n── AI Executive Summary (Gemini) ─────────────────────────────────\n"
            f"  {report.ai_summary}\n"
        )

    return f"""
{_SEPARATOR}
        PLACEMENT READINESS REPORT
{_SEPARATOR}

Student : {report.student_name} ({report.student_id})
Target Role : {report.target_role}

Overall Readiness Score : {report.overall_readiness_score:.1f} / 100
{threshold_label}
{ai_summary_section}
── Strengths ──────────────────────────────────────────
{strengths_text}

── Skill Gaps ─────────────────────────────────────────
{gaps_text}

── Coding Signals ─────────────────────────────────────
{coding_text}

── Recommended Next Steps ─────────────────────────────
{steps_text}

── Historical Similar Cases ───────────────────────────
{cases_text}

── Plan Reference ─────────────────────────────────────
  Plan ID : {report.plan_id}

{_SEPARATOR}
""".strip()


class FormatSkill:
    """
    Lab 3 reusable skill: formats a ReadinessReport from analysis data.

    The skill is stateless and works for any student/role combination.
    """

    def format_readiness_report(
        self,
        analysis: ReadinessAnalysis,
        plan: ReadinessPlan,
        student_name: str = "Unknown",
        historical_cases: list[HistoricalCase] | None = None,
        api_key: str | None = None,
    ) -> ReadinessReport:
        """
        Produce a structured ReadinessReport.

        Args:
            analysis:         ReadinessAnalysis from readiness_tools.
            plan:             ReadinessPlan from PlanSkill or planner_agent.
            student_name:     Human-readable name for the report header.
            historical_cases: Optional list of similar historical cases from
                              long-term memory retrieval.
            api_key:          Optional custom user API key.

        Returns:
            A ReadinessReport Pydantic model. Call .to_text() for a printable
            string or serialise to JSON for API responses.
        """
        cases = historical_cases or []

        # Build recommended steps: gaps → specific advice, then general steps
        recommended_steps = self._build_recommended_steps(analysis)

        coding_signals: dict[str, float | int | str] = {
            "coding_score": round(analysis.coding_score, 2),
            "skill_coverage_score": round(analysis.skill_coverage_score, 2),
            "project_score": round(analysis.project_score, 2),
            "overall_readiness_score": round(analysis.overall_readiness_score, 2),
        }

        # Build partial report (without report_text yet)
        report = ReadinessReport(
            student_name=student_name,
            student_id=analysis.student_id,
            target_role=analysis.target_role,
            overall_readiness_score=analysis.overall_readiness_score,
            meets_threshold=analysis.meets_minimum_threshold,
            strengths=analysis.strengths,
            skill_gaps=analysis.skill_gaps,
            coding_signals=coding_signals,
            recommended_steps=recommended_steps,
            historical_similar_cases=cases,
            plan_id=plan.plan_id,
        )

        # Optional: AI executive summary from Gemini
        if _LLM_IMPORT_OK:
            try:
                llm = get_llm_service(api_key=api_key)
                ai_text = llm.summarise_readiness(
                    student_name=student_name,
                    target_role=analysis.target_role,
                    score=analysis.overall_readiness_score,
                    strengths=analysis.strengths,
                    gaps=analysis.skill_gaps,
                )
                report.ai_summary = ai_text  # None if LLM unavailable
            except Exception:
                pass  # Never let LLM failure break the report

        # Now attach the rendered text
        report.report_text = _build_report_text(report)
        return report

    def _build_recommended_steps(self, analysis: ReadinessAnalysis) -> list[str]:
        """
        Derive targeted recommended steps from the analysis.

        Priority: fill skill gaps first, then improve coding, then projects.
        """
        steps: list[str] = []

        if analysis.skill_gaps:
            gap_list = ", ".join(analysis.skill_gaps[:3])
            steps.append(
                f"Focus on improving missing/weak skills: {gap_list}."
            )
            if len(analysis.skill_gaps) > 3:
                remaining = ", ".join(analysis.skill_gaps[3:])
                steps.append(f"Also address: {remaining}.")

        if analysis.coding_score < 60:
            steps.append(
                "Increase DSA practice — target 300+ problems solved and "
                "a contest rating above 1500."
            )
        elif analysis.coding_score < 80:
            steps.append(
                "Maintain coding practice cadence — participate in weekly "
                "contests to improve rating."
            )

        if analysis.project_score < 67:
            steps.append(
                "Build at least one more end-to-end project relevant to "
                f"the '{analysis.target_role}' role and publish it on GitHub."
            )

        if not steps:
            steps.append(
                "Strong profile! Focus on mock interviews and resume polish "
                "before applying."
            )

        steps.append(
            "Schedule a mock interview with the Placement Cell for personalised feedback."
        )
        return steps
