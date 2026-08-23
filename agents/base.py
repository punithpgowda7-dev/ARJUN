"""Shared Gemini client wrapper and structured-response primitives."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Sequence
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from config.settings import Settings
from utils.parser import parse_json_response

logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class GeminiAgentError(RuntimeError):
    """Raised when Gemini cannot produce a usable response."""

    def __init__(self, message: str, *, status_code: int | str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseAgent:
    """Base class for agents with retrying text and multimodal generation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self._closed = False

    async def close(self) -> None:
        """Close the underlying async and sync HTTP clients."""
        if self._closed:
            return
        await self.client.aio.aclose()
        self.client.close()
        self._closed = True

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        """Identify transient provider failures without coupling to one SDK error class."""
        status = getattr(error, "status_code", None) or getattr(error, "code", None)
        text = str(error).lower()
        return status in {408, 409, 425, 429, 500, 502, 503, 504} or any(
            marker in text
            for marker in ("429", "resource_exhausted", "rate limit", "temporarily unavailable")
        )

    @staticmethod
    def _status_code(error: BaseException) -> int | str | None:
        """Extract a provider status without printing provider response bodies."""
        return getattr(error, "status_code", None) or getattr(error, "code", None)

    @staticmethod
    def _retry_delay(error: BaseException, attempt: int) -> float:
        """Respect Gemini's retry hint while keeping one request bounded."""
        fallback = min(30.0, 2**attempt) + random.uniform(0.0, 0.75)
        text = str(error)
        match = re.search(
            r"(?:retry(?:\s+after)?|retryDelay)\D{0,20}(\d+(?:\.\d+)?)\s*s",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return fallback
        # A provider can report a daily reset in its body. Do not freeze the
        # Telegram worker for hours; short rate limits are retried automatically.
        return min(60.0, max(fallback, float(match.group(1))))

    @classmethod
    def _safe_failure_detail(cls, error: BaseException) -> tuple[int | str | None, str]:
        """Map provider failures to actionable, credential-safe Telegram text."""
        status = cls._status_code(error)
        text = str(error).lower()
        if status in {401, 403} or "unauthenticated" in text or "authentication" in text:
            return status, (
                "Gemini authentication failed. Set GEMINI_API_KEY to a Google AI Studio API key "
                "created at https://aistudio.google.com/apikey; do not use a Google OAuth access "
                "token, service-account JSON, or the Telegram/GitHub/Vercel token."
            )
        if status == 404 or "not found" in text:
            return status, (
                "The configured Gemini model or API endpoint was not found. Check GEMINI_MODEL "
                "and use a model available to this API key."
            )
        if status == 429 or any(marker in text for marker in ("quota", "resource_exhausted", "rate limit")):
            return status, "Gemini rate limit or free-tier quota reached. Wait and retry."
        if any(marker in text for marker in ("timeout", "timed out", "connection", "dns")):
            return status, "Gemini could not be reached. Check the cloud worker network and retry."
        return status, "Gemini returned an unexpected provider error. Check the worker logs for its error type."

    async def generate_text(
        self,
        contents: Any,
        *,
        system_instruction: str,
        temperature: float = 0.2,
        attempts: int = 4,
        response_mime_type: str | None = None,
        response_schema: Any = None,
    ) -> str:
        """Generate text with exponential backoff and jitter for transient failures."""
        last_error: BaseException | None = None
        for attempt in range(attempts):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=temperature,
                        response_mime_type=response_mime_type,
                        response_schema=response_schema,
                    ),
                )
                text = (response.text or "").strip()
                if not text:
                    raise GeminiAgentError("Gemini returned an empty response")
                return text
            except Exception as error:  # SDK errors differ across releases.
                last_error = error
                if attempt == attempts - 1 or not self._is_retryable(error):
                    break
                delay = self._retry_delay(error, attempt)
                logger.warning("Transient Gemini error; retrying in %.2fs", delay)
                await asyncio.sleep(delay)
        status, detail = self._safe_failure_detail(last_error or RuntimeError("unknown provider error"))
        logger.error(
            "Gemini request failed after retries: error_type=%s status=%s",
            type(last_error).__name__ if last_error else "unknown",
            status,
        )
        raise GeminiAgentError(detail, status_code=status) from last_error

    async def generate_json(
        self,
        contents: Any,
        *,
        system_instruction: str,
        response_model: type[ModelT],
        temperature: float = 0.1,
    ) -> ModelT:
        """Generate, extract, and validate a JSON response against a Pydantic model."""
        schema = response_model.model_json_schema()
        correction = ""
        last_error: BaseException | None = None
        # A model can return syntactically valid JSON while missing a required
        # field or using the wrong enum. Retry with the validation shape instead
        # of aborting the entire Telegram task.
        for attempt in range(3):
            instruction = (
                f"{system_instruction}\n\nReturn only valid JSON matching this schema:\n{schema}"
                f"{correction}"
            )
            raw = await self.generate_text(
                contents,
                system_instruction=instruction,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_model,
            )
            try:
                return response_model.model_validate(parse_json_response(raw))
            except Exception as error:
                last_error = error
                if attempt == 2:
                    break
                correction = (
                    "\n\nThe previous JSON did not validate. Correct these validation "
                    f"requirements and return the complete object again: {error}."
                )
                logger.warning(
                    "Gemini structured response failed validation; retrying model=%s "
                    "schema=%s attempt=%s",
                    self.settings.gemini_model,
                    response_model.__name__,
                    attempt + 1,
                )
        raise GeminiAgentError(
            f"Gemini returned JSON that does not match {response_model.__name__} "
            "after 3 correction attempts"
        ) from last_error

    async def generate_audio_text(self, audio_bytes: bytes, prompt: str) -> str:
        """Interpret an in-memory OGG voice note as a developer task."""
        if not audio_bytes:
            raise GeminiAgentError("The voice message was empty")
        contents: Sequence[Any] = [
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
            prompt,
        ]
        return await self.generate_text(
            contents,
            system_instruction=(
                "You are a careful speech-to-text and intent extraction service. "
                "Transcribe the audio and rewrite it as one precise developer task. "
                "Return only the task text. If there is no discernible speech, return "
                "the exact marker NO_SPEECH. Do not invent requirements."
            ),
            temperature=0.0,
        )
