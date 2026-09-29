"""
main.py — FastAPI application entry point.

Exposes the Placement Readiness & Career Intelligence Portal REST API.

Endpoints:
    GET  /health
    GET  /llm/status
    POST /clarify
    POST /plan
    POST /analyze
    GET  /students/{student_id}
    GET  /roles/{role_name}
    POST /memory/similar
    POST /run
"""

from __future__ import annotations

# Load .env before anything else so GEMINI_API_KEY is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from app.agents.planner_agent import PlannerAgent
from app.connector.placement_connector import PlacementConnector, UnauthorizedAccessError
from app.coordinator.coordinator import PlacementCoordinator
from app.memory.retrieval_store import RetrievalStore
from app.models.schemas import (
    AccessContext,
    AnalyzeRequest,
    ApprovalRequest,
    BatchRunRequest,
    ClarificationResponse,
    ClarifiedRequest,
    ClarifyRequest,
    CreateStudentRequest,
    GraphState,
    HealthResponse,
    PlanRequest,
    ReadinessAnalysis,
    ReadinessPlan,
    ReadinessReport,
    ReviseRequest,
    RunRequest,
    SimilarStudentsRequest,
    StudentProfile,
    RoleRequirements,
)
from app.tools.readiness_tools import calculate_readiness, get_skill_assessment, validate_inputs
from app.tools.profile_tools import get_student_profile
from app.tools.role_tools import get_role_requirements
from app.skills.plan_skill import PlanSkill, PlanSkillInput

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Placement Readiness & Career Intelligence Portal",
    description=(
        "An agentic AI system that provides deterministic placement readiness "
        "analysis for students. Labs 1–8 implemented."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Singletons — in production these would be dependency-injected
_coordinator = PlacementCoordinator()
_planner = PlannerAgent()
_retrieval = _coordinator.get_retrieval_store()
_plan_skill = PlanSkill()

# Default system context for API calls (no auth enforcement at API level for now)
_SYSTEM_CONTEXT = AccessContext(actor_id="system", actor_role="system")

# Serve static frontend files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(static_dir, "index.html"))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Return API health status."""
    return HealthResponse()


@app.get("/llm/status", tags=["System"])
def llm_status(x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """
    Check whether the Gemini LLM integration is active.

    Returns the model name and availability.
    """
    try:
        from app.services.llm_service import get_llm_service
        svc = get_llm_service(api_key=x_gemini_api_key)
        return {
            "llm_available": svc.is_available(),
            "model": svc._model,
            "enabled": svc._enabled,
            "custom_key_used": bool(x_gemini_api_key and x_gemini_api_key.strip()),
            "note": (
                "Using custom user Gemini API Key"
                if (x_gemini_api_key and x_gemini_api_key.strip())
                else "Using server Gemini API Key"
            ),
        }
    except Exception as e:
        return {"llm_available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Lab 1 — Clarification and Planning
# ---------------------------------------------------------------------------


@app.post("/clarify", tags=["Lab 1 — Agent Loop"])
def clarify(body: ClarifyRequest, x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """
    Clarify a vague placement readiness request.

    Returns either clarifying questions (if request is incomplete) or a
    fully parsed ClarifiedRequest.
    """
    result = _planner.clarify(body.raw_request, api_key=x_gemini_api_key)
    if isinstance(result, ClarificationResponse):
        return {
            "status": "needs_clarification",
            "questions": [q.model_dump() for q in result.questions],
            "message": result.message,
        }
    return {"status": "clarified", "clarified_request": result.model_dump()}


@app.post("/plan", response_model=ReadinessPlan, tags=["Lab 1 — Agent Loop"])
def create_plan(body: PlanRequest, x_gemini_api_key: Optional[str] = Header(None)) -> ReadinessPlan:
    """Create a ReadinessPlan from a ClarifiedRequest."""
    return _planner.create_plan(
        ClarifiedRequest(
            student_id=body.clarified_request.student_id,
            target_role=body.clarified_request.target_role,
            target_companies=body.clarified_request.target_companies,
            focus_areas=body.clarified_request.focus_areas,
        ),
        api_key=x_gemini_api_key
    )


# ---------------------------------------------------------------------------
# Lab 2 — Tool-based data access and analysis
# ---------------------------------------------------------------------------


@app.get("/students", tags=["Lab 2 — Tools"])
def list_students() -> list[dict]:
    """List all registered students."""
    connector = PlacementConnector(_SYSTEM_CONTEXT)
    ids = connector.list_all_student_ids()
    res = []
    for sid in ids:
        try:
            p = connector.get_student_profile(sid)
            res.append({"student_id": p.student_id, "name": p.name, "branch": p.branch, "skills": list(p.skills.keys())})
        except Exception:
            pass
    return res


@app.post("/students", response_model=StudentProfile, tags=["Lab 2 — Tools"])
def create_student(body: CreateStudentRequest) -> StudentProfile:
    """Dynamically register or update a student profile."""
    connector = PlacementConnector(_SYSTEM_CONTEXT)
    return connector.add_student_profile(
        student_id=body.student_id,
        name=body.name,
        branch=body.branch,
        cgpa=body.cgpa,
        skills=body.skills,
        projects=body.projects,
        coding_stats=body.coding_stats,
        dsa_score=body.dsa_score,
        aptitude_score=body.aptitude_score,
        communication_score=body.communication_score,
        mock_interview_score=body.mock_interview_score,
    )


@app.get("/students/{student_id}", response_model=StudentProfile, tags=["Lab 2 — Tools"])
def get_student(student_id: str) -> StudentProfile:
    """Retrieve a student profile through the PlacementConnector."""
    try:
        connector = PlacementConnector(_SYSTEM_CONTEXT)
        return get_student_profile(student_id, connector)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/roles/{role_name}", response_model=RoleRequirements, tags=["Lab 2 — Tools"])
def get_role(role_name: str) -> RoleRequirements:
    """Retrieve role requirements through the PlacementConnector."""
    try:
        connector = PlacementConnector(_SYSTEM_CONTEXT)
        return get_role_requirements(role_name, connector)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/analyze", response_model=ReadinessAnalysis, tags=["Lab 2 — Tools"])
def analyze(body: AnalyzeRequest) -> ReadinessAnalysis:
    """Run deterministic readiness analysis for a student and role."""
    try:
        connector = PlacementConnector(_SYSTEM_CONTEXT)
        profile = get_student_profile(body.student_id, connector)
        role = get_role_requirements(body.role_name, connector)
        assessment = get_skill_assessment(body.student_id, connector)
        validate_inputs(profile, role)
        return calculate_readiness(profile, role, assessment)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# Lab 4 — Memory retrieval
# ---------------------------------------------------------------------------


@app.post("/memory/similar", tags=["Lab 4 — Memory"])
def similar_students(body: SimilarStudentsRequest) -> dict:
    """Retrieve historically similar student cases from long-term memory."""
    cases = _retrieval.retrieve_similar_students(body.query, k=body.k)
    return {
        "query": body.query,
        "k": body.k,
        "results": [c.model_dump() for c in cases],
    }


# ---------------------------------------------------------------------------
# Full workflow run (Labs 1–5)
# ---------------------------------------------------------------------------


@app.post("/run", tags=["Full Workflow"])
def run_workflow(body: RunRequest, x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """
    Execute the complete Labs 1–5 placement readiness workflow.

    Returns the final ReadinessReport with all analysis, plan, and historical
    context included.
    """
    try:
        context = AccessContext(actor_id=body.actor_id, actor_role=body.actor_role)
        state, report = _coordinator.run(
            student_id=body.student_id,
            target_role=body.target_role,
            context=context,
            target_companies=body.target_companies,
            focus_areas=body.focus_areas,
            api_key=x_gemini_api_key,
        )
        return {
            "run_id": state.run_id,
            "report": report.model_dump(),
            "report_text": report.to_text(),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedAccessError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# Lab 7 — Graph pipeline runs
# ---------------------------------------------------------------------------


@app.post("/runs", tags=["Lab 7 — Graph Pipeline"])
def create_graph_run(body: RunRequest, x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """
    Execute the complete Lab 7 agentic node graph pipeline.

    Returns the graph state including readiness analysis, validation,
    and approval status.
    """
    try:
        context = AccessContext(actor_id=body.actor_id, actor_role=body.actor_role)
        state = _coordinator.run_graph(
            student_id=body.student_id,
            target_role=body.target_role,
            context=context,
            target_companies=body.target_companies,
            focus_areas=body.focus_areas,
            api_key=x_gemini_api_key,
        )
        return {
            "run_id": state.run_id,
            "student_id": state.student_id,
            "status": state.status,
            "approval_status": state.approval_status,
            "placement_score": state.placement_score,
            "match_confidence": state.match_confidence,
            "completed_nodes": state.completed_nodes,
            "errors": state.errors,
            "report": state.final_report.model_dump() if state.final_report else None,
            "report_text": state.final_report.to_text() if state.final_report else "",
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedAccessError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/runs/{run_id}/resume", tags=["Lab 7 — Graph Pipeline"])
def resume_graph_run(run_id: str, body: RunRequest, x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """Resume a graph run from its latest checkpoint."""
    try:
        context = AccessContext(actor_id=body.actor_id, actor_role=body.actor_role)
        state = _coordinator.run_graph(
            student_id=body.student_id,
            target_role=body.target_role,
            context=context,
            target_companies=body.target_companies,
            focus_areas=body.focus_areas,
            api_key=x_gemini_api_key,
            resume_from_run_id=run_id,
        )
        return {
            "run_id": state.run_id,
            "status": state.status,
            "approval_status": state.approval_status,
            "completed_nodes": state.completed_nodes,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/runs/{run_id}", tags=["Lab 7 — Graph Pipeline"])
def get_run_status(run_id: str) -> dict:
    """Get the current status and state of a graph run."""
    state = _coordinator.get_graph_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return {
        "run_id": state.run_id,
        "student_id": state.student_id,
        "status": state.status,
        "approval_status": state.approval_status,
        "placement_score": state.placement_score,
        "match_confidence": state.match_confidence,
        "current_node": state.current_node,
        "completed_nodes": state.completed_nodes,
        "errors": state.errors,
        "skill_gap": state.skill_gap,
        "coding_analytics": state.coding_analytics,
        "company_matches": state.company_matches,
        "learning_roadmap": state.learning_roadmap,
        "validation_report": state.validation_report.model_dump() if state.validation_report else None,
    }


@app.get("/runs/{run_id}/audit", tags=["Lab 6 — Runtime"])
def get_run_audit(run_id: str) -> dict:
    """Get the audit trail for a run."""
    events = _coordinator.get_run_audit(run_id)
    return {
        "run_id": run_id,
        "event_count": len(events),
        "events": [e.model_dump() for e in events],
    }


@app.post("/runs/{run_id}/approve", tags=["Lab 7 — Approval Gate"])
def approve_run(run_id: str, body: ApprovalRequest) -> dict:
    """
    Submit a human approval decision for a run.

    Decisions: approved, rejected, edit_requested, override.
    Only placement officers/mentors may approve.
    """
    try:
        state = _coordinator.approve_run(
            run_id=run_id,
            reviewer_id=body.reviewer_id,
            decision=body.decision,
            comments=body.comments,
        )
        return {
            "run_id": state.run_id,
            "student_id": state.student_id,
            "approval_status": state.approval_status,
            "status": state.status,
            "reviewer_feedback": state.reviewer_feedback,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/runs/{run_id}/publish", tags=["Lab 7 — Governed Publish"])
def publish_run(run_id: str) -> dict:
    """Publish approved results. Only works if the run has been approved."""
    try:
        state = _coordinator.publish_run(run_id)
        return {
            "run_id": state.run_id,
            "student_id": state.student_id,
            "status": state.status,
            "approval_status": state.approval_status,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/runs/{run_id}/revise", tags=["Lab 7 — Approval Gate"])
def revise_run(run_id: str, body: ReviseRequest) -> dict:
    """Request revision on a run that was edit_requested."""
    try:
        state = _coordinator.approve_run(
            run_id=run_id,
            reviewer_id=body.reviewer_id,
            decision="edit_requested",
            comments=body.feedback,
        )
        return {
            "run_id": state.run_id,
            "approval_status": state.approval_status,
            "status": state.status,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# Lab 8 — Batch / Swarm
# ---------------------------------------------------------------------------


@app.post("/batch-runs", tags=["Lab 8 — Parallel Swarm"])
def create_batch_run(body: BatchRunRequest, x_gemini_api_key: Optional[str] = Header(None)) -> dict:
    """
    Execute the placement pipeline for multiple students concurrently.

    Each student gets independent state, audit, and validation.
    Failures are isolated — one student's error doesn't affect others.
    """
    try:
        context = AccessContext(actor_id=body.actor_id, actor_role=body.actor_role)
        result = _coordinator.run_batch(
            student_ids=body.student_ids,
            target_role=body.target_role,
            context=context,
            target_companies=body.target_companies,
            focus_areas=body.focus_areas,
            api_key=x_gemini_api_key,
            max_concurrency=body.max_concurrency,
        )
        return result.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedAccessError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/batch-runs/{batch_id}", tags=["Lab 8 — Parallel Swarm"])
def get_batch_status(batch_id: str) -> dict:
    """Get the status and results of a batch run."""
    result = _coordinator.get_batch_result(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")
    return result.model_dump()

