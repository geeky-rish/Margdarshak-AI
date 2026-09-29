"""
graph.py — Lab 7: The complete explicit agentic node graph.

Connects all specialist agents through the Runtime and typed GraphState.

Graph topology:
    START
      ↓
    Coordinator / Create Run
      ↓
    Consent + Profile Intake (Resume Agent)
      ↓
    ┌─────────────────────────────┐
    │                             │
    Skill Gap Agent       Coding Analytics Agent
    │                             │
    └──────────────┬──────────────┘
                   ↓
          Job Matching Agent
                   ↓
           Interview Agent
                   ↓
          Assemble Readiness Plan
                   ↓
          Validation Agent
           /           \
        FAIL            PASS
         ↓                ↓
  Regenerate/Revise   Approval Gate
         ↓             /       \
       retry       EDIT      APPROVE
         ↓           ↓          ↓
     Validation   Revise    Governed Publish
                                ↓
                               END

All data access goes through the Lab 5 PlacementConnector.
All execution goes through the Lab 6 Runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.schemas import (
    AccessContext,
    BudgetConfig,
    GraphState,
)
from app.runtime.runtime import Runtime
from app.runtime.budget import BudgetExhaustedError
from app.agents.resume_agent import ResumeAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.coding_analytics_agent import CodingAnalyticsAgent
from app.agents.job_matching_agent import JobMatchingAgent
from app.agents.interview_agent import InterviewAgent
from app.agents.validation_agent import ValidationAgent
from app.skills.format_skill import FormatSkill
from app.skills.plan_skill import PlanSkill, PlanSkillInput
from app.memory.retrieval_store import RetrievalStore

logger = logging.getLogger(__name__)


class PlacementGraph:
    """
    Lab 7: Complete agentic node graph for placement readiness.

    Orchestrates all agents through the Runtime with explicit state
    transitions, audit, checkpoints, and bounded validation retries.
    """

    def __init__(
        self,
        budget: BudgetConfig | None = None,
        runtime: Runtime | None = None,
    ) -> None:
        self._runtime = runtime or Runtime(
            budget=budget,
            audit_persist=True,
        )
        self._resume_agent = ResumeAgent()
        self._skill_gap_agent = SkillGapAgent()
        self._coding_agent = CodingAnalyticsAgent()
        self._job_matching_agent = JobMatchingAgent()
        self._interview_agent = InterviewAgent()
        self._validation_agent = ValidationAgent()
        self._format_skill = FormatSkill()
        self._plan_skill = PlanSkill()

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    def execute(
        self,
        student_id: str,
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        batch_id: str | None = None,
        api_key: str | None = None,
        resume_from_run_id: str | None = None,
    ) -> GraphState:
        """
        Execute the complete placement readiness pipeline.

        Args:
            student_id:         Student to analyse.
            target_role:        Target placement role.
            context:            Access context for connector authorization.
            target_companies:   Optional company preferences.
            focus_areas:        Optional skill focus areas.
            batch_id:           Optional batch ID for Lab 8 swarm.
            api_key:            Optional LLM API key.
            resume_from_run_id: Optional run ID to resume from checkpoint.

        Returns:
            Final GraphState with all results.
        """
        rt = self._runtime
        connector = rt.get_connector(context)

        # Resume from checkpoint if requested
        if resume_from_run_id:
            state = rt.resume_run(resume_from_run_id)
            if state is None:
                raise KeyError(f"No checkpoint found for run '{resume_from_run_id}'.")
        else:
            state = rt.create_run(
                student_id=student_id,
                target_role=target_role,
                context=context,
                target_companies=target_companies,
                focus_areas=focus_areas,
                batch_id=batch_id,
            )

        try:
            # Node 1: Resume Agent (if not already completed)
            if "resume_agent" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="resume_agent",
                    agent="ResumeAgent",
                    action="profile_intake",
                    step_fn=lambda s: self._resume_agent.process(s, connector),
                    input_summary={"student_id": student_id},
                )

            # Node 2a: Skill Gap Agent (if not already completed)
            if "skill_gap_agent" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="skill_gap_agent",
                    agent="SkillGapAgent",
                    action="skill_gap_analysis",
                    step_fn=lambda s: self._skill_gap_agent.process(s, connector),
                    input_summary={"target_role": target_role},
                )

            # Node 2b: Coding Analytics Agent (if not already completed)
            if "coding_analytics_agent" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="coding_analytics_agent",
                    agent="CodingAnalyticsAgent",
                    action="coding_analytics",
                    step_fn=lambda s: self._coding_agent.process(s, connector),
                    input_summary={"student_id": student_id},
                )

            # Node 3: Job Matching Agent
            if "job_matching_agent" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="job_matching_agent",
                    agent="JobMatchingAgent",
                    action="job_matching",
                    step_fn=lambda s: self._job_matching_agent.process(s, connector),
                    input_summary={"target_role": target_role},
                )

            # Node 4: Interview Agent
            if "interview_agent" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="interview_agent",
                    agent="InterviewAgent",
                    action="interview_roadmap",
                    step_fn=lambda s: self._interview_agent.process(s),
                    input_summary={"gaps_count": len(state.skill_gap.get("skill_gaps", []))},
                )

            # Node 5: Assemble Plan + Report
            if "assemble_plan" not in state.completed_nodes:
                state = rt.execute_step(
                    state,
                    node="assemble_plan",
                    agent="PlanSkill",
                    action="assemble_readiness_plan",
                    step_fn=lambda s: self._assemble_plan(s, connector, api_key),
                    input_summary={"student_id": student_id, "target_role": target_role},
                )

            # Node 6: Validation (with bounded retry)
            state = self._run_validation_loop(state, connector, api_key)

            # Node 7: Submit for approval (graph stops here until human acts)
            if state.approval_status == "validated":
                state = rt.submit_for_approval(state)

            return state

        except BudgetExhaustedError as e:
            state.status = "failed"
            state.errors.append(str(e))
            rt.audit.log(
                run_id=state.run_id,
                node="runtime",
                action="budget_exhausted",
                agent="Runtime",
                student_id=student_id,
                status="failed",
                error=str(e),
            )
            rt._runs[state.run_id] = state
            return state

        except Exception as e:
            state.status = "failed"
            state.errors.append(f"{type(e).__name__}: {e}")
            rt.audit.log(
                run_id=state.run_id,
                node="runtime",
                action="pipeline_failed",
                agent="Runtime",
                student_id=student_id,
                status="failed",
                error=str(e),
            )
            rt._runs[state.run_id] = state
            return state

    def _assemble_plan(self, state: GraphState, connector, api_key: str | None) -> GraphState:
        """Assemble the readiness plan and report."""
        # Create plan
        plan = self._plan_skill.create_readiness_plan(
            PlanSkillInput(
                student_id=state.student_id,
                target_role=state.target_role,
                target_companies=state.target_companies,
                focus_areas=state.focus_areas,
            ),
            api_key=api_key,
        )
        plan = self._plan_skill.lock_plan(plan)
        state.locked_plan = plan

        # Retrieve similar historical cases from Lab 4 long-term memory
        retrieval = self._runtime.get_retrieval_store()
        query = self._build_retrieval_query(state)
        historical_cases = retrieval.retrieve_similar_students(query, k=3)

        # Format report
        if state.readiness_analysis is not None and state.profile is not None:
            report = self._format_skill.format_readiness_report(
                analysis=state.readiness_analysis,
                plan=plan,
                student_name=state.profile.name,
                historical_cases=historical_cases,
                api_key=api_key,
            )
            state.final_report = report

        return state

    def _build_retrieval_query(self, state: GraphState) -> str:
        """Build a retrieval query from current state for similarity search."""
        if state.profile is None:
            return f"Student targeting {state.target_role}"
        skill_text = ", ".join(
            f"{s} {l}" for s, l in list(state.profile.skills.items())[:5]
        )
        gap_text = ", ".join(
            f"missing {g}" for g in state.skill_gap.get("missing_skills", [])[:3]
        ) or "no major gaps"
        return (
            f"Student targeting {state.target_role}. "
            f"Skills: {skill_text}. "
            f"Gaps: {gap_text}. "
            f"Score: {state.placement_score:.1f}."
        )

    def _run_validation_loop(self, state: GraphState, connector, api_key) -> GraphState:
        """Run validation with bounded retry on failure."""
        rt = self._runtime

        while True:
            rt.budget.record_validation_attempt()
            rt.budget.check_limits()

            state, report = self._validation_agent.validate(state)

            rt.audit.log(
                run_id=state.run_id,
                node="validation_agent",
                action="validation_check",
                agent="ValidationAgent",
                student_id=state.student_id,
                status="completed" if report.passed else "failed",
                output_summary={
                    "passed": report.passed,
                    "failures": len(report.failures),
                    "warnings": len(report.warnings),
                },
            )

            if report.passed:
                if "validation_agent" not in state.completed_nodes:
                    state.completed_nodes.append("validation_agent")
                rt.checkpoint_mgr.create_checkpoint(state, "validation_passed")
                break

            # Validation failed — can we retry?
            if not rt.budget.can_retry():
                # Exhausted retries — escalate to human review
                state.approval_status = "draft"
                state.errors.append(
                    f"Validation failed after {rt.budget.retries} retries. "
                    f"Escalating to human reviewer. Diagnosis: {report.diagnosis}"
                )
                rt.audit.log(
                    run_id=state.run_id,
                    node="validation_agent",
                    action="retries_exhausted",
                    agent="ValidationAgent",
                    student_id=state.student_id,
                    status="failed",
                    error="Max retries exhausted, escalating to human review.",
                    retry_count=rt.budget.retries,
                )
                break

            # Targeted regeneration
            rt.budget.record_retry()
            state.retry_count += 1

            failing_nodes = set(f.affected_node for f in report.failures)

            rt.audit.log(
                run_id=state.run_id,
                node="validation_agent",
                action="regeneration_triggered",
                agent="ValidationAgent",
                student_id=state.student_id,
                status="retrying",
                retry_count=state.retry_count,
                output_summary={"regenerating_nodes": list(failing_nodes)},
            )

            # Remove failed nodes from completed so they re-run
            for node in failing_nodes:
                if node in state.completed_nodes:
                    state.completed_nodes.remove(node)

            # Re-run only the failed nodes
            if "resume_agent" in failing_nodes and state.profile is None:
                state = rt.execute_step(
                    state,
                    node="resume_agent",
                    agent="ResumeAgent",
                    action="profile_intake_retry",
                    step_fn=lambda s: self._resume_agent.process(s, connector),
                )

            if "skill_gap_agent" in failing_nodes:
                state = rt.execute_step(
                    state,
                    node="skill_gap_agent",
                    agent="SkillGapAgent",
                    action="skill_gap_analysis_retry",
                    step_fn=lambda s: self._skill_gap_agent.process(s, connector),
                )

            if "coding_analytics_agent" in failing_nodes:
                state = rt.execute_step(
                    state,
                    node="coding_analytics_agent",
                    agent="CodingAnalyticsAgent",
                    action="coding_analytics_retry",
                    step_fn=lambda s: self._coding_agent.process(s, connector),
                )

            if "job_matching_agent" in failing_nodes:
                state = rt.execute_step(
                    state,
                    node="job_matching_agent",
                    agent="JobMatchingAgent",
                    action="job_matching_retry",
                    step_fn=lambda s: self._job_matching_agent.process(s, connector),
                )

            if "interview_agent" in failing_nodes:
                state = rt.execute_step(
                    state,
                    node="interview_agent",
                    agent="InterviewAgent",
                    action="interview_roadmap_retry",
                    step_fn=lambda s: self._interview_agent.process(s),
                )

        return state

    # ------------------------------------------------------------------
    # Approval and Publish (called externally after human decision)
    # ------------------------------------------------------------------

    def approve(self, run_id: str, reviewer_id: str, decision: str, comments: str = "") -> GraphState:
        """Process approval decision on a run."""
        return self._runtime.process_approval(run_id, reviewer_id, decision, comments)

    def publish(self, run_id: str) -> GraphState:
        """Publish approved results."""
        state = self._runtime.get_run(run_id)
        if state is None:
            raise KeyError(f"Run '{run_id}' not found.")
        return self._runtime.publish(state)
