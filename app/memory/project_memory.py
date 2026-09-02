"""
project_memory.py — Lab 4: Multi-Session Scoped Topic Memory & Governance.

Implements Lab 4 specifications:
    - MemoryRecorddataclass with (topic, fact, date, source).
    - Scoped topic retrieval (retrieve(topic)).
    - Permission-gated writes (write(record, user_role)).
    - Conflict detection (receive_statement(topic, new_fact, user_role)).
    - Staleness threshold checking (retention_days).
    - Explicit source tagging in answers ([session], [memory, dated ...]).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Any


@dataclass
class MemoryRecord:
    topic: str
    fact: str
    date: str
    source: str = "memory"


class ProjectMemory:
    """
    Lab 4 Multi-Session Scoped Topic Memory Store.
    """

    def __init__(self, retention_days: int = 30) -> None:
        self.records: list[MemoryRecord] = []
        self.allowed_writers: set[str] = {"placement_officer", "system", "team_lead"}
        self.retention_days = retention_days

    def retrieve(self, topic: str) -> list[MemoryRecord]:
        """Scoped topic retrieval — returns only records matching topic."""
        return [r for r in self.records if r.topic.lower() == topic.lower()]

    def write(self, record: MemoryRecord, user_role: str) -> None:
        """Permission-gated write — raises PermissionError if role is forbidden."""
        if user_role not in self.allowed_writers:
            raise PermissionError(f"role '{user_role}' is not permitted to write memory")
        self.records.append(record)

    def is_stale(self, record: MemoryRecord) -> tuple[bool, int]:
        """Check if record exceeds retention_days threshold."""
        try:
            rec_date = datetime.strptime(record.date, "%Y-%m-%d").date()
            today = date.today()
            age_days = (today - rec_date).days
            return age_days > self.retention_days, age_days
        except Exception:
            return False, 0


class ProjectAssistant:
    """
    Lab 4 Project Assistant enforcing source-tagged answers, conflict checks, and staleness warnings.
    """

    def __init__(self, memory: ProjectMemory) -> None:
        self.memory = memory
        self.session_facts: dict[str, str] = {}

    def answer(self, topic: str, question: str) -> str:
        """
        Produce a source-tagged answer explicitly attributing memory origin.
        """
        # 1. Check session state first
        if topic in self.session_facts:
            return f"[session] {question} → Current session state: {self.session_facts[topic]}"

        # 2. Check scoped memory
        hits = self.memory.retrieve(topic)
        if not hits:
            return f"[session] No stored decision on '{topic}' yet."

        latest = hits[-1]
        stale, age = self.memory.is_stale(latest)
        staleness_msg = f" (⚠️ WARNING: decision is {age} days old and may be stale)" if stale else ""

        return (
            f"[memory, dated {latest.date}] Per decision on {latest.date}{staleness_msg}, "
            f"'{latest.fact}'"
        )

    def receive_statement(
        self, topic: str, new_fact: str, user_role: str
    ) -> dict[str, Any]:
        """
        Check for conflict with existing stored decision before writing memory.
        """
        hits = self.memory.retrieve(topic)
        if hits and hits[-1].fact.lower() != new_fact.lower():
            return {
                "conflict": True,
                "stored": hits[-1].fact,
                "stored_date": hits[-1].date,
                "new": new_fact,
                "message": (
                    f"This conflicts with stored decision from {hits[-1].date} "
                    f"('{hits[-1].fact}'). Should memory be updated to '{new_fact}'?"
                ),
            }

        # No conflict — write statement (permission-gated)
        record = MemoryRecord(topic=topic, fact=new_fact, date=str(date.today()))
        self.memory.write(record, user_role)
        return {
            "conflict": False,
            "message": f"Recorded: {new_fact}",
            "written": True,
        }
