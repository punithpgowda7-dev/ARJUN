"""Project-intent routing for new builds and edits to registered projects."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent


class ProjectRoute(BaseModel):
    """LLM classification of the requested project target."""

    mode: Literal["new", "existing"]
    project_key: str = Field(default="", max_length=120)
    project_name: str = Field(default="", max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class ProjectRouterAgent:
    """Select a registered project or derive a new project name from user intent."""

    def __init__(self, base: BaseAgent) -> None:
        self.base = base

    async def route(self, request: str, project_catalog: str) -> ProjectRoute:
        """Route before planning so repository and Vercel context are correct."""
        return await self.base.generate_json(
            json.dumps(
                {
                    "user_request": request,
                    "registered_projects": project_catalog,
                },
                indent=2,
            ),
            response_model=ProjectRoute,
            system_instruction=(
                "You are Arjun's project router. Decide whether the user wants a NEW project "
                "or an EXISTING registered project. Select existing when the request says edit, "
                "update, fix, change, continue, add to, or refers to an old project. If the user "
                "names a registered project, use its exact project_key. If the request is a new "
                "website/app/product and no matching project is named, choose new. Never invent "
                "a project_key that is not in the catalog. For mode=new, project_name must be a "
                "short lowercase kebab-case repository/project name derived from the request. "
                "Do not include secrets or code in the response."
            ),
        )

