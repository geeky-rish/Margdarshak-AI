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
    ClarificationResponse,
    ClarifiedRequest,
    ClarifyRequest,
    CreateStudentRequest,
    HealthResponse,
    PlanRequest,
    ReadinessAnalysis,
    ReadinessPlan,
    ReadinessReport,
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
        "analysis for students. Labs 1–5 implemented."
    ),
    version="1.0.0",
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
