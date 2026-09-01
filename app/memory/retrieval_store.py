"""
retrieval_store.py — Lab 4: Long-term vector memory using ChromaDB.

This module provides:
    • Storage of historical placement cases.
    • Tag-based retrieval (exact metadata filter).
    • Semantic similarity retrieval using sentence-transformers embeddings.

IMPORTANT SEPARATION:
    RetrievalStore  ← long-term, persistent, ChromaDB-backed
    SessionMemory   ← short-term, in-process, ephemeral

These two components must NEVER be mixed. RunState is never written here.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from app.models.schemas import HistoricalCase

# ---------------------------------------------------------------------------
# Lazy imports so the app starts even if chromadb isn't installed.
# The module degrades gracefully to a JSON-backed fallback.
# ---------------------------------------------------------------------------
try:
    import chromadb
    from chromadb.config import Settings

    _CHROMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    _ST_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ST_AVAILABLE = False

_DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
_CHROMA_DIR = pathlib.Path(__file__).resolve().parents[2] / ".chroma_db"
_COLLECTION_NAME = "placement_history"


class RetrievalStore:
    """
    Long-term ChromaDB-backed store for historical placement cases.

    On first use, it bootstraps itself from placement_history.json. Subsequent
    runs reuse the persisted collection so data survives process restarts.

    If ChromaDB or sentence-transformers are not installed, the store falls
    back to simple JSON-based in-memory search (sufficient for tests and demos).
    """

    def __init__(self, persist_directory: str | None = None) -> None:
        self._persist_dir = persist_directory or str(_CHROMA_DIR)
        self._collection: Any = None
        self._model: Any = None
        self._fallback_data: list[dict] = []
        self._use_fallback = not _CHROMA_AVAILABLE

        if not self._use_fallback:
            self._init_chroma()
        else:
            self._init_fallback()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_chroma(self) -> None:
        """Set up ChromaDB client and collection."""
        client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        if _ST_AVAILABLE:
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

        # Bootstrap from JSON if collection is empty
        if self._collection.count() == 0:
            self._bootstrap_from_json()

    def _init_fallback(self) -> None:
        """Load data into memory for fallback mode."""
        path = _DATA_DIR / "placement_history.json"
        with path.open(encoding="utf-8") as fh:
            self._fallback_data = json.load(fh)

    def _bootstrap_from_json(self) -> None:
        """Populate ChromaDB from the JSON seed file."""
        path = _DATA_DIR / "placement_history.json"
        with path.open(encoding="utf-8") as fh:
            records: list[dict] = json.load(fh)

        for rec in records:
            self._add_record(rec)

    def _add_record(self, rec: dict) -> None:
        """Add a single record to the ChromaDB collection."""
        doc_text = self._record_to_text(rec)
        metadata = {
            "student_id": rec["student_id"],
            "target_role": rec["target_role"],
            "outcome": rec["outcome"],
            "readiness_score": float(rec["readiness_score"]),
            "tags": ",".join(rec.get("tags", [])),
        }
        embedding = self._embed(doc_text)
        kwargs: dict[str, Any] = {
            "ids": [rec["case_id"]],
            "documents": [doc_text],
            "metadatas": [metadata],
        }
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        self._collection.add(**kwargs)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float] | None:
        """Return an embedding vector, or None if sentence-transformers unavailable."""
        if self._model is not None:
            return self._model.encode(text).tolist()
        return None

    @staticmethod
    def _record_to_text(rec: dict) -> str:
        """Convert a historical record to a single descriptive text for embedding."""
        skills_text = ", ".join(
            f"{k} {v}" for k, v in rec.get("skill_levels", {}).items()
        )
        return (
            f"Student targeting {rec['target_role']}. "
            f"Skills: {skills_text}. "
            f"Outcome: {rec['outcome']}. "
            f"Summary: {rec.get('summary', '')} "
            f"Tags: {' '.join(rec.get('tags', []))}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_case(self, record: dict) -> None:
        """
        Add a new historical case to long-term memory.

        Args:
            record: A dict matching the placement_history.json schema.
        """
        if self._use_fallback:
            self._fallback_data.append(record)
        else:
            self._add_record(record)

    def retrieve_by_tags(self, tags: list[str]) -> list[HistoricalCase]:
        """
        Retrieve historical cases that have at least one matching tag.

        Args:
            tags: List of tag strings, e.g. ['software_engineer', 'placed'].

        Returns:
            List of HistoricalCase models, may be empty.
        """
        if self._use_fallback:
            return self._fallback_retrieve_by_tags(tags)
        return self._chroma_retrieve_by_tags(tags)

    def retrieve_similar_students(
        self, query: str, k: int = 5
    ) -> list[HistoricalCase]:
        """
        Retrieve the k most similar historical student cases to the query.

        The query should describe the current student's situation, e.g.:
            "DSA intermediate, Java intermediate, missing OS and CN.
             Target: Software Engineer."

        Args:
            query: Natural language description of the current student profile.
            k:     Maximum number of results to return.

        Returns:
            List of up to k HistoricalCase models, ranked by similarity.
        """
        if self._use_fallback:
            return self._fallback_retrieve_similar(query, k)
        return self._chroma_retrieve_similar(query, k)

    # ------------------------------------------------------------------
    # ChromaDB implementations
    # ------------------------------------------------------------------

    def _chroma_retrieve_by_tags(self, tags: list[str]) -> list[HistoricalCase]:
        """Tag-based retrieval via ChromaDB metadata filter (OR semantics)."""
        results = self._collection.get(
            include=["metadatas", "documents"],
        )
        cases: list[HistoricalCase] = []
        for i, meta in enumerate(results["metadatas"]):
            stored_tags = set(meta.get("tags", "").split(","))
            if any(t in stored_tags for t in tags):
                case_id = results["ids"][i]
                cases.append(self._meta_to_case(case_id, meta))
        return cases

    def _chroma_retrieve_similar(
        self, query: str, k: int
    ) -> list[HistoricalCase]:
        """Semantic similarity retrieval via ChromaDB."""
        query_embedding = self._embed(query)

        if query_embedding is not None:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, self._collection.count()),
                include=["metadatas", "distances"],
            )
        else:
            # No embedding model — fall back to returning first k records
            all_results = self._collection.get(include=["metadatas"])
            cases = [
                self._meta_to_case(all_results["ids"][i], all_results["metadatas"][i])
                for i in range(min(k, len(all_results["ids"])))
            ]
            return cases

        cases: list[HistoricalCase] = []
        for i, meta in enumerate(results["metadatas"][0]):
            case_id = results["ids"][0][i]
            cases.append(self._meta_to_case(case_id, meta))
        return cases

    @staticmethod
    def _meta_to_case(case_id: str, meta: dict) -> HistoricalCase:
        """Convert a ChromaDB metadata dict to a HistoricalCase model."""
        return HistoricalCase(
            case_id=case_id,
            student_id=meta.get("student_id", ""),
            target_role=meta.get("target_role", ""),
            readiness_score=float(meta.get("readiness_score", 0.0)),
            outcome=meta.get("outcome", "not_placed"),
            summary=meta.get("summary", ""),
            tags=meta.get("tags", "").split(",") if meta.get("tags") else [],
        )

    # ------------------------------------------------------------------
    # Fallback (JSON-based) implementations
    # ------------------------------------------------------------------

    def _fallback_retrieve_by_tags(self, tags: list[str]) -> list[HistoricalCase]:
        """Simple tag filter over in-memory list."""
        results: list[HistoricalCase] = []
        tag_set = {t.lower() for t in tags}
        for rec in self._fallback_data:
            stored_tags = {t.lower() for t in rec.get("tags", [])}
            if stored_tags & tag_set:
                results.append(self._rec_to_case(rec))
        return results

    def _fallback_retrieve_similar(
        self, query: str, k: int
    ) -> list[HistoricalCase]:
        """
        Simple keyword overlap similarity for fallback mode.
        Scores each record by how many query words appear in its text.
        """
        query_words = set(query.lower().split())
        scored: list[tuple[float, dict]] = []

        for rec in self._fallback_data:
            rec_text = self._record_to_text(rec).lower()
            overlap = sum(1 for w in query_words if w in rec_text)
            scored.append((overlap, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._rec_to_case(rec) for _, rec in scored[:k]]

    @staticmethod
    def _rec_to_case(rec: dict) -> HistoricalCase:
        """Convert a raw JSON record to a HistoricalCase model."""
        return HistoricalCase(
            case_id=rec.get("case_id", ""),
            student_id=rec.get("student_id", ""),
            target_role=rec.get("target_role", ""),
            readiness_score=float(rec.get("readiness_score", 0.0)),
            outcome=rec.get("outcome", "not_placed"),
            summary=rec.get("summary", ""),
            tags=rec.get("tags", []),
        )
