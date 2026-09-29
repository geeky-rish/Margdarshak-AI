"""
schemas.py — Domain models for the Placement Readiness & Career Intelligence Portal.

All Pydantic v2 models that represent the core domain contracts shared across
Labs 1–8. No business logic lives here; only data shapes.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Lab 1 — Agent Loop Models
# ---------------------------------------------------------------------------

class ClarifiedRequest(BaseModel):
    """A fully clarified placement readiness request after the agent loop."""

    student_id: str = Field(..., description="Unique student identifier, e.g. 'student_001'")
    target_role: str = Field(..., description="The role the student is targeting, e.g. 'Software Engineer'")
    target_companies: list[str] = Field(
        default_factory=list,
        description="Optional list of specific companies the student wants to target",
    )
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Specific skill areas or topics to prioritise during analysis",
    )


class ReadinessPlan(BaseModel):
    """
    A structured, editable plan that the agent creates after clarification.

    Status can be 'draft' (editable) or 'locked' (committed for execution).
    """

    plan_id: str = Field(..., description="Unique plan identifier, e.g. 'plan_<uuid4>'")
    student_id: str
    target_role: str
    target_companies: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    steps: list[str] = Field(..., description="Ordered list of workflow steps")
    status: Literal["draft", "locked"] = "draft"


class ClarificationQuestion(BaseModel):
    """A single clarifying question the agent asks the user."""

    field: str = Field(..., description="Which field this question clarifies, e.g. 'student_id'")
    question: str = Field(..., description="Human-readable question text")


class ClarificationResponse(BaseModel):
    """Agent response when the request is still vague — returns questions."""

    questions: list[ClarificationQuestion]
    message: str = "Please answer the following questions to proceed."


# ---------------------------------------------------------------------------
# Lab 2 — Tool Data Models
# ---------------------------------------------------------------------------

class StudentProfile(BaseModel):
    """Student profile as returned by the PlacementConnector / profile tools."""

    student_id: str
    name: str
    consent: bool
    branch: str
    cgpa: float
    skills: dict[str, str] = Field(
        ..., description="Skill name → proficiency level (beginner/intermediate/advanced)"
    )
    projects: list[str] = Field(default_factory=list)
    coding_stats: dict[str, float | int] = Field(default_factory=dict)


class RoleRequirements(BaseModel):
    """Role requirements as returned by the PlacementConnector / role tools."""

    role: str
    required_skills: list[str]
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_readiness_score: float
    description: str = ""
    typical_companies: list[str] = Field(default_factory=list)


class SkillAssessment(BaseModel):
    """Formal skill assessment record for a student."""

    student_id: str
    assessment_date: str
    dsa_score: float = Field(..., ge=0, le=100)
    aptitude_score: float = Field(..., ge=0, le=100)
    communication_score: float = Field(..., ge=0, le=100)
    mock_interview_score: float = Field(..., ge=0, le=100)
    notes: str = ""


class ReadinessAnalysis(BaseModel):
    """
    Deterministic readiness analysis output.

    Formula (documented):
        skill_coverage_score  — 50% weight
            = (skills_met / required_skills_count) * 100
        coding_score          — 30% weight
            = normalised from (problems_solved + contest_rating) range
        project_score         — 20% weight
            = min(projects_count / 3, 1.0) * 100

        overall_readiness_score = (
            skill_coverage_score * 0.50
            + coding_score       * 0.30
            + project_score      * 0.20
        )
    """

    student_id: str
    target_role: str
    skill_coverage_score: float = Field(..., ge=0, le=100)
    coding_score: float = Field(..., ge=0, le=100)
    project_score: float = Field(..., ge=0, le=100)
    overall_readiness_score: float = Field(..., ge=0, le=100)
    strengths: list[str]
    skill_gaps: list[str]
    meets_minimum_threshold: bool


# ---------------------------------------------------------------------------
# Lab 3 — Skill Output Models
# ---------------------------------------------------------------------------

class HistoricalCase(BaseModel):
    """A summary of one historical placement case retrieved from long-term memory."""

    case_id: str
    student_id: str
    target_role: str
    readiness_score: float
    outcome: Literal["placed", "not_placed"]
    summary: str
    tags: list[str] = Field(default_factory=list)


class ReadinessReport(BaseModel):
    """
    The final structured placement readiness report produced by FormatSkill.

    This is a typed Pydantic object that callers can serialise to JSON or render
    as a human-readable string via `to_text()`.
    """

    student_name: str
    student_id: str
    target_role: str
    overall_readiness_score: float
    meets_threshold: bool
    strengths: list[str]
    skill_gaps: list[str]
    coding_signals: dict[str, float | int | str]
    recommended_steps: list[str]
    historical_similar_cases: list[HistoricalCase] = Field(default_factory=list)
    plan_id: str
    ai_summary: str | None = Field(
        default=None,
        description="Optional AI-generated executive summary from Gemini. "
                    "None when LLM is not configured.",
    )
    report_text: str = ""

    def to_text(self) -> str:
        """Render the report as a human-readable string."""
        return self.report_text


# ---------------------------------------------------------------------------
# Lab 4 — Run State
# ---------------------------------------------------------------------------

class RunState(BaseModel):
    """
    Short-term, per-execution run state.

    Lives only for the duration of one workflow execution. Must NEVER be
    persisted to the long-term memory store.
    """

    run_id: str
    original_request: str
    clarified_request: ClarifiedRequest | None = None
    current_plan: ReadinessPlan | None = None
    tool_results: dict = Field(default_factory=dict)
    current_analysis: ReadinessAnalysis | None = None


# ---------------------------------------------------------------------------
# Lab 5 — Access Control
# ---------------------------------------------------------------------------

class AccessContext(BaseModel):
    """
    Authorization context that must accompany every connector call.

    Roles:
        student          — may access only their own profile/assessment.
        placement_officer — may access all profiles and assessments.
        system           — internal service-to-service calls (full access).
    """

    actor_id: str = Field(..., description="ID of the acting entity (student_id or officer_id)")
    actor_role: Literal["student", "placement_officer", "system"]


# ---------------------------------------------------------------------------
# API Request/Response Wrappers
# ---------------------------------------------------------------------------

class ClarifyRequest(BaseModel):
    """Body for POST /clarify."""

    raw_request: str


class PlanRequest(BaseModel):
    """Body for POST /plan."""

    clarified_request: ClarifiedRequest


class AnalyzeRequest(BaseModel):
    """Body for POST /analyze."""

    student_id: str
    role_name: str


class SimilarStudentsRequest(BaseModel):
    """Body for GET /memory/similar."""

    query: str
    k: int = 5


class RunRequest(BaseModel):
    """Body for POST /run — triggers the full Labs 1–5 workflow."""

    student_id: str
    target_role: str
    target_companies: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    actor_id: str = "system"
    actor_role: Literal["student", "placement_officer", "system"] = "system"


class CreateStudentRequest(BaseModel):
    """Body for POST /students to dynamically register a student."""
    student_id: str
    name: str
    branch: str = "CSE"
    cgpa: float = Field(default=8.0, ge=0, le=10)
    skills: dict[str, str] = Field(
        default_factory=dict,
        description="Dict of skill -> proficiency level, e.g. {'Python': 'advanced', 'Docker': 'intermediate'}"
    )
    projects: list[str] = Field(default_factory=list)
    coding_stats: dict[str, float | int] = Field(default_factory=dict)
    dsa_score: float = Field(default=75.0, ge=0, le=100)
    aptitude_score: float = Field(default=80.0, ge=0, le=100)
    communication_score: float = Field(default=85.0, ge=0, le=100)
    mock_interview_score: float = Field(default=78.0, ge=0, le=100)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    labs_active: list[str] = Field(
        default_factory=lambda: ["lab1", "lab2", "lab3", "lab4", "lab5", "lab6", "lab7", "lab8"]
    )


# ---------------------------------------------------------------------------
# Lab 6 — Runtime / Audit / Checkpoint / Approval
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """A single auditable event in the runtime execution log."""

    event_id: str
    run_id: str
    batch_id: str | None = None
    student_id: str | None = None
    timestamp: str
    node: str = Field(..., description="Graph node or step name")
    agent: str = Field(default="", description="Agent that performed the action")
    action: str = Field(..., description="What was done")
    input_summary: dict = Field(default_factory=dict)
    output_summary: dict = Field(default_factory=dict)
    status: Literal["started", "completed", "failed", "skipped", "retrying"] = "started"
    error: str | None = None
    retry_count: int = 0
    checkpoint_id: str | None = None
    approval_state: str | None = None
    duration_ms: float | None = None


class CheckpointData(BaseModel):
    """Serialisable snapshot of a run's state at a meaningful transition."""

    checkpoint_id: str
    run_id: str
    batch_id: str | None = None
    student_id: str | None = None
    timestamp: str
    node: str = Field(..., description="Node at which checkpoint was taken")
    state_snapshot: dict = Field(
        default_factory=dict,
        description="Serialised graph state at this point",
    )
    completed_nodes: list[str] = Field(default_factory=list)
    status: Literal["valid", "invalidated"] = "valid"


