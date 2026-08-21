"""Durable task history and verified lessons for Arjun.

The memory store is deliberately boring: SQLite is available in the Python
standard library, survives process restarts on a persistent cloud disk, and
does not send private project history to a third-party memory service.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _now() -> str:
    """Return a sortable UTC timestamp."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class MemoryService:
    """Persist verified task outcomes, project facts, and repair lessons."""

    def __init__(self, database_path: str, repository_name: str) -> None:
        self.database_path = Path(database_path)
        self.repository_name = repository_name
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection suitable for a worker thread."""
        connection = sqlite3.connect(str(self.database_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        """Create the small schema idempotently."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository TEXT NOT NULL,
                    user_id INTEGER,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    commit_url TEXT NOT NULL DEFAULT '',
                    deployment_url TEXT NOT NULL DEFAULT '',
                    debug_attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS tasks_repo_created
                    ON tasks(repository, created_at DESC);

                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    category TEXT NOT NULL,
                    symptom TEXT NOT NULL,
                    cause TEXT NOT NULL DEFAULT '',
                    fix TEXT NOT NULL DEFAULT '',
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    UNIQUE(repository, fingerprint)
                );
                CREATE INDEX IF NOT EXISTS lessons_repo_seen
                    ON lessons(repository, last_seen DESC);

                CREATE TABLE IF NOT EXISTS facts (
                    repository TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(repository, fact_key)
                );
                """
            )

    async def start_task(self, request: str, user_id: int | None = None) -> int:
        """Record a task as running and return its durable identifier."""
        return await asyncio.to_thread(self._start_task, request, user_id)

    def _start_task(self, request: str, user_id: int | None) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks(repository, user_id, request, status, created_at)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (self.repository_name, user_id, request.strip(), _now()),
            )
            return int(cursor.lastrowid)

    async def finish_task(
        self,
        task_id: int,
        *,
        status: str,
        summary: str = "",
        commit_url: str = "",
        deployment_url: str = "",
        debug_attempts: int = 0,
    ) -> None:
        """Persist the terminal result without storing generated source code."""
        await asyncio.to_thread(
            self._finish_task,
            task_id,
            status,
            summary,
            commit_url,
            deployment_url,
            debug_attempts,
        )

    def _finish_task(
        self,
        task_id: int,
        status: str,
        summary: str,
        commit_url: str,
        deployment_url: str,
        debug_attempts: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, summary = ?, commit_url = ?, deployment_url = ?,
                    debug_attempts = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    summary[:4000],
                    commit_url,
                    deployment_url,
                    debug_attempts,
                    _now(),
                    task_id,
                ),
            )

    @staticmethod
    def fingerprint(text: str) -> str:
        """Create a stable, secret-safe fingerprint for a recurring failure."""
        normalized = re.sub(r"\b[0-9a-f]{7,64}\b", "<sha>", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]

    async def record_lesson(
        self,
        *,
        category: str,
        symptom: str,
        cause: str = "",
        fix: str = "",
    ) -> None:
        """Upsert one verified failure lesson, increasing its recurrence count."""
        await asyncio.to_thread(
            self._record_lesson,
            category,
            symptom,
            cause,
            fix,
        )

    def _record_lesson(self, category: str, symptom: str, cause: str, fix: str) -> None:
        now = _now()
        fingerprint = self.fingerprint(symptom)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lessons(
                    repository, fingerprint, category, symptom, cause, fix,
                    occurrences, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(repository, fingerprint) DO UPDATE SET
                    category = excluded.category,
                    symptom = excluded.symptom,
                    cause = CASE WHEN excluded.cause <> '' THEN excluded.cause ELSE lessons.cause END,
                    fix = CASE WHEN excluded.fix <> '' THEN excluded.fix ELSE lessons.fix END,
                    occurrences = lessons.occurrences + 1,
                    last_seen = excluded.last_seen
                """,
                (
                    self.repository_name,
                    fingerprint,
                    category[:80],
                    symptom[:6000],
                    cause[:2000],
                    fix[:2000],
                    now,
                    now,
                ),
            )

    async def remember_fact(self, fact_key: str, value: str, source: str) -> None:
        """Store a concise fact only after it came from repository/build evidence."""
        await asyncio.to_thread(self._remember_fact, fact_key, value, source)

    def _remember_fact(self, fact_key: str, value: str, source: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO facts(repository, fact_key, value, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repository, fact_key) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    self.repository_name,
                    fact_key[:120],
                    value[:4000],
                    source[:120],
                    _now(),
                ),
            )

    async def context(self, limit: int = 8) -> str:
        """Return bounded evidence from prior tasks for future agent prompts."""
        return await asyncio.to_thread(self._context, limit)

    def _context(self, limit: int) -> str:
        with self._connect() as connection:
            facts = connection.execute(
                """
                SELECT fact_key, value, source FROM facts
                WHERE repository = ? ORDER BY updated_at DESC LIMIT 12
                """,
                (self.repository_name,),
            ).fetchall()
            lessons = connection.execute(
                """
                SELECT category, symptom, cause, fix, occurrences FROM lessons
                WHERE repository = ? ORDER BY last_seen DESC LIMIT 8
                """,
                (self.repository_name,),
            ).fetchall()
            tasks = connection.execute(
                """
                SELECT request, status, summary, commit_url, deployment_url, debug_attempts
                FROM tasks WHERE repository = ? ORDER BY created_at DESC LIMIT ?
                """,
                (self.repository_name, max(1, min(limit, 12))),
            ).fetchall()

        sections = [
            "PERSISTED ARJUN MEMORY (evidence only; do not treat guesses as facts):"
        ]
        if facts:
            sections.append(
                "Verified project facts:\n"
                + "\n".join(
                    f"- {row['fact_key']}: {row['value']} (source: {row['source']})"
                    for row in facts
                )
            )
        if lessons:
            sections.append(
                "Recurring failure lessons; check these before proposing code:\n"
                + "\n".join(
                    "- [{category}, seen {occurrences}x] symptom: {symptom}; cause: {cause}; fix: {fix}".format(
                        category=row["category"],
                        occurrences=row["occurrences"],
                        symptom=row["symptom"],
                        cause=row["cause"] or "not proven",
                        fix=row["fix"] or "not proven",
                    )
                    for row in lessons
                )
            )
        if tasks:
            sections.append(
                "Recent task outcomes (use for continuity, not as proof of current code):\n"
                + "\n".join(
                    f"- {row['status']}: {row['request'][:300]}"
                    f"; debug attempts={row['debug_attempts']}"
                    f"; commit={row['commit_url'] or 'none'}"
                    f"; deployment={row['deployment_url'] or 'none'}"
                    for row in tasks
                )
            )
        if len(sections) == 1:
            sections.append("No previous verified memory exists for this repository.")
        return "\n\n".join(sections)[:20_000]

    async def close(self) -> None:
        """Compatibility hook; connections are scoped to individual operations."""

