"""Shared LLM client wrapper and structured-response primitives."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Sequence
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from config.settings import Settings
from utils.parser import parse_json_response

logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMAgentError(RuntimeError):
    """Raised when the LLM cannot produce a usable response."""

    def __init__(self, message: str, *, status_code: int | str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseAgent:
    """Base class for agents with retrying text and multimodal generation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self._closed = False

    async def close(self) -> None:
        """Close the underlying async client."""
        if self._closed:
            return
        await self.client.close()
        self._closed = True

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        status = getattr(error, "status_code", None) or getattr(error, "code", None)
        text = str(error).lower()
        return status in {408, 409, 425, 429, 500, 502, 503, 504} or any(
            marker in text
            for marker in ("429", "resource_exhausted", "rate limit", "temporarily unavailable")
        )

    @staticmethod
    def _status_code(error: BaseException) -> int | str | None:
        return getattr(error, "status_code", None) or getattr(error, "code", None)

    @staticmethod
    def _retry_delay(error: BaseException, attempt: int) -> float:
        fallback = min(30.0, 2**attempt) + random.uniform(0.0, 0.75)
        text = str(error)
        match = re.search(
            r"(?:retry(?:\s+after)?|retryDelay)\D{0,20}(\d+(?:\.\d+)?)\s*s",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return fallback
        return min(60.0, max(fallback, float(match.group(1))))

    @classmethod
    def _safe_failure_detail(cls, error: BaseException) -> tuple[int | str | None, str]:
        status = cls._status_code(error)
        text = str(error).lower()
        if status in {401, 403} or "unauthenticated" in text or "authentication" in text:
            return status, (
                "LLM authentication failed. Check your API key and base URL."
            )
        if status == 404 or "not found" in text:
            return status, (
                "The configured LLM model or API endpoint was not found. Check LLM_MODEL."
            )
        if status == 429 or any(marker in text for marker in ("quota", "resource_exhausted", "rate limit")):
            return status, "LLM rate limit or free-tier quota reached. Wait and retry."
        if any(marker in text for marker in ("timeout", "timed out", "connection", "dns")):
            return status, "LLM could not be reached. Check the cloud worker network and retry."
        return status, "LLM returned an unexpected provider error. Check the worker logs for its error type."

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
        
        kwargs = {}
        if response_mime_type == "application/json":
            kwargs["response_format"] = {"type": "json_object"}

        messages = [
            {"role": "system", "content": system_instruction},
        ]
        
        if isinstance(contents, str):
            messages.append({"role": "user", "content": contents})
        elif isinstance(contents, Sequence) and not isinstance(contents, str):
            user_content = ""
            for part in contents:
                if isinstance(part, str):
                    user_content += part + "\n"
                elif hasattr(part, "text"):
                    user_content += part.text + "\n"
                elif hasattr(part, "data") and hasattr(part, "mime_type"):
                    logger.warning("Unsupported part data with mime_type: %s", part.mime_type)
            messages.append({"role": "user", "content": user_content.strip()})
        else:
            messages.append({"role": "user", "content": str(contents)})

        for attempt in range(attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs
                )
                text = (response.choices[0].message.content or "").strip()
                if not text:
                    raise LLMAgentError("LLM returned an empty response")
                return text
            except Exception as error:
                last_error = error
                if attempt == attempts - 1 or not self._is_retryable(error):
                    break
                delay = self._retry_delay(error, attempt)
                logger.warning("Transient LLM error; retrying in %.2fs", delay)
                await asyncio.sleep(delay)
                
        status, detail = self._safe_failure_detail(last_error or RuntimeError("unknown provider error"))
        logger.error(
            "LLM request failed after retries: error_type=%s status=%s",
            type(last_error).__name__ if last_error else "unknown",
            status,
        )
        raise LLMAgentError(detail, status_code=status) from last_error

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
                    "LLM structured response failed validation; retrying model=%s "
                    "schema=%s attempt=%s",
                    self.settings.llm_model,
                    response_model.__name__,
                    attempt + 1,
                )
        raise LLMAgentError(
            f"LLM returned JSON that does not match {response_model.__name__} "
            "after 3 correction attempts"
        ) from last_error

    async def generate_audio_text(self, audio_bytes: bytes, prompt: str) -> str:
        """Interpret an in-memory OGG voice note."""
        if not audio_bytes:
            raise LLMAgentError("The voice message was empty")
            
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.ogg"
        
        try:
            # Check if groq is used based on base_url or model
            is_groq = self.settings.llm_base_url and "groq" in self.settings.llm_base_url.lower()
            model = "whisper-large-v3" if is_groq else "whisper-1"
            
            response = await self.client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                prompt=prompt
            )
            return response.text
        except Exception as error:
            logger.error("Audio transcription failed: %s", str(error))
            raise LLMAgentError(f"Audio transcription failed: {error}")
