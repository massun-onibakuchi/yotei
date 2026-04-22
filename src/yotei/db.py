"""Where: database module. What: persist tasks, runs, and queued executions. Why: keep scheduler state durable across restarts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid


SCHEMA_VERSION = 2


class SchemaVersionError(RuntimeError):
    """Raised when the state database schema cannot be used by this binary."""


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    schedule_text: str
    schedule_kind: str
    schedule_value: str
    prompt: str
    agent: str
    model: str
    session_mode: str
    session_id: str | None
    chat_id: str
    workspace_root: str | None
    next_run_at: str
    last_run_at: str | None
    enabled: bool = True


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    _reject_newer_schema_if_present(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            schedule_text TEXT NOT NULL,
            schedule_kind TEXT NOT NULL,
            schedule_value TEXT NOT NULL,
            prompt TEXT NOT NULL,
            agent TEXT NOT NULL,
            model TEXT NOT NULL,
            session_mode TEXT NOT NULL,
            session_id TEXT,
            chat_id TEXT NOT NULL,
            workspace_root TEXT,
            next_run_at TEXT NOT NULL,
            last_run_at TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            summary TEXT,
            exit_code INTEGER,
            log_path TEXT NOT NULL,
            session_id TEXT,
            error_text TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS run_queue (
            queue_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            due_at TEXT NOT NULL,
            enqueued_at TEXT NOT NULL
        );
        """
    )
    _add_column_if_missing(connection, "tasks", "enabled", "INTEGER NOT NULL DEFAULT 1")
    _apply_migrations(connection)
    connection.commit()


def create_task(connection: sqlite3.Connection, task: TaskRecord) -> None:
    if not task.workspace_root:
        raise ValueError("New tasks must include workspace_root.")
    now = utc_now()
    connection.execute(
        """
        INSERT INTO tasks (
            task_id, schedule_text, schedule_kind, schedule_value, prompt, agent, model,
            session_mode, session_id, chat_id, workspace_root, next_run_at, last_run_at, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.task_id,
            task.schedule_text,
            task.schedule_kind,
            task.schedule_value,
            task.prompt,
            task.agent,
            task.model,
            task.session_mode,
            task.session_id,
            task.chat_id,
            task.workspace_root,
            task.next_run_at,
            task.last_run_at,
            1 if task.enabled else 0,
            now,
            now,
        ),
    )
    connection.commit()


def list_tasks(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            t.*,
            (
                SELECT COUNT(*)
                FROM run_queue q
                WHERE q.task_id = t.task_id
            ) AS queued_runs,
            (
                SELECT r.status
                FROM runs r
                WHERE r.task_id = t.task_id
                ORDER BY r.started_at DESC
                LIMIT 1
            ) AS last_status
        FROM tasks t
        ORDER BY t.task_id ASC
        """
    ).fetchall()


def get_task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()


def delete_task(connection: sqlite3.Connection, task_id: str) -> int:
    cursor = connection.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    connection.commit()
    return cursor.rowcount


def update_task(
    connection: sqlite3.Connection,
    task_id: str,
    *,
    schedule_text: str,
    schedule_kind: str,
    schedule_value: str,
    prompt: str,
    agent: str,
    model: str,
    session_mode: str,
    session_id: str | None,
    chat_id: str,
    workspace_root: str | None,
    next_run_at: str,
) -> int:
    cursor = connection.execute(
        """
        UPDATE tasks
        SET schedule_text = ?,
            schedule_kind = ?,
            schedule_value = ?,
            prompt = ?,
            agent = ?,
            model = ?,
            session_mode = ?,
            session_id = ?,
            chat_id = ?,
            workspace_root = ?,
            next_run_at = ?,
            updated_at = ?
        WHERE task_id = ?
        """,
        (
            schedule_text,
            schedule_kind,
            schedule_value,
            prompt,
            agent,
            model,
            session_mode,
            session_id,
            chat_id,
            workspace_root,
            next_run_at,
            utc_now(),
            task_id,
        ),
    )
    connection.commit()
    return cursor.rowcount


def set_task_enabled(connection: sqlite3.Connection, task_id: str, enabled: bool, next_run_at: str | None = None) -> int:
    if next_run_at is None:
        cursor = connection.execute(
            "UPDATE tasks SET enabled = ?, updated_at = ? WHERE task_id = ?",
            (1 if enabled else 0, utc_now(), task_id),
        )
    else:
        cursor = connection.execute(
            "UPDATE tasks SET enabled = ?, next_run_at = ?, updated_at = ? WHERE task_id = ?",
            (1 if enabled else 0, next_run_at, utc_now(), task_id),
        )
    connection.commit()
    return cursor.rowcount


