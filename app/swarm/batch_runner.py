"""
batch_runner.py — Lab 8: Parallel batch execution with fan-out/fan-in.

Executes the Lab 7 pipeline for multiple students concurrently with:
  - Bounded concurrency (asyncio.Semaphore)
  - Independent per-student state and audit
  - Error isolation (one failure doesn't crash others)
  - Deterministic schema-based merge
"""

from __future__ import annotations

import asyncio
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.models.schemas import (
    AccessContext,
    BatchResult,
    BudgetConfig,
    GraphState,
    StudentRunResult,
)
from app.graph.graph import PlacementGraph
from app.runtime.runtime import Runtime
from app.runtime.audit import AuditLogger

logger = logging.getLogger(__name__)


class BatchRunner:
    """
    Lab 8: Executes the placement readiness pipeline for multiple students
    concurrently with bounded parallelism.

    Architecture:
        batch → fan-out → independent student pipelines → fan-in → merge

    Each student gets:
      - Independent GraphState
      - Independent run_id
      - Independent audit trail
      - Independent checkpoints
      - Independent validation/approval status

    One student's data NEVER leaks into another's context.
    """

    def __init__(
        self,
        budget: BudgetConfig | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self._budget_config = budget or BudgetConfig()
        self._max_concurrency = max(1, min(max_concurrency, 20))
        self._batch_results: dict[str, BatchResult] = {}
        self._batch_audit = AuditLogger(persist=True)

    def run_batch_sync(
        self,
        student_ids: list[str],
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        api_key: str | None = None,
        max_concurrency: int | None = None,
    ) -> BatchResult:
        """
        Synchronous entry point for batch execution.
        Internally uses asyncio for concurrent execution.

        Args:
            student_ids:      List of student IDs to process.
            target_role:      Target role for all students.
            context:          Access context (must be officer/system).
            target_companies: Optional company preferences.
            focus_areas:      Optional focus areas.
            api_key:          Optional LLM API key.
            max_concurrency:  Override default concurrency limit.

        Returns:
            BatchResult with per-student results and aggregate metrics.
        """
        concurrency = max_concurrency or self._max_concurrency

        # Use thread pool for truly concurrent execution
        return self._run_with_threads(
            student_ids=student_ids,
            target_role=target_role,
            context=context,
            target_companies=target_companies,
            focus_areas=focus_areas,
            api_key=api_key,
            max_concurrency=concurrency,
        )

    def _run_with_threads(
        self,
        student_ids: list[str],
        target_role: str,
        context: AccessContext,
        *,
        target_companies: list[str] | None = None,
        focus_areas: list[str] | None = None,
        api_key: str | None = None,
        max_concurrency: int = 5,
    ) -> BatchResult:
        """Execute student pipelines concurrently using thread pool."""
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        start_time = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()

        self._batch_audit.log(
            run_id=batch_id,
            node="batch_runner",
            action="batch_started",
            agent="BatchRunner",
            batch_id=batch_id,
            input_summary={
                "student_count": len(student_ids),
                "target_role": target_role,
                "max_concurrency": max_concurrency,
            },
            status="started",
        )

        results: list[StudentRunResult] = []

        def run_single_student(sid: str) -> StudentRunResult:
            """Execute pipeline for a single student in isolation."""
            student_start = time.monotonic()
            try:
                # Each student gets INDEPENDENT Runtime and Graph
                student_runtime = Runtime(
                    budget=self._budget_config,
                    audit_persist=True,
                )
                graph = PlacementGraph(
                    budget=self._budget_config,
                    runtime=student_runtime,
                )

                state = graph.execute(
                    student_id=sid,
                    target_role=target_role,
                    context=context,
                    target_companies=target_companies,
                    focus_areas=focus_areas,
                    batch_id=batch_id,
                    api_key=api_key,
                )

                duration = (time.monotonic() - student_start) * 1000

                if state.status == "failed":
                    return StudentRunResult(
                        student_id=sid,
                        run_id=state.run_id,
                        status="failed",
                        error="; ".join(state.errors) if state.errors else "Unknown error",
                        duration_ms=duration,
                    )
                elif state.status == "pending_approval":
                    return StudentRunResult(
                        student_id=sid,
                        run_id=state.run_id,
                        status="pending_approval",
                        readiness_score=state.placement_score,
                        approval_status=state.approval_status,
                        report=state.final_report,
                        duration_ms=duration,
                    )
                elif state.match_confidence < 0.5:
                    return StudentRunResult(
                        student_id=sid,
                        run_id=state.run_id,
                        status="requires_review",
                        readiness_score=state.placement_score,
                        approval_status=state.approval_status,
                        report=state.final_report,
                        duration_ms=duration,
                    )
                else:
                    return StudentRunResult(
                        student_id=sid,
                        run_id=state.run_id,
                        status="pending_approval",
                        readiness_score=state.placement_score,
                        approval_status=state.approval_status,
                        report=state.final_report,
                        duration_ms=duration,
                    )

            except Exception as e:
                duration = (time.monotonic() - student_start) * 1000
                return StudentRunResult(
                    student_id=sid,
                    run_id=f"failed_{uuid.uuid4().hex[:8]}",
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                    duration_ms=duration,
                )

        # Fan-out: execute with bounded concurrency via ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {executor.submit(run_single_student, sid): sid for sid in student_ids}
            for future in futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    sid = futures[future]
                    results.append(StudentRunResult(
                        student_id=sid,
                        run_id=f"failed_{uuid.uuid4().hex[:8]}",
                        status="failed",
                        error=str(e),
                    ))

        # Fan-in: merge results
        batch_result = self._merge_results(
            batch_id=batch_id,
            results=results,
            student_ids=student_ids,
            started_at=started_at,
            start_time=start_time,
        )

        self._batch_results[batch_id] = batch_result

        self._batch_audit.log(
            run_id=batch_id,
            node="batch_runner",
            action="batch_completed",
            agent="BatchRunner",
            batch_id=batch_id,
            status="completed",
            output_summary={
                "total": batch_result.total_students,
                "successful": len(batch_result.successful),
                "failed": len(batch_result.failed),
                "pending_approval": len(batch_result.pending_approval),
                "requires_review": len(batch_result.requires_review),
            },
            duration_ms=batch_result.duration_ms,
        )

        return batch_result

    def _merge_results(
        self,
        batch_id: str,
        results: list[StudentRunResult],
        student_ids: list[str],
        started_at: str,
        start_time: float,
    ) -> BatchResult:
        """
        Deterministic schema-based merge of per-student results.

        Groups results by status. Does NOT combine student data.
        Each student's information remains isolated.
        """
        successful = []
        failed = []
        pending_approval = []
        requires_review = []

        for r in results:
            if r.status == "success":
                successful.append(r)
            elif r.status == "failed":
                failed.append(r)
            elif r.status == "pending_approval":
                pending_approval.append(r)
            elif r.status == "requires_review":
                requires_review.append(r)

        # Aggregate metrics (no cross-student data mixing)
        scores = [
            r.readiness_score for r in results
            if r.readiness_score is not None
        ]
        total_duration = (time.monotonic() - start_time) * 1000

        aggregate = {
            "total_students": len(student_ids),
            "completed": len(successful) + len(pending_approval) + len(requires_review),
            "failed": len(failed),
            "avg_readiness_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "min_readiness_score": round(min(scores), 2) if scores else 0.0,
            "max_readiness_score": round(max(scores), 2) if scores else 0.0,
        }

        return BatchResult(
            batch_id=batch_id,
            total_students=len(student_ids),
            successful=successful,
            failed=failed,
            pending_approval=pending_approval,
            requires_review=requires_review,
            aggregate_metrics=aggregate,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=total_duration,
        )

    def get_batch_result(self, batch_id: str) -> BatchResult | None:
        """Retrieve a batch result by ID."""
        return self._batch_results.get(batch_id)

    def get_all_batch_results(self) -> dict[str, BatchResult]:
        """Return all batch results."""
        return dict(self._batch_results)
