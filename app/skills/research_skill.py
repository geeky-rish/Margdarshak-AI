"""
research_skill.py — Lab 3: Research Summary Skill & Reusability Audit.

Implements the research-summary skill according to Lab 3 specifications:
    - SKILL_SPEC metadata dictionary packaging instructions and constraints.
    - Extraction contract (claim, evidence, limitation, takeaway).
    - Fallback discipline ("not stated in source").
    - Automated reusability_check testing schema consistency across inputs.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

SKILL_SPEC: dict[str, Any] = {
    "name": "research_summary",
    "instructions": [
        "identify the single main claim",
        "list supporting evidence for that claim",
        "note at least one limitation (or 'not stated in source' if genuinely absent)",
        "write a 1-sentence undergraduate-level takeaway",
    ],
    "constraints": [
        "never present a hedged claim as unhedged fact",
        "never omit the limitation row, even if the source states none",
    ],
}


class ResearchSummaryOutput(BaseModel):
    """Structured output contract for research summaries."""

    claim: str = Field(..., description="The main claim of the article")
    evidence: str = Field(..., description="Supporting evidence provided in text")
    limitation: str = Field(..., description="Limitations or 'not stated in source'")
    takeaway: str = Field(..., description="Undergraduate-level takeaway")


class ResearchSummarySkill:
    """
    Lab 3 reusable research summary skill.
    """

    def __init__(self) -> None:
        self.spec = SKILL_SPEC

    def summarize(self, article: dict[str, str]) -> dict[str, str]:
        """
        Apply the research summary skill to an article dictionary.
        Must contain 'title' and 'text' keys.
        """
        text = article.get("text", "")
        sentences = [s.strip() for s in text.split(".") if s.strip()]

        if not sentences:
            return {
                "claim": "not stated in source",
                "evidence": "not stated in source",
                "limitation": "not stated in source",
                "takeaway": "Undergraduate takeaway: No text provided.",
            }

        claim = sentences[0]
        evidence = sentences[1] if len(sentences) > 1 else "not stated in source"

        limitation = next(
            (
                s
                for s in sentences
                if any(
                    kw in s.lower()
                    for kw in [
                        "small",
                        "does not include",
                        "unclear",
                        "may not generalize",
                        "limitation",
                        "restricted",
                    ]
                )
            ),
            "not stated in source",
        )

        takeaway = (
            f"Undergraduate takeaway: {claim.strip().rstrip('.')} — verify before generalizing."
        )

        return {
            "claim": claim,
            "evidence": evidence,
            "limitation": limitation,
            "takeaway": takeaway,
        }


def reusability_check(output_a: dict[str, str], output_b: dict[str, str]) -> dict[str, Any]:
    """
    Automated reusability test: verifies identical keys and populated limitation fields.
    """
    keys_a, keys_b = set(output_a.keys()), set(output_b.keys())
    same_structure = keys_a == keys_b
    both_have_limitation = all(o.get("limitation", "") != "" for o in (output_a, output_b))
    is_reusable = same_structure and both_have_limitation

    return {
        "same_structure": same_structure,
        "both_have_limitation": both_have_limitation,
        "is_reusable": is_reusable,
        "conclusion": "SKILL IS REUSABLE" if is_reusable else "SKILL NEEDS TIGHTER INSTRUCTIONS",
    }
