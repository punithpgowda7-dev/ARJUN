"""Code review and self-correction agent."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .coder import CoderOutput


class ReviewIssue(BaseModel):
    """Actionable issue found during review."""

    filepath: str = Field(min_length=1)
    severity: Literal["blocker", "high", "medium", "low"]
    problem: str = Field(min_length=1)
    correction: str = Field(min_length=1)


class ReviewResult(BaseModel):
    """Review decision and structured feedback for the coder."""

    approved: bool
    summary: str = Field(min_length=1)
    issues: list[ReviewIssue] = Field(default_factory=list)


class ReviewerAgent:
    """Inspect generated code for correctness, security, and completeness."""

    def __init__(self, base: BaseAgent) -> None:
        self.base = base

    async def review(
        self,
        request: str,
        output: CoderOutput,
        *,
        memory_context: str = "",
    ) -> ReviewResult:
        """Review all generated files and return a push/no-push decision."""
        payload = {
            "original_request": request,
            "generated_output": output.model_dump(),
            "memory_context": memory_context,
        }
        return await self.base.generate_json(
            json.dumps(payload, indent=2),
            response_model=ReviewResult,
            system_instruction=(
                "You are the Reviewer agent. Review the generated repository changes as a "
                "strict production gate. Check imports, syntax consistency, edge cases, "
                "security issues, leaked credentials, unsafe path handling, incomplete logic, "
                "and whether the original request is actually satisfied. Approve only when "
                "the code is complete and safe to commit. Report every blocker with a precise "
                "file-specific correction. Low-risk style preferences must not block approval. "
                "Use memory only to check known recurring mistakes; require evidence in the "
                "current generated files before declaring a defect or success."
            ),
        )
