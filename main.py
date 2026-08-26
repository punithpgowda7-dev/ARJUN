"""Application entry point for the autonomous Telegram developer bot."""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from agents.base import BaseAgent
from agents.coder import CoderAgent
from agents.orchestrator import Orchestrator
from agents.planner import PlannerAgent
from agents.reviewer import ReviewerAgent
from config.settings import get_settings
from services.github_service import GitHubService
from services.memory_service import MemoryService
from services.project_service import ProjectManager
from services.secret_service import SecretStore
from services.telegram_handler import TelegramHandler
from services.vercel_service import VercelService
from utils.audio import VoiceTranscriber


def build_application() -> tuple[Application, BaseAgent, GitHubService]:
    """Construct the Telegram application and all dependency-injected services."""
    settings = get_settings()
    base_agent = BaseAgent(settings)
    planner = PlannerAgent(base_agent)
    coder = CoderAgent(base_agent)
    reviewer = ReviewerAgent(base_agent)
    github = GitHubService(settings)
    memory = MemoryService(settings.state_db_path, settings.github_repo)
    secrets = SecretStore(settings.state_db_path, settings.arjun_secret_key)
    project_manager = ProjectManager(settings, base_agent)
    vercel = VercelService(settings)
    orchestrator = Orchestrator(
        planner,
        coder,
        reviewer,
        github,
        vercel,
        memory,
        secrets,
        project_manager,
    )
    handler = TelegramHandler(settings, orchestrator, VoiceTranscriber(base_agent), memory=memory)

    async def shutdown(_: Application) -> None:
        """Close external clients before the polling event loop exits."""
        await base_agent.close()
        await github.close()
        await vercel.close()
        await memory.close()
        await secrets.close()

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_shutdown(shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", handler.start))
    application.add_handler(CommandHandler("help", handler.start))
    application.add_handler(MessageHandler(filters.VOICE, handler.handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handler.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_text))
    application.add_error_handler(handler.error_handler)
    return application, base_agent, github


def main() -> None:
    """Validate configuration and start long-polling."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Start a dummy HTTP server so Render "Web Service" health checks pass
    import os
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler).serve_forever(),
        daemon=True
    ).start()

    # httpx logs full Telegram URLs at INFO, which would expose the bot token.
    # Keep provider failures in our own sanitized handlers instead.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    application, base_agent, github = build_application()
    try:
        application.run_polling(allowed_updates=["message"])
    finally:
        # run_polling owns the event loop; shutdown is handled by PTB. The clients are
        # explicitly closed for deployments that invoke main under a custom runner.
        del base_agent, github


if __name__ == "__main__":
    main()
