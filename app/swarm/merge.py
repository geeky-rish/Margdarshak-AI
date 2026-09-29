"""
merge.py — Lab 8: Deterministic merge logic for batch results.

Ensures that multi-student batch results are merged according to schema
validation, not by selecting 'the nicest' output. No cross-student data
mixing occurs.
"""

from __future__ import annotations

from app.models.schemas import BatchResult, StudentRunResult


def validate_merge_integrity(batch_result: BatchResult) -> list[str]:
    """
    Validate that a merged batch result maintains data integrity.

    Checks:
      - No duplicate student IDs across result buckets
      - All results have valid schema fields
      - No cross-student data leakage

    Returns:
        List of integrity violation messages (empty = valid).
    """
    violations: list[str] = []

    all_results = (
        batch_result.successful
        + batch_result.failed
        + batch_result.pending_approval
        + batch_result.requires_review
    )

    # Check for duplicate student IDs
    student_ids = [r.student_id for r in all_results]
    seen = set()
    for sid in student_ids:
        if sid in seen:
            violations.append(f"Duplicate student_id '{sid}' in batch results.")
        seen.add(sid)

    # Check run_id uniqueness
    run_ids = [r.run_id for r in all_results]
    seen_runs = set()
    for rid in run_ids:
        if rid in seen_runs and not rid.startswith("failed_"):
            violations.append(f"Duplicate run_id '{rid}' in batch results.")
        seen_runs.add(rid)

    # Check all results have required fields
    for r in all_results:
        if not r.student_id:
            violations.append("Result missing student_id.")
        if not r.run_id:
            violations.append("Result missing run_id.")

    # Verify total_students matches
    if batch_result.total_students != len(all_results):
        violations.append(
            f"total_students ({batch_result.total_students}) does not match "
            f"actual results count ({len(all_results)})."
        )

    return violations


def remerge_batch(batch_result: BatchResult) -> BatchResult:
    """
    Re-classify results in a batch based on current status fields.

    Useful after approval decisions change individual student statuses.
    """
    all_results = (
        batch_result.successful
        + batch_result.failed
        + batch_result.pending_approval
        + batch_result.requires_review
    )

    successful = []
    failed = []
    pending = []
    review = []

    for r in all_results:
        if r.status == "success":
            successful.append(r)
        elif r.status == "failed":
            failed.append(r)
        elif r.status == "pending_approval":
            pending.append(r)
        elif r.status == "requires_review":
            review.append(r)

    scores = [r.readiness_score for r in all_results if r.readiness_score is not None]

    batch_result.successful = successful
    batch_result.failed = failed
    batch_result.pending_approval = pending
    batch_result.requires_review = review
    batch_result.aggregate_metrics = {
        "total_students": batch_result.total_students,
        "completed": len(successful) + len(pending) + len(review),
        "failed": len(failed),
        "avg_readiness_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "min_readiness_score": round(min(scores), 2) if scores else 0.0,
        "max_readiness_score": round(max(scores), 2) if scores else 0.0,
    }

    return batch_result
