"""LLM abstraction over Google Gemini with a deterministic heuristic fallback.

When ``GEMINI_API_KEY`` is set the Gemini API is used. Requests try the primary
model first and fall back to a secondary model if the primary fails, so a single
transient error or model outage does not break the pipeline. If Gemini is
unavailable entirely, ``enabled`` is False and callers use their own heuristics,
so the whole platform still runs offline.
"""
from __future__ import annotations

import json
from typing import Any

from .config import settings


class LLM:
    def __init__(self) -> None:
        self.enabled = settings.llm_enabled
        self._client = None
        self._models = [m for m in (settings.gemini_model, settings.gemini_fallback_model) if m]
        if self.enabled:
            try:
                from google import genai

                self._client = genai.Client(api_key=settings.gemini_api_key)
            except Exception:
                self.enabled = False

    def _generate(self, system: str, user: str, json_mode: bool) -> str | None:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        for model in self._models:
            try:
                resp = self._client.models.generate_content(
                    model=model, contents=user, config=config
                )
                if resp and resp.text:
                    return resp.text
            except Exception:
                continue
        return None

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str | None:
        """Return the model response, or None if the LLM is unavailable."""
        if not self.enabled or self._client is None:
            return None
        try:
            return self._generate(system, user, json_mode)
        except Exception:
            return None

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        raw = self.complete(system, user, json_mode=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None


llm = LLM()
