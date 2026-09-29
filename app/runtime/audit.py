"""
audit.py — Lab 6: Structured audit logging for runtime execution.

Every meaningful action in the pipeline is logged as an AuditEvent.
Audit events are stored in-process and can be persisted to JSON files.
Sensitive student data (raw resume, personal details) is NOT included;
only metadata and summaries are logged.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.schemas import AuditEvent

_AUDIT_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "audit"


class AuditLogger:
    """
    Structured audit logger for runtime execution.

    Stores events in-memory and optionally persists to disk.
    Thread-safe for single-process use (GIL protected).
    """

    def __init__(self, persist: bool = True) -> None:
        self._events: list[AuditEvent] = []
        self._persist = persist
        if self._persist:
            _AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        run_id: str,
        node: str,
        action: str,
        *,
        agent: str = "",
        batch_id: str | None = None,
        student_id: str | None = None,
        input_summary: dict | None = None,
        output_summary: dict | None = None,
        status: str = "started",
        error: str | None = None,
        retry_count: int = 0,
        checkpoint_id: str | None = None,
        approval_state: str | None = None,
        duration_ms: float | None = None,
    ) -> AuditEvent:
        """Record a single audit event and return it."""
        event = AuditEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            batch_id=batch_id,
            student_id=student_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            node=node,
            agent=agent,
            action=action,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            status=status,
            error=error,
            retry_count=retry_count,
            checkpoint_id=checkpoint_id,
            approval_state=approval_state,
            duration_ms=duration_ms,
        )
        self._events.append(event)
        if self._persist:
            self._persist_event(event)
        return event

    def get_events(self, run_id: str | None = None) -> list[AuditEvent]:
        """Return audit events, optionally filtered by run_id."""
        if run_id is None:
            return list(self._events)
        return [e for e in self._events if e.run_id == run_id]

    def get_events_by_batch(self, batch_id: str) -> list[AuditEvent]:
        """Return audit events for a specific batch."""
        return [e for e in self._events if e.batch_id == batch_id]

    def clear(self) -> None:
        """Clear all in-memory events. For testing only."""
        self._events.clear()

    def _persist_event(self, event: AuditEvent) -> None:
        """Append event to a per-run JSON-lines audit file."""
        try:
            path = _AUDIT_DIR / f"{event.run_id}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.model_dump(), default=str) + "\n")
        except Exception:
            pass  # Never let audit persistence crash the runtime

    def load_events_from_disk(self, run_id: str) -> list[AuditEvent]:
        """Load persisted audit events for a run."""
        path = _AUDIT_DIR / f"{run_id}.jsonl"
        if not path.exists():
            return []
        events = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(AuditEvent(**json.loads(line)))
        return events
