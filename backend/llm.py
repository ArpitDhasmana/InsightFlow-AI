"""LLM abstraction with a deterministic heuristic fallback.

When ``OPENAI_API_KEY`` is set the real OpenAI chat API is used. Otherwise the
``enabled`` flag is False and callers fall back to their own heuristics, so the
whole platform runs offline for demos and tests.
"""
from __future__ import annotations

import json
from typing import Any

from .config import settings


class LLM:
    def __init__(self) -> None:
        self.enabled = settings.llm_enabled
        self._client = None
        if self.enabled:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
            except Exception:
                self.enabled = False

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str | None:
        """Return the model response, or None if the LLM is unavailable."""
        if not self.enabled or self._client is None:
            return None
        try:
            kwargs: dict[str, Any] = {
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
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