def due_tasks(connection: sqlite3.Connection, now_iso: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM tasks WHERE enabled = 1 AND next_run_at <= ? ORDER BY next_run_at ASC",
        (now_iso,),
    ).fetchall()


def has_running_run(connection: sqlite3.Connection, task_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM runs WHERE task_id = ? AND status = 'running' LIMIT 1",
        (task_id,),
    ).fetchone()
    return row is not None


def enqueue_run(connection: sqlite3.Connection, task_id: str, due_at: str) -> None:
    existing = connection.execute(
        "SELECT 1 FROM run_queue WHERE task_id = ? AND due_at = ? LIMIT 1",
        (task_id, due_at),
    ).fetchone()
    if existing is not None:
        return
    connection.execute(
        "INSERT INTO run_queue (queue_id, task_id, due_at, enqueued_at) VALUES (?, ?, ?, ?)",
        (new_id(), task_id, due_at, utc_now()),
    )
    connection.commit()


def dequeue_next(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT q.queue_id, q.task_id, q.due_at, t.*
        FROM run_queue q
        JOIN tasks t ON t.task_id = q.task_id
        ORDER BY q.due_at ASC, q.enqueued_at ASC
        LIMIT 1
        """
    ).fetchone()


def remove_queue_item(connection: sqlite3.Connection, queue_id: str) -> None:
    connection.execute("DELETE FROM run_queue WHERE queue_id = ?", (queue_id,))
    connection.commit()


def advance_task_schedule(connection: sqlite3.Connection, task_id: str, next_run_at: str) -> None:
    connection.execute(
        "UPDATE tasks SET next_run_at = ?, updated_at = ? WHERE task_id = ?",
        (next_run_at, utc_now(), task_id),
    )
    connection.commit()


def disable_task(connection: sqlite3.Connection, task_id: str) -> None:
    connection.execute(
        "UPDATE tasks SET enabled = 0, updated_at = ? WHERE task_id = ?",
        (utc_now(), task_id),
    )
    connection.commit()


def start_run(connection: sqlite3.Connection, task_id: str, log_path: str) -> str:
    run_id = new_id()
    connection.execute(
        """
        INSERT INTO runs (run_id, task_id, status, log_path, started_at)
        VALUES (?, ?, 'running', ?, ?)
        """,
        (run_id, task_id, log_path, utc_now()),
    )
    connection.commit()
    return run_id


def finish_run(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    summary: str,
    exit_code: int,
    session_id: str | None,
    error_text: str | None,
) -> None:
    finished_at = utc_now()
    connection.execute(
        """
        UPDATE runs
        SET status = ?, summary = ?, exit_code = ?, session_id = ?, error_text = ?, finished_at = ?
        WHERE run_id = ?
        """,
        (status, summary, exit_code, session_id, error_text, finished_at, run_id),
    )
    connection.execute(
        """
        UPDATE tasks
        SET session_id = ?, last_run_at = ?, updated_at = ?
        WHERE task_id = (SELECT task_id FROM runs WHERE run_id = ?)
        """,
        (session_id, finished_at, finished_at, run_id),
    )
    connection.commit()


def update_run_log_path(connection: sqlite3.Connection, run_id: str, log_path: str) -> None:
    connection.execute(
        """
        UPDATE runs
        SET log_path = ?
        WHERE run_id = ?
        """,
        (log_path, run_id),
    )
    connection.commit()


def mark_interrupted_runs(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE runs
        SET status = 'failed',
            error_text = COALESCE(error_text, 'Previous scheduler run stopped before the run finished.'),
            finished_at = ?
        WHERE status = 'running'
        """,
        (utc_now(),),
    )
    connection.commit()


def _add_column_if_missing(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    if any(row["name"] == column for row in rows):
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _apply_migrations(connection: sqlite3.Connection) -> None:
    _ensure_schema_version_table(connection)
    current_version = schema_version(connection)
    if current_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"State database schema version {current_version} is newer than supported version {SCHEMA_VERSION}."
        )
    for version in range(current_version + 1, SCHEMA_VERSION + 1):
        _run_migration(connection, version)
        _record_schema_version(connection, version)


def _ensure_schema_version_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _reject_newer_schema_if_present(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "schema_migrations"):
        return
    current_version = schema_version(connection)
    if current_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"State database schema version {current_version} is newer than supported version {SCHEMA_VERSION}."
        )


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def _run_migration(connection: sqlite3.Connection, version: int) -> None:
    if version == 1:
        return
    if version == 2:
        _add_column_if_missing(connection, "tasks", "workspace_root", "TEXT")
        return
    raise SchemaVersionError(f"No migration registered for schema version {version}.")


def _record_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, utc_now()),
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
