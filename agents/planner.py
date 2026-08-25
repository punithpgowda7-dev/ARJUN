"""Architecture and file-change planning agent."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent


class PlannedFile(BaseModel):
    """One file in the requested implementation plan."""

    filepath: str = Field(min_length=1)
    action: Literal["create", "update"]
    purpose: str = Field(min_length=1)
    implementation_notes: list[str] = Field(default_factory=list)


class EnvironmentRequirement(BaseModel):
    """An application configuration value the implementation may need."""

    key: str = Field(min_length=2, max_length=128)
    purpose: str = Field(min_length=1)
    required: bool = True
    secret: bool = True


class TechnologyDecision(BaseModel):
    """A material architecture choice that should be confirmed by the user."""

    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=4)
    context: str = Field(min_length=1)


class TaskPlan(BaseModel):
    """Structured architecture plan produced before code generation."""

    summary: str = Field(min_length=1)
    files: list[PlannedFile] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    technology_stack: list[str] = Field(default_factory=list)
    test_strategy: list[str] = Field(default_factory=list)
    environment_variables: list[EnvironmentRequirement] = Field(default_factory=list)
    technology_decisions: list[TechnologyDecision] = Field(default_factory=list)


class TechnologyDecisionResult(BaseModel):
    """The planner's recommendation when the user asks Arjun to decide."""

    choice: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class PlannerAgent:
    """Turn a natural-language request into a bounded, implementable file plan."""

    def __init__(self, base: BaseAgent) -> None:
        self.base = base

    async def plan(
        self,
        request: str,
        *,
        repository_context: str = "",
        memory_context: str = "",
    ) -> TaskPlan:
        """Create a plan with paths, purposes, logic, and acceptance criteria."""
        
        # New Brain Expansion Phase: Pre-planning investigation with Antigravity SDK
        investigation_notes = ""
        try:
            from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
            import logging
            
            # Spin up an Antigravity Agent with MCP tools for deep investigation
            config = LocalAgentConfig(
                system_instructions=(
                    "You are an architecture investigator. Analyze the user request and repository context. "
                    "Use your tools (like Figma MCP or sequential-thinking) to break down the problem. "
                    "Output brief architectural notes to guide the JSON code generation phase."
                ),
                capabilities=CapabilitiesConfig()
            )
            async with Agent(config) as mcp_agent:
                inv_prompt = f"REQUEST:\n{request}\n\nREPO:\n{repository_context}\n\nInvestigate and summarize key findings."
                response = await mcp_agent.chat(inv_prompt)
                
                # Stream the response tokens
                notes_chunks = []
                async for token in response:
                    notes_chunks.append(token)
                investigation_notes = "".join(notes_chunks)
        except ImportError:
            pass # Fallback if google-antigravity SDK is not installed yet
        except Exception as e:
            # Log but don't block the build if MCP investigation fails
            import logging
            logging.getLogger(__name__).warning(f"MCP Investigation failed: {e}")

        prompt = (
            f"USER REQUEST:\n{request}\n\n"
            f"REPOSITORY CONTEXT:\n{repository_context}\n\n"
            f"MEMORY CONTEXT:\n{memory_context}\n\n"
            f"INVESTIGATION NOTES (MCP):\n{investigation_notes}"
        )
        return await self.base.generate_json(
            prompt,
            response_model=TaskPlan,
            max_tokens=2048,
            system_instruction=(
                "You are the Planner agent in a production software repository. "
                "Analyze the developer request and plan a complete implementation. "
                "CRITICAL - SIMPLICITY SIGNALS: If the user says 'simple', 'static', "
                "'no database', 'no .env', 'no environment variables', 'no login', "
                "'no backend', or 'plain HTML', you MUST plan a fully static implementation "
                "using only HTML, CSS, and JavaScript files. Do NOT plan Flask, Django, "
                "SQLite, PostgreSQL, any server framework, or any environment variables. "
                "The environment_variables list MUST be empty [] for static sites. "
                "Use localStorage or in-memory JS state for any data the user needs to store. "
                "CRITICAL - ENV VARIABLES: Only add items to environment_variables when the "
                "request genuinely requires a secret API key, OAuth token, or external service "
                "credential. Never invent environment variables for a path, a port, or a "
                "configuration value that can be hardcoded or has a safe default. "
                "For a full-stack request (when user does NOT say simple/static), explicitly "
                "cover the frontend, backend/API, database schema and access layer, environment "
                "configuration, deployment configuration, and tests. "
                "Respect the existing repository context supplied by the user. Treat only "
                "current repository files and explicit build output as codebase evidence. "
                "Use prior memory for warnings and continuity, never as proof that a file "
                "still exists. Use repository-relative POSIX paths; never include secrets, generated "
                "binaries, or vague placeholder files. Each file must have concrete "
                "implementation notes. Select a practical technology stack compatible with "
                "the repository and make acceptance criteria and test strategy executable. "
                "Add technology_decisions only for genuinely material choices with two or more "
                "reasonable options; never ask the user about trivial implementation details. "
                "Keep the plan compact: at most 6 files for a simple/static site, short notes, "
                "and empty technology_decisions unless a real choice exists."
            ),
        )

    async def decide(
        self,
        request: str,
        decision: TechnologyDecision,
        *,
        repository_context: str = "",
        memory_context: str = "",
    ) -> TechnologyDecisionResult:
        """Compare options using repository evidence when the user replies DO."""
        prompt = (
            f"REQUEST:\n{request}\n\nDECISION:\n{json.dumps(decision.model_dump(), indent=2)}\n\n"
            f"REPOSITORY EVIDENCE:\n{repository_context}\n\nMEMORY WARNINGS:\n{memory_context}"
        )
        return await self.base.generate_json(
            prompt,
            response_model=TechnologyDecisionResult,
            max_tokens=512,
            system_instruction=(
                "You are the architecture decision agent. Choose exactly one supplied option. "
                "Compare compatibility with the current repository, security, operational "
                "complexity, maintenance, performance, free-tier cost, and testability. "
                "Do not invent unavailable credentials or claim that an unobserved package is installed."
            ),
        )

    @staticmethod
    def as_prompt(plan: TaskPlan) -> str:
        """Serialize a plan for the coder agent without losing structure."""
        return json.dumps(plan.model_dump(), indent=2)