class ApprovalRecord(BaseModel):
    """Records a human approval decision on a run's output."""

    approval_id: str
    run_id: str
    student_id: str
    reviewer_id: str
    decision: Literal["approved", "rejected", "edit_requested", "override"]
    timestamp: str
    comments: str = ""
    previous_status: str = ""
    resulting_status: str = ""


class BudgetConfig(BaseModel):
    """Configurable budget limits for a runtime execution."""

    max_retries: int = Field(default=3, ge=0, description="Max validation retries per run")
    max_agent_calls: int = Field(default=50, ge=1, description="Max total agent/tool invocations")
    max_execution_seconds: float = Field(default=300.0, gt=0, description="Max wall-clock time")
    max_validation_attempts: int = Field(default=3, ge=1)


class ValidationFailure(BaseModel):
    """One specific validation check that failed."""

    check: str
    severity: Literal["error", "warning"]
    message: str
    affected_node: str = ""


class ValidationReport(BaseModel):
    """Structured output from the Validation Agent."""

    passed: bool
    failures: list[ValidationFailure] = Field(default_factory=list)
    warnings: list[ValidationFailure] = Field(default_factory=list)
    diagnosis: str = ""
    validated_at: str = ""


# ---------------------------------------------------------------------------
# Lab 7 — Graph State
# ---------------------------------------------------------------------------


