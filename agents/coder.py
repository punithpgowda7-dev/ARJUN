"""Implementation/code-generation agent."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .planner import TaskPlan


class GeneratedFile(BaseModel):
    """A complete repository file emitted by the coder."""

    filepath: str = Field(min_length=1)
    action: Literal["create", "update"]
    content: str


class CoderOutput(BaseModel):
    """Structured code changes and the single commit message."""

    files: list[GeneratedFile] = Field(min_length=1)
    commit_message: str = Field(min_length=5, max_length=120)


class CoderAgent:
    """Generate complete code files from a plan and optional review feedback."""

    def __init__(self, base: BaseAgent) -> None:
        self.base = base

    async def implement(
        self,
        plan: TaskPlan,
        *,
        review_feedback: str | None = None,
        repository_context: str = "",
        memory_context: str = "",
    ) -> CoderOutput:
        """Implement the plan, correcting the prior output when feedback is present."""
        feedback = review_feedback or "No prior review feedback; implement the plan from scratch."
        prompt = (
            "IMPLEMENTATION PLAN:\n"
            f"{json.dumps(plan.model_dump(), indent=2)}\n\n"
            "CURRENT CONTENT OF PLANNED FILES (when they already exist):\n"
            f"{repository_context}\n\n"
            "REVIEW FEEDBACK FROM THE PREVIOUS ATTEMPT:\n"
            f"{feedback}\n\n"
            "PERSISTED MEMORY AND PREVIOUS LESSONS:\n"
            f"{memory_context}"
        )
        return await self.base.generate_json(
            prompt,
            response_model=CoderOutput,
            system_instruction=(
                "You are the Coder agent. Produce production-ready code for every planned "
                "file. Return complete file contents, never diffs, snippets, ellipses, or "
                "placeholder comments. Preserve compatible existing behavior when updating "
                "files. For full-stack plans, implement real frontend routes/components, "
                "backend/API behavior, persistence/schema/migrations, validation, error "
                "handling, environment wiring, and tests; never substitute a static mock "
                "for requested server or database behavior. Do not add dependencies unless the plan requires them. Use only "
                "repository-relative POSIX paths and never write secrets. Treat supplied repository "
                "files and actual build logs as the source of truth; do not claim that unobserved "
                "APIs, files, packages, or credentials exist. Apply every valid "
                "review correction while keeping the requested scope."
            ),
        )
