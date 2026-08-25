"""Implementation/code-generation agent."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .base import BaseAgent
from .planner import PlannedFile, TaskPlan


class GeneratedFile(BaseModel):
    """A complete repository file emitted by the coder."""

    filepath: str = Field(min_length=1)
    action: Literal["create", "update"] = "update"
    content: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def _normalize_action(cls, v: Any) -> str:
        if not isinstance(v, str):
            return "update"
        v_lower = v.strip().lower()
        if v_lower in {"create", "new", "add", "created", "added"}:
            return "create"
        return "update"

    @model_validator(mode="before")
    @classmethod
    def _normalize_generated_file(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "filepath" not in data or not data["filepath"]:
                for alt in ("path", "file", "filename", "name", "file_path", "target_file"):
                    if alt in data and data[alt]:
                        data["filepath"] = str(data[alt])
                        break
            if "content" not in data:
                for alt in ("code", "file_content", "body", "source"):
                    if alt in data:
                        data["content"] = str(data[alt])
                        break
                if "content" not in data:
                    data["content"] = ""
        return data


class CommitMessage(BaseModel):
    """Single-line commit summary for the generated files."""

    commit_message: str = Field(min_length=3, max_length=150, default="feat: implement requested code changes")

    @model_validator(mode="before")
    @classmethod
    def _normalize_commit(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"commit_message": data}
        if isinstance(data, dict):
            if "commit_message" not in data:
                for alt in ("message", "commit", "summary", "title"):
                    if alt in data and data[alt]:
                        data["commit_message"] = str(data[alt])
                        break
                if "commit_message" not in data:
                    data["commit_message"] = "feat: implement requested code changes"
        return data


class CoderOutput(BaseModel):
    """Structured code changes and the single commit message."""

    files: list[GeneratedFile] = Field(min_length=1)
    commit_message: str = Field(min_length=3, max_length=150, default="feat: implement requested code changes")


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
        """Implement the plan one file at a time so Groq TPM limits are not exceeded."""
        feedback = review_feedback or "No prior review feedback; implement the plan from scratch."
        generated: list[GeneratedFile] = []
        for planned in plan.files:
            generated.append(
                await self._implement_file(
                    plan,
                    planned,
                    feedback=feedback,
                    repository_context=repository_context,
                    memory_context=memory_context,
                    sibling_paths=[item.filepath for item in generated],
                )
            )
        commit = await self.base.generate_json(
            json.dumps(
                {
                    "summary": plan.summary,
                    "files": [item.filepath for item in generated],
                },
                separators=(",", ":"),
            ),
            response_model=CommitMessage,
            max_tokens=256,
            system_instruction=(
                "Write one concise conventional-commit style message for these files. "
                "No body, no secrets."
            ),
        )
        return CoderOutput(files=generated, commit_message=commit.commit_message)

    async def _implement_file(
        self,
        plan: TaskPlan,
        planned: PlannedFile,
        *,
        feedback: str,
        repository_context: str,
        memory_context: str,
        sibling_paths: list[str],
    ) -> GeneratedFile:
        prompt = json.dumps(
            {
                "summary": plan.summary,
                "stack": plan.technology_stack,
                "acceptance": plan.acceptance_criteria[:6],
                "target_file": planned.model_dump(),
                "other_planned_paths": [item.filepath for item in plan.files],
                "already_generated_paths": sibling_paths,
                "repository_excerpt": repository_context[:3500],
                "review_feedback": feedback[:1500],
                "memory": memory_context[:500],
            },
            separators=(",", ":"),
        )
        result = await self.base.generate_json(
            prompt,
            response_model=GeneratedFile,
            max_tokens=2500,
            system_instruction=(
                "You are the Coder agent. Produce the complete content for exactly the "
                "target_file path. Return complete file contents, never diffs, snippets, "
                "ellipses, or placeholder comments. The filepath and action must match "
                "target_file. Preserve compatible existing behavior when updating files. "
                "Do not add dependencies unless the plan requires them. Use only "
                "repository-relative POSIX paths and never write secrets. Apply every "
                "valid review correction that affects this file."
            ),
        )
        if result.filepath != planned.filepath or result.action != planned.action:
            return GeneratedFile(
                filepath=planned.filepath,
                action=planned.action,
                content=result.content,
            )
        return result
