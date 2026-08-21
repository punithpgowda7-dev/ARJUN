"""Defensive extraction helpers for model responses."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*(.*?)\s*```\s*$", re.DOTALL)


def strip_markdown_fence(value: str) -> str:
    """Remove a surrounding Markdown code fence, if present."""
    match = _FENCE_RE.match(value.strip())
    return match.group(1).strip() if match else value.strip()


def parse_json_response(value: str) -> Any:
    """Parse strict JSON or recover the first valid object/array from model prose."""
    cleaned = strip_markdown_fence(value)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(cleaned[index:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise ValueError("No valid JSON object or array found in model response") from original_error
