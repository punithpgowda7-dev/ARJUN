"""Vercel REST API integration for environment sync and deployments."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from config.settings import Settings

logger = logging.getLogger(__name__)


class VercelError(RuntimeError):
    """Raised when Vercel cannot accept or complete an operation."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class EnvironmentSyncResult:
    """Non-secret summary of the environment synchronization."""

    synced: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VercelProjectResult:
    """Vercel project identity after discovery or automatic provisioning."""

    project_id: str
    name: str
    dashboard_url: str


@dataclass(frozen=True, slots=True)
class VercelDeploymentResult:
    """Deployment state and links returned by Vercel."""

    deployment_id: str
    state: str
    url: str
    dashboard_url: str
    error_summary: str = ""

    @property
    def ready(self) -> bool:
        """Return whether the deployment reached a usable state."""
        return self.state == "READY" and bool(self.url)


class VercelService:
    """Call Vercel without exposing configured secret values to the LLM."""

    _base_url = "https://api.vercel.com"
    _blocked_env_keys = {
        "TELEGRAM_BOT_TOKEN",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "VERCEL_TOKEN",
        "ARJUN_SECRET_KEY",
        "TELEGRAM_ALLOWED_USERS",
        "GITHUB_REPO",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=15.0),
            headers={
                "Authorization": f"Bearer {settings.vercel_token}",
                "Content-Type": "application/json",
            },
        )

    @property
    def enabled(self) -> bool:
        """Return whether the service can deploy or provision a project."""
        return bool(self.settings.vercel_token)

    def _params(self) -> dict[str, str]:
        """Build team scoping parameters without sending empty values."""
        return {"teamId": self.settings.vercel_team_id} if self.settings.vercel_team_id else {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        """Make an API request and turn provider errors into safe exceptions."""
        response = await self.client.request(
            method,
            path,
            json=json,
            params={**self._params(), **(params or {})},
        )
        if response.is_error:
            detail = response.text[:500].replace("\n", " ")
            raise VercelError(
                f"Vercel API {response.status_code}: {detail}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        return response.json()

    async def ensure_project(
        self,
        *,
        repository_name: str,
        production_branch: str,
    ) -> VercelProjectResult:
        """Find the configured project or create/link it to the GitHub repository."""
        if not self.settings.vercel_token:
            raise VercelError("Set VERCEL_TOKEN to enable automatic Vercel provisioning")

        project_name = self._project_name(repository_name)
        project_ref = (
            self.settings.vercel_project_id
            or self.settings.vercel_project_name
            or project_name
        )
        if project_ref:
            try:
                project = await self._request("GET", f"/v9/projects/{project_ref}")
                project_id = str(project.get("id") or project_ref)
                self.settings.vercel_project_id = project_id
                return self._project_result(project_id, project)
            except VercelError as error:
                if error.status_code != 404 or not self.settings.vercel_auto_create_project:
                    raise

        if not self.settings.vercel_auto_create_project:
            raise VercelError(
                "Vercel project not found. Set VERCEL_PROJECT_ID or enable "
                "VERCEL_AUTO_CREATE_PROJECT."
            )

        try:
            project = await self._request(
                "POST",
                "/v11/projects",
                json={
                    "name": project_name,
                    "gitRepository": {
                        "type": "github",
                        "repo": f"https://github.com/{repository_name}",
                    },
                },
            )
        except VercelError as error:
            raise VercelError(
                "Vercel project provisioning failed. Authorize the Vercel GitHub "
                "integration for this repository, then retry. "
                f"Provider detail: {error}"
            ) from error

        project_id = str(project.get("id") or project.get("projectId") or "")
        if not project_id:
            raise VercelError("Vercel project provisioning returned no project ID")
        self.settings.vercel_project_id = project_id
        self.settings.vercel_project_name = str(project.get("name") or project_name)
        del production_branch  # Vercel uses the repository default branch on creation.
        return self._project_result(project_id, project)

    def _project_result(self, project_id: str, project: dict[str, Any]) -> VercelProjectResult:
        """Normalize a Vercel project response."""
        name = str(project.get("name") or self.settings.vercel_project_name or project_id)
        self.settings.vercel_project_name = name
        return VercelProjectResult(
            project_id=project_id,
            name=name,
            dashboard_url=f"https://vercel.com/{name}",
        )

    @staticmethod
    def _project_name(repository_name: str) -> str:
        """Convert a GitHub repository name into a valid stable Vercel project name."""
        raw = repository_name.rsplit("/", 1)[-1].lower()
        normalized = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
        return (normalized or "arjun-project")[:100]

    async def sync_environment(
        self,
        values: Mapping[str, str] | None = None,
    ) -> EnvironmentSyncResult:
        """Create or update explicitly allow-listed worker environment variables."""
        if not self.enabled or (not self.settings.vercel_sync_env_keys and not values):
            return EnvironmentSyncResult()

        project_id = self.settings.vercel_project_id
        if not project_id:
            raise VercelError("Call ensure_project before syncing Vercel variables")

        configured = {
            key: os.getenv(key)
            for key in self.settings.vercel_sync_env_keys
            if key not in self._blocked_env_keys
        }
        if values:
            configured.update(
                {
                    key: value
                    for key, value in values.items()
                    if key not in self._blocked_env_keys
                }
            )
        missing = tuple(key for key, value in configured.items() if not value)
        valid = {key: value for key, value in configured.items() if value}
        existing_payload = await self._request(
            "GET", f"/v9/projects/{project_id}/env"
        )
        existing = {
            item.get("key"): item
            for item in existing_payload.get("envs", [])
            if item.get("key")
        }
        synced: list[str] = []
        skipped: list[str] = []
        targets = list(self.settings.vercel_env_targets or ("production",))

        for key, value in valid.items():
            body = {
                "key": key,
                "value": value,
                "type": "encrypted",
                "target": targets,
            }
            current = existing.get(key)
            try:
                if current and current.get("id"):
                    await self._request(
                        "PATCH",
                        f"/v9/projects/{project_id}/env/{current['id']}",
                        json=body,
                    )
                else:
                    await self._request(
                        "POST",
                        f"/v10/projects/{project_id}/env",
                        json=body,
                    )
                synced.append(key)
            except VercelError:
                logger.exception("Could not sync Vercel environment variable %s", key)
                skipped.append(key)

        return EnvironmentSyncResult(
            synced=tuple(synced), missing=missing, skipped=tuple(skipped)
        )

    async def deploy(
        self,
        *,
        repository_name: str,
        repository_id: int,
        branch: str,
        commit_sha: str,
        target: str | None = None,
    ) -> VercelDeploymentResult:
        """Start a deployment from the exact GitHub commit and poll until terminal."""
        if not self.enabled or not self.settings.vercel_project_id:
            raise VercelError(
                "Vercel is not configured. Set VERCEL_TOKEN and provision a project."
            )
        payload = {
            "name": repository_name.rsplit("/", 1)[-1],
            "project": self.settings.vercel_project_id,
            "target": target or self.settings.vercel_target,
            "gitSource": {
                "type": "github",
                "repoId": str(repository_id),
                "ref": branch,
                "sha": commit_sha,
            },
        }
        created = await self._request("POST", "/v13/deployments", json=payload)
        deployment_id = str(created.get("id") or created.get("uid") or "")
        if not deployment_id:
            raise VercelError("Vercel did not return a deployment ID")
        return await self._poll(deployment_id)

    async def _poll(self, deployment_id: str) -> VercelDeploymentResult:
        """Poll deployment status, then retrieve build logs for failed builds."""
        loops = max(
            1,
            self.settings.vercel_deploy_timeout_seconds
            // self.settings.vercel_poll_interval_seconds,
        )
        latest: dict[str, Any] = {}
        for _ in range(loops):
            latest = await self._request("GET", f"/v13/deployments/{deployment_id}")
            state = str(latest.get("readyState") or latest.get("state") or "UNKNOWN")
            if state in {"READY", "ERROR", "CANCELED"}:
                error_summary = ""
                if state != "READY":
                    error_summary = await self.build_error_summary(deployment_id, latest)
                return self._result(deployment_id, latest, state, error_summary)
            await asyncio.sleep(self.settings.vercel_poll_interval_seconds)

        raise VercelError(
            f"Vercel deployment {deployment_id} timed out after "
            f"{self.settings.vercel_deploy_timeout_seconds} seconds"
        )

    async def build_error_summary(
        self, deployment_id: str, deployment: dict[str, Any] | None = None
    ) -> str:
        """Fetch bounded build-log text suitable for a coder debugging prompt."""
        try:
            events = await self._request(
                "GET",
                f"/v3/deployments/{deployment_id}/events",
                params={"limit": "100", "direction": "backward"},
            )
        except VercelError as error:
            return f"Vercel build failed, but logs were unavailable: {error}"
        lines: list[str] = []
        for event in events if isinstance(events, list) else []:
            payload = event.get("payload", {}) if isinstance(event, dict) else {}
            text = ""
            if isinstance(event, dict):
                text = payload.get("text") or event.get("text") or ""
            if text:
                lines.append(str(text))
        if deployment:
            error_code = deployment.get("errorCode")
            error_message = deployment.get("errorMessage")
            if error_code:
                lines.append(f"errorCode: {error_code}")
            if error_message:
                lines.append(f"errorMessage: {error_message}")
        return "\n".join(lines)[-12_000:] or "Vercel reported a failed build without log text."

    async def smoke_test(self, deployment_url: str) -> tuple[bool, str]:
        """Request the deployed app without forwarding the Vercel API token."""
        if not self.settings.vercel_smoke_test_enabled:
            return True, "Smoke test disabled"
        path = self.settings.vercel_smoke_test_path
        url = deployment_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=10.0),
                follow_redirects=True,
            ) as public_client:
                response = await public_client.get(url)
        except httpx.HTTPError as error:
            return False, f"Smoke test could not reach {url}: {error}"
        if 200 <= response.status_code < 400:
            return True, f"HTTP {response.status_code} from {path}"
        body = response.text[:800].replace("\n", " ")
        return False, f"Smoke test returned HTTP {response.status_code} from {path}: {body}"

    def _result(
        self,
        deployment_id: str,
        deployment: dict[str, Any],
        state: str,
        error_summary: str = "",
    ) -> VercelDeploymentResult:
        """Normalize Vercel's deployment response into Telegram-safe links."""
        url = str(deployment.get("url") or "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        dashboard_url = str(
            deployment.get("inspectorUrl")
            or f"https://vercel.com/{self.settings.vercel_project_name or self.settings.vercel_project_id}/{deployment_id}"
        )
        return VercelDeploymentResult(
            deployment_id=deployment_id,
            state=state,
            url=url,
            dashboard_url=dashboard_url,
            error_summary=error_summary,
        )

    async def close(self) -> None:
        """Close the asynchronous HTTP client."""
        await self.client.aclose()
