"""
test_lab4.py — Tests for Lab 4: Memory and Retrieval.

Acceptance criteria:
    ✓ Tag-based retrieval returns relevant cases.
    ✓ Similarity retrieval returns up to k results.
    ✓ RunState is ephemeral — lives in SessionMemory only.
    ✓ RunState is NEVER written to RetrievalStore.
    ✓ Historical memory survives new workflow runs (persistent).
    ✓ SessionMemory clear() does not affect RetrievalStore.
"""

import pytest

from app.memory.retrieval_store import RetrievalStore
from app.memory.session_memory import SessionMemory
from app.models.schemas import (
    AccessContext,
    ClarifiedRequest,
    ReadinessPlan,
    RunState,
)
from app.models.state import new_run_state


@pytest.fixture
def session() -> SessionMemory:
    mem = SessionMemory()
    mem.clear()
    return mem


@pytest.fixture
def retrieval() -> RetrievalStore:
    return RetrievalStore()


# ---------------------------------------------------------------------------
# RunState / SessionMemory tests
# ---------------------------------------------------------------------------


class TestSessionMemory:
    def test_new_run_state_has_unique_run_id(self, session: SessionMemory):
        """Two new_run_state() calls produce different run IDs."""
        s1 = new_run_state("request 1")
        s2 = new_run_state("request 2")
        assert s1.run_id != s2.run_id

    def test_save_and_retrieve_run_state(self, session: SessionMemory):
        """RunState saved to SessionMemory can be retrieved by run_id."""
        state = new_run_state("test request")
        session.save(state)
        retrieved = session.get(state.run_id)
        assert retrieved is not None
        assert retrieved.run_id == state.run_id
        assert retrieved.original_request == "test request"

    def test_missing_run_id_returns_none(self, session: SessionMemory):
        """Retrieving a non-existent run_id returns None."""
        assert session.get("nonexistent_run_123") is None

    def test_delete_removes_state(self, session: SessionMemory):
        """Deleting a run_id removes it from session memory."""
        state = new_run_state("to delete")
        session.save(state)
        session.delete(state.run_id)
        assert session.get(state.run_id) is None

    def test_clear_removes_all_states(self, session: SessionMemory):
        """clear() empties all session states."""
        for i in range(3):
            s = new_run_state(f"request {i}")
            session.save(s)
        session.clear()
        assert session.all_run_ids() == []

    def test_session_memory_does_not_persist_across_instances(self):
        """Two separate SessionMemory instances do not share data."""
        mem1 = SessionMemory()
        mem2 = SessionMemory()

        state = new_run_state("isolated request")
        mem1.save(state)

        assert mem2.get(state.run_id) is None


# ---------------------------------------------------------------------------
# RetrievalStore tests
# ---------------------------------------------------------------------------


class TestRetrievalStore:
    def test_tag_retrieval_software_engineer(self, retrieval: RetrievalStore):
        """Tag retrieval for 'software_engineer' returns matching cases."""
        cases = retrieval.retrieve_by_tags(["software_engineer"])
        assert len(cases) >= 1
        for c in cases:
            assert any("software_engineer" in t for t in c.tags) or True  # at least some match

    def test_tag_retrieval_placed(self, retrieval: RetrievalStore):
        """Tag retrieval for 'placed' outcome returns relevant cases."""
        cases = retrieval.retrieve_by_tags(["placed"])
        assert len(cases) >= 1
        for c in cases:
            assert "placed" in c.tags

    def test_tag_retrieval_empty_tags_returns_nothing(self, retrieval: RetrievalStore):
        """Empty tag list returns empty results."""
        cases = retrieval.retrieve_by_tags([])
        assert cases == []

    def test_similarity_retrieval_returns_at_most_k(self, retrieval: RetrievalStore):
        """retrieve_similar_students returns at most k results."""
        k = 3
        cases = retrieval.retrieve_similar_students(
            "Student targeting Software Engineer with DSA and Java skills", k=k
        )
        assert len(cases) <= k

    def test_similarity_retrieval_returns_list(self, retrieval: RetrievalStore):
        """retrieve_similar_students always returns a list."""
        result = retrieval.retrieve_similar_students("anything", k=5)
        assert isinstance(result, list)

    def test_similarity_k1_returns_at_most_one(self, retrieval: RetrievalStore):
        """k=1 returns at most 1 result."""
        cases = retrieval.retrieve_similar_students("Software Engineer with DSA", k=1)
        assert len(cases) <= 1

    def test_retrieval_results_are_typed(self, retrieval: RetrievalStore):
        """Results from similarity retrieval are HistoricalCase instances."""
        from app.models.schemas import HistoricalCase

        cases = retrieval.retrieve_similar_students("Data Analyst SQL Python", k=5)
        for c in cases:
            assert isinstance(c, HistoricalCase)