class GraphState(BaseModel):
    """
    Strongly typed shared state for the Lab 7 agentic node graph.

    Carries all data through the pipeline from intake to publish.
    """

    # Identity
    run_id: str
    batch_id: str | None = None
    student_id: str
    consent: bool = False

    # Request
    target_role: str = ""
    target_companies: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)

    # Plan
    locked_plan: ReadinessPlan | None = None

    # Resume / Profile
    profile: StudentProfile | None = None
    resume_summary: dict = Field(default_factory=dict)

    # Analysis
    skill_gap: dict = Field(default_factory=dict)
    coding_analytics: dict = Field(default_factory=dict)

    # Job matching
    company_matches: list[dict] = Field(default_factory=list)
    placement_score: float = 0.0
    match_confidence: float = 0.0
    match_reasoning: str = ""

    # Interview / Roadmap
    interview_results: dict = Field(default_factory=dict)
    learning_roadmap: list[str] = Field(default_factory=list)

    # Validation
    validation_report: ValidationReport | None = None
    retry_count: int = 0

    # Approval
    approval_status: Literal[
        "draft", "validated", "pending_approval", "approved",
        "edit_requested", "rejected", "published",
    ] = "draft"
    reviewer_feedback: str = ""
    approval_record: ApprovalRecord | None = None

    # Audit / Checkpoint
    completed_nodes: list[str] = Field(default_factory=list)
    checkpoint_id: str | None = None
    current_node: str = ""

    # Output
    readiness_analysis: ReadinessAnalysis | None = None
    final_report: ReadinessReport | None = None
    evidence: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Status
    status: Literal[
        "running", "completed", "failed", "pending_approval",
        "approved", "published", "cancelled",
    ] = "running"


# ---------------------------------------------------------------------------
# Lab 8 — Batch / Swarm
# ---------------------------------------------------------------------------


class StudentRunResult(BaseModel):
    """Per-student result within a batch execution."""

    student_id: str
    run_id: str
    status: Literal["success", "failed", "pending_approval", "requires_review"]
    readiness_score: float | None = None
    approval_status: str = "draft"
    error: str | None = None
    report: ReadinessReport | None = None
    duration_ms: float = 0.0


class BatchResult(BaseModel):
    """Aggregated result from a parallel batch execution (Lab 8)."""

    batch_id: str
    total_students: int
    successful: list[StudentRunResult] = Field(default_factory=list)
    failed: list[StudentRunResult] = Field(default_factory=list)
    pending_approval: list[StudentRunResult] = Field(default_factory=list)
    requires_review: list[StudentRunResult] = Field(default_factory=list)
    aggregate_metrics: dict = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0


class BatchRunRequest(BaseModel):
    """Body for POST /batch-runs."""

    student_ids: list[str] = Field(..., min_length=1)
    target_role: str
    target_companies: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    actor_id: str = "system"
    actor_role: Literal["student", "placement_officer", "system"] = "system"
    max_concurrency: int = Field(default=5, ge=1, le=20)


class ApprovalRequest(BaseModel):
    """Body for POST /runs/{run_id}/approve."""

    reviewer_id: str
    decision: Literal["approved", "rejected", "edit_requested", "override"]
    comments: str = ""


class ReviseRequest(BaseModel):
    """Body for POST /runs/{run_id}/revise."""

    reviewer_id: str
    feedback: str
    regenerate_nodes: list[str] = Field(default_factory=list)

