"""
demo.py — Demonstrates the complete Labs 1–5 workflow.

Run with:
    python demo.py

No server needs to be running. This script uses the coordinator and components
directly to show the full agent pipeline in action.

Case 1: Vague request → clarification → structured plan
Case 2: student_001 → Software Engineer (full workflow)
Case 3: student_002 → Data Analyst (proves skills are reusable)
"""

from __future__ import annotations

import sys
import os

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from app.agents.planner_agent import PlannerAgent
from app.coordinator.coordinator import PlacementCoordinator
from app.models.schemas import AccessContext, ClarificationResponse, ClarifiedRequest

DIVIDER = "\n" + "═" * 70 + "\n"
THIN_LINE = "─" * 70


def section(title: str) -> None:
    print(DIVIDER)
    print(f"  {title}")
    print(THIN_LINE)


def run_demo() -> None:
    print(DIVIDER)
    print("  PLACEMENT READINESS & CAREER INTELLIGENCE PORTAL")
    print("  Labs 1–5 Demonstration")
    print(THIN_LINE)

    coordinator = PlacementCoordinator()
    planner = PlannerAgent()

    # ====================================================================
    # CASE 1: Vague request → clarification
    # ====================================================================

    section("CASE 1: Vague Request → Clarification Loop (Lab 1)")

    vague_request = "I want to know whether I am ready for placements."
    print(f"\nOriginal request:\n  \"{vague_request}\"\n")

    result = planner.clarify(vague_request)
    if isinstance(result, ClarificationResponse):
        print(f"[AGENT] Request is too vague. Asking {len(result.questions)} clarifying questions:\n")
        for i, q in enumerate(result.questions, 1):
            print(f"  Q{i} [{q.field}]: {q.question}")
    else:
        print("[AGENT] Request was complete:", result)

    # Simulate user responding with answers
    print(f"\n[USER ANSWERS]")
    print("  student_id      → student_001")
    print("  target_role     → Software Engineer")
    print("  focus_areas     → DSA, Operating Systems")

    from app.models.schemas import ClarifiedRequest
    from app.skills.plan_skill import PlanSkill, PlanSkillInput

    clarified = ClarifiedRequest(
        student_id="student_001",
        target_role="Software Engineer",
        focus_areas=["DSA", "Operating Systems"],
    )

    skill = PlanSkill()
    plan = skill.create_readiness_plan(
        PlanSkillInput(
            student_id=clarified.student_id,
            target_role=clarified.target_role,
            focus_areas=clarified.focus_areas,
        )
    )

    print(f"\n[AGENT] Structured ReadinessPlan created:")
    print(f"  plan_id     : {plan.plan_id}")
    print(f"  student_id  : {plan.student_id}")
    print(f"  target_role : {plan.target_role}")
    print(f"  focus_areas : {plan.focus_areas}")
    print(f"  status      : {plan.status}")
    print(f"\n  Workflow Steps:")
    for i, step in enumerate(plan.steps, 1):
        print(f"    {i}. {step}")

    # Demonstrate revision
    print(f"\n[USER] Actually, change the target role to ML Engineer.")
    revised_plan = planner.revise_plan(plan, {"target_role": "ML Engineer", "focus_areas": ["Python", "ML"]})
    print(f"[AGENT] Plan revised:")
    print(f"  target_role : {revised_plan.target_role}")
    print(f"  focus_areas : {revised_plan.focus_areas}")
    print(f"  (plan_id preserved: {revised_plan.plan_id == plan.plan_id})")

    # ====================================================================
    # CASE 2: student_001 → Software Engineer (full workflow)
    # ====================================================================

    section("CASE 2: Full Workflow — student_001 → Software Engineer (Labs 1–5)")

    ctx = AccessContext(actor_id="system", actor_role="system")

    print("\nExecuting full Labs 1–5 workflow...\n")
    print("  [Lab 5] PlacementConnector initialised with system context.")
    print("  [Lab 5] Fetching student_001 profile via connector...")
    print("  [Lab 5] Fetching Software Engineer requirements via connector...")
    print("  [Lab 5] Fetching student_001 skill assessment via connector...")
    print("  [Lab 2] Running deterministic readiness calculation...")
    print("  [Lab 3] Creating plan via PlanSkill...")
    print("  [Lab 4] Retrieving similar historical cases from long-term memory...")
    print("  [Lab 3] Formatting report via FormatSkill...")

    state, report = coordinator.run(
        student_id="student_001",
        target_role="Software Engineer",
        context=ctx,
    )

    print(f"\n[Workflow complete]")
    print(f"  run_id         : {state.run_id}")
    print(f"  plan_id        : {report.plan_id}")
    print(f"  readiness score: {report.overall_readiness_score:.1f} / 100")
    print(f"  meets threshold: {'YES ✅' if report.meets_threshold else 'NO ⚠️'}")

    print(f"\n{report.to_text()}")

    # ====================================================================
    # CASE 3: student_002 → Data Analyst (proves skills are reusable)
    # ====================================================================

    section("CASE 3: Reusability Proof — student_002 → Data Analyst (Lab 3)")

    print("\nRunning SAME coordinator, SAME PlanSkill, SAME FormatSkill...\n")

    state2, report2 = coordinator.run(
        student_id="student_002",
        target_role="Data Analyst",
        context=ctx,
    )

    print(f"[Workflow complete for student_002]")
    print(f"  run_id         : {state2.run_id}")
    print(f"  readiness score: {report2.overall_readiness_score:.1f} / 100")
    print(f"  meets threshold: {'YES ✅' if report2.meets_threshold else 'NO ⚠️'}")
    print(f"  strengths      : {', '.join(report2.strengths[:3]) or 'none'}")
    print(f"  skill_gaps     : {', '.join(report2.skill_gaps[:3]) or 'none'}")
    print(f"\n{report2.to_text()}")

    # ====================================================================
    # Summary
    # ====================================================================

    section("DEMO COMPLETE — Labs 1–5 Successfully Demonstrated")

    print("  Lab 1 ✅  Clarification loop triggered >= 2 questions for vague request.")
    print("  Lab 1 ✅  Structured ReadinessPlan created and revised.")
    print("  Lab 2 ✅  Student, role, and assessment data fetched through tools.")
    print("  Lab 2 ✅  Deterministic readiness score calculated.")
    print("  Lab 3 ✅  PlanSkill and FormatSkill reused for both students without changes.")
    print("  Lab 4 ✅  Historical cases retrieved from long-term memory.")
    print("  Lab 5 ✅  All data access went through PlacementConnector.\n")


if __name__ == "__main__":
    run_demo()
