"""
llm_service.py — Gemini LLM integration (PRIMARY intelligence layer).

Gemini is the primary LLM for this project. It handles:
  • Intelligent request parsing (clarify_request)
  • Natural clarification question generation
  • AI executive summaries in readiness reports (summarise_readiness)

The deterministic heuristics in PlannerAgent are a SAFETY NET only —
they kick in automatically if:
  (a) GEMINI_API_KEY is not set in .env, or
  (b) google-genai package is not installed, or
  (c) a specific Gemini API call fails (network/quota issue)

This design ensures the system never crashes but always uses Gemini
when your key is available.

Configuration (.env):
  GEMINI_API_KEY = your key
  GEMINI_MODEL   = gemini-2.0-flash   (default; change to any valid Gemini model)
  LLM_ENABLED    = true               (set to false to force deterministic mode)

Note on model "gemini-3.6-flash":
  This model name does not exist in the Gemini API as of Sep 2026.
  GEMINI_MODEL defaults to "gemini-2.0-flash" which is the fastest available.
  You can set any valid model name in .env.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import — don't crash if google-genai isn't installed
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.warning("google-genai not installed. LLM features will be disabled.")

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env won't be auto-loaded but os.environ still works


class LLMService:
    """
    Thin wrapper around the Gemini API (google-genai SDK).

    All agent code calls this service. If the API key is missing or
    the library is not installed, is_available() returns False and
    callers transparently fall back to deterministic logic.

    This keeps the core system runnable with NO paid API dependency.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key if (api_key and api_key.strip()) else os.getenv("GEMINI_API_KEY", "").strip()
        self._api_key: str | None = key or None
        self._model: str = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self._enabled: bool = os.getenv("LLM_ENABLED", "true").lower() == "true"
        self._client = None

        if self._enabled and self._api_key and _GENAI_AVAILABLE:
            try:
                self._client = genai.Client(api_key=self._api_key)
                logger.info(f"LLMService initialised with model={self._model}")
            except Exception as e:
                logger.warning(f"Failed to initialise Gemini client: {e}")
                self._client = None

    def is_available(self) -> bool:
        """Return True if the Gemini API is configured and accessible."""
        return self._client is not None

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> Optional[str]:
        """
        Generate text using Gemini. Returns None if LLM is unavailable.

        Args:
            prompt:             The user-facing prompt.
            system_instruction: Optional system-level instruction.
            temperature:        Sampling temperature (0 = deterministic).
            max_tokens:         Maximum output tokens.

        Returns:
            Generated text string, or None if LLM is unavailable.
        """
        if not self.is_available():
            return None

        try:
            config = genai_types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                system_instruction=system_instruction or (
                    "You are an expert placement readiness analyst for engineering students. "
                    "Be concise, specific, and actionable."
                ),
            )
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")
            return None

    def clarify_request(self, raw_request: str) -> Optional[dict]:
        """
        Use Gemini to extract student_id, target_role, companies, focus_areas
        from a natural language request.

        Returns a dict with extracted fields, or None to use deterministic fallback.

        Example response structure:
            {
                "student_id": "student_001" | null,
                "target_role": "Software Engineer" | null,
                "target_companies": ["TCS"],
                "focus_areas": ["DSA"],
                "missing_fields": ["student_id"]
            }
        """
        if not self.is_available():
            return None

        prompt = f"""
Analyse this placement readiness request from a student:

REQUEST: "{raw_request}"

Extract the following information as JSON. Use null for any field not mentioned.

{{
    "student_id": "<student ID mentioned (e.g. student_001, student_004, etc.), or null if not mentioned>",
    "target_role": "<target role mentioned (e.g. Software Engineer, Data Analyst, ML Engineer, DevOps Engineer, etc.), or null>",
    "target_companies": ["<company names mentioned, empty list if none>"],
    "focus_areas": ["<skill areas to focus on, empty list if none>"],
    "missing_fields": ["<list of field names that are null/missing>"]
}}

Return ONLY valid JSON. No explanation or markdown.
"""
        response = self.generate(prompt, temperature=0.1)
        if not response:
            return None

        try:
            import json
            # Strip any accidental markdown fences
            cleaned = response.strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except Exception:
            return None

    def enhance_clarification_questions(
        self, raw_request: str, missing_fields: list[str]
    ) -> Optional[list[dict]]:
        """
        Use Gemini to generate more natural clarification questions for missing fields.

        Returns list of {field, question} dicts, or None to use default questions.
        """
        if not self.is_available() or not missing_fields:
            return None

        prompt = f"""
A student submitted this placement readiness request:
"{raw_request}"

The following information is missing: {', '.join(missing_fields)}

Generate one concise, friendly clarification question for each missing field.
Return as JSON array:
[
  {{"field": "<field_name>", "question": "<question text>"}},
  ...
]

Return ONLY valid JSON array. No markdown.
"""
        response = self.generate(prompt, temperature=0.4)
        if not response:
            return None

        try:
            import json
            cleaned = response.strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except Exception:
            return None

    def summarise_readiness(
        self,
        student_name: str,
        target_role: str,
        score: float,
        strengths: list[str],
        gaps: list[str],
    ) -> Optional[str]:
        """
        Use Gemini to write a natural language executive summary for the readiness report.

        Returns a 2-3 sentence summary string, or None to skip LLM summary.
        """
        if not self.is_available():
            return None

        prompt = f"""
Write a 2-3 sentence placement readiness summary for this student.
Be direct and encouraging but honest.

Student: {student_name}
Target Role: {target_role}
Readiness Score: {score:.1f}/100
Strengths: {', '.join(strengths) if strengths else 'None identified'}
Skill Gaps: {', '.join(gaps) if gaps else 'None'}

Return ONLY the summary paragraph. No headers.
"""
        return self.generate(prompt, temperature=0.5, max_tokens=200)

    def generate_plan_steps(
        self,
        student_id: str,
        target_role: str,
        focus_areas: list[str] = None,
        target_companies: list[str] = None,
    ) -> Optional[list[str]]:
        """
        Use Gemini to generate a tailored preparation roadmap for the student and role.

        Returns a list of action step strings, or None to fall back.
        """
        if not self.is_available():
            return None

        prompt = f"""
Generate 6 specific, actionable placement preparation roadmap steps for student '{student_id}' preparing for the role of '{target_role}'.
Focus areas: {', '.join(focus_areas) if focus_areas else 'General preparation'}
Target companies: {', '.join(target_companies) if target_companies else 'General companies'}

Format as a simple numbered list, one step per line (1. Step one, 2. Step two, etc).
Be direct, specific to {target_role}, and concise.
"""
        response = self.generate(prompt, temperature=0.3, max_tokens=1000)
        if not response:
            return None

        import re
        steps = []
        for line in response.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            # Strip leading numbers/bullets like "1.", "1)", "-", "*", "Step 1:"
            cleaned = re.sub(r'^(?:step\s*\d+:?|\d+[\.\)]|[\-\*\•])\s*', '', line, flags=re.IGNORECASE).strip()
            cleaned = cleaned.replace("**", "")
            if len(cleaned) > 5:
                steps.append(cleaned)

        if len(steps) >= 3:
            return steps
        return None


# Singleton instance — import this in other modules
_llm_service: LLMService | None = None


def get_llm_service(api_key: str | None = None) -> LLMService:
    """Get the global LLMService singleton or a custom instance if api_key is provided."""
    global _llm_service
    if api_key and api_key.strip():
        return LLMService(api_key=api_key.strip())
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