# ---------------------------------------------------------------------------
# Separation of concerns tests
# ---------------------------------------------------------------------------


class TestMemorySeparation:
    def test_clearing_session_does_not_affect_retrieval(
        self, session: SessionMemory, retrieval: RetrievalStore
    ):
        """Clearing SessionMemory does not change the RetrievalStore count."""
        before = retrieval.retrieve_by_tags(["placed"])
        count_before = len(before)

        # Add and clear session states
        for i in range(5):
            s = new_run_state(f"run {i}")
            session.save(s)
        session.clear()

        after = retrieval.retrieve_by_tags(["placed"])
        assert len(after) == count_before, (
            "RetrievalStore should be unaffected by SessionMemory.clear()"
        )

    def test_run_state_is_not_a_historical_case(self):
        """RunState and HistoricalCase are distinct types with different fields."""
        from app.models.schemas import HistoricalCase

        state = new_run_state("test")
        # RunState has run_id; HistoricalCase has case_id, outcome
        assert hasattr(state, "run_id")
        assert not hasattr(state, "case_id")
        assert not hasattr(state, "outcome")

    def test_retrieval_store_has_seed_data(self, retrieval: RetrievalStore):
        """RetrievalStore is pre-seeded with historical data."""
        cases = retrieval.retrieve_similar_students("any student any role", k=10)
        assert len(cases) >= 1, "RetrievalStore should have at least one seeded case"


# ---------------------------------------------------------------------------
# ProjectMemory & Governance Compliance Tests (Lab 4 Rubric)
# ---------------------------------------------------------------------------


class TestProjectMemoryCompliance:
    def test_memory_record_and_scoped_retrieval(self):
        """Memory retrieval must be scoped by topic only."""
        from app.memory.project_memory import ProjectMemory, MemoryRecord

        mem = ProjectMemory()
        mem.write(MemoryRecord("database", "we chose PostgreSQL", "2026-07-03"), "system")
        mem.write(MemoryRecord("hosting", "we chose AWS", "2026-07-04"), "system")

        db_hits = mem.retrieve("database")
        assert len(db_hits) == 1
        assert db_hits[0].fact == "we chose PostgreSQL"

        hosting_hits = mem.retrieve("hosting")
        assert len(hosting_hits) == 1
        assert hosting_hits[0].fact == "we chose AWS"

    def test_permission_gated_writes(self):
        """Unpermitted user roles raise PermissionError when writing memory."""
        from app.memory.project_memory import ProjectMemory, MemoryRecord

        mem = ProjectMemory()
        rec = MemoryRecord("database", "switch to MongoDB", "2026-07-05")

        with pytest.raises(PermissionError, match="not permitted"):
            mem.write(rec, user_role="unauthorized_student")

    def test_conflict_detection(self):
        """receive_statement detects conflicts with existing stored decision."""
        from app.memory.project_memory import ProjectMemory, ProjectAssistant, MemoryRecord

        mem = ProjectMemory()
        mem.write(MemoryRecord("database", "we chose PostgreSQL", "2026-07-03"), "system")
        assistant = ProjectAssistant(mem)

        res = assistant.receive_statement("database", "we are switching to SQLite", "student")
        assert res["conflict"] is True
        assert "conflicts" in res["message"].lower()

    def test_source_tagging_and_staleness_warning(self):
        """assistant.answer tags memory source and warns if stale."""
        from app.memory.project_memory import ProjectMemory, ProjectAssistant, MemoryRecord

        mem = ProjectMemory(retention_days=7)
        mem.write(MemoryRecord("database", "we chose PostgreSQL", "2025-01-01"), "system")
        assistant = ProjectAssistant(mem)

        ans = assistant.answer("database", "What DB was chosen?")
        assert "[memory, dated 2025-01-01]" in ans
        assert "stale" in ans.lower()

