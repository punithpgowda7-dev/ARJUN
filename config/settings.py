"""Validated environment-backed application settings."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """Runtime configuration for the Telegram developer bot."""

    telegram_bot_token: str = Field(min_length=1)
    telegram_allowed_users: frozenset[int] = Field(min_length=1)
    gemini_api_key: str = Field(min_length=1)
    gemini_model: str = Field(default="gemini-2.5-flash", min_length=1)
    github_token: str = Field(min_length=1)
    github_repo: str = Field(min_length=3)
    default_branch: str = Field(default="main", min_length=1)
    agent_working_branch: str = Field(default="agent-builds", min_length=1)
    vercel_token: str = ""
    vercel_project_id: str = ""
    vercel_project_name: str = ""
    vercel_team_id: str = ""
    vercel_target: str = Field(default="production", min_length=1)
    vercel_preview_target: str = Field(default="preview", min_length=1)
    vercel_auto_create_project: bool = True
    auto_promote_production: bool = True
    vercel_smoke_test_enabled: bool = True
    vercel_smoke_test_path: str = Field(default="/", min_length=1)
    vercel_sync_env_keys: tuple[str, ...] = Field(default_factory=tuple)
    vercel_env_targets: tuple[str, ...] = Field(
        default=("production", "preview")
    )
    vercel_deploy_timeout_seconds: int = Field(default=900, ge=60, le=3600)
    vercel_poll_interval_seconds: int = Field(default=8, ge=2, le=60)
    max_debug_attempts: int = Field(default=2, ge=0, le=5)
    state_db_path: str = Field(default="data/arjun.sqlite3", min_length=1)
    arjun_secret_key: str = ""
    question_timeout_seconds: int = Field(default=900, ge=60, le=3600)
    github_auto_create_repositories: bool = True
    github_new_repo_private: bool = True

    @field_validator("github_repo")
    @classmethod
    def validate_repository_name(cls, value: str) -> str:
        """Require the GitHub owner/repository format."""
        parts = value.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("GITHUB_REPO must use the owner/repository format")
        return value.strip()

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load and validate settings from the process environment."""
        load_dotenv()
        raw_users = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        try:
            users = frozenset(
                int(item.strip()) for item in raw_users.split(",") if item.strip()
            )
        except ValueError as exc:
            raise ValueError("TELEGRAM_ALLOWED_USERS must contain integer IDs") from exc

        def csv_values(name: str, default: str = "") -> tuple[str, ...]:
            return tuple(
                item.strip()
                for item in os.getenv(name, default).split(",")
                if item.strip()
            )

        def integer(name: str, default: int) -> int:
            raw = os.getenv(name, str(default)).strip()
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer") from exc

        def boolean(name: str, default: bool) -> bool:
            raw = os.getenv(name, str(default)).strip().lower()
            if raw in {"1", "true", "yes", "on"}:
                return True
            if raw in {"0", "false", "no", "off"}:
                return False
            raise ValueError(f"{name} must be true or false")

        default_branch = os.getenv("DEFAULT_BRANCH", "main")
        auto_promote = boolean("AUTO_PROMOTE_PRODUCTION", True)
        working_branch = os.getenv("AGENT_WORKING_BRANCH", "agent-builds")
        if auto_promote and working_branch == default_branch:
            working_branch = "arjun-builds"

        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_allowed_users=users,
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
            default_branch=default_branch,
            agent_working_branch=working_branch,
            vercel_token=os.getenv("VERCEL_TOKEN", ""),
            vercel_project_id=os.getenv("VERCEL_PROJECT_ID", ""),
            vercel_project_name=os.getenv("VERCEL_PROJECT_NAME", ""),
            vercel_team_id=os.getenv("VERCEL_TEAM_ID", ""),
            vercel_target=os.getenv("VERCEL_TARGET", "production"),
            vercel_preview_target=os.getenv("VERCEL_PREVIEW_TARGET", "preview"),
            vercel_auto_create_project=boolean("VERCEL_AUTO_CREATE_PROJECT", True),
            auto_promote_production=auto_promote,
            vercel_smoke_test_enabled=boolean("VERCEL_SMOKE_TEST_ENABLED", True),
            vercel_smoke_test_path=os.getenv("VERCEL_SMOKE_TEST_PATH", "/"),
            vercel_sync_env_keys=csv_values("VERCEL_SYNC_ENV_KEYS"),
            vercel_env_targets=csv_values(
                "VERCEL_ENV_TARGETS", "production,preview"
            ),
            vercel_deploy_timeout_seconds=integer("VERCEL_DEPLOY_TIMEOUT_SECONDS", 900),
            vercel_poll_interval_seconds=integer("VERCEL_POLL_INTERVAL_SECONDS", 8),
            max_debug_attempts=integer("MAX_DEBUG_ATTEMPTS", 2),
            state_db_path=os.getenv("ARJUN_STATE_DB_PATH", "data/arjun.sqlite3"),
            arjun_secret_key=os.getenv("ARJUN_SECRET_KEY", ""),
            question_timeout_seconds=integer("ARJUN_QUESTION_TIMEOUT_SECONDS", 900),
            github_auto_create_repositories=boolean("GITHUB_AUTO_CREATE_REPOSITORIES", True),
            github_new_repo_private=boolean("GITHUB_NEW_REPO_PRIVATE", True),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable-by-convention settings object."""
    return Settings.from_environment()
