"""Voice-note interpretation using Gemini's native multimodal input."""

from __future__ import annotations

from io import BytesIO

from agents.base import BaseAgent, LLMAgentError


class VoiceTranscriber:
    """Transcribe and normalize Telegram OGG voice notes in one Gemini call."""

    def __init__(self, base: BaseAgent) -> None:
        self.base = base

    async def transcribe(self, audio_bytes: bytes) -> str | None:
        """Return a developer task, or None when the audio has no discernible speech."""
        try:
            result = await self.base.generate_audio_text(
                audio_bytes,
                "Transcribe this voice note and turn it into a concise developer instruction.",
            )
        except LLMAgentError:
            raise
        if not result.strip() or result.strip().upper() == "NO_SPEECH":
            return None
        return result.strip()


class SpeechSynthesizer:
    """Best-effort free speech acknowledgement for voice-driven tasks."""

    @staticmethod
    async def synthesize(text: str) -> bytes | None:
        """Return MP3 bytes for Telegram, or None if the optional service is unavailable."""
        def render() -> bytes:
            from gtts import gTTS

            output = BytesIO()
            gTTS(text=text[:700], lang="en", slow=False).write_to_fp(output)
            return output.getvalue()

        try:
            import asyncio

            return await asyncio.to_thread(render)
        except Exception:
            return None
