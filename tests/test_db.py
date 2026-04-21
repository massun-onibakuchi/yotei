"""Where: database tests. What: verify schema initialization and migrations. Why: protect durable state compatibility."""

from contextlib import closing
from pathlib import Path

import pytest

from yotei.db import SCHEMA_VERSION, connect, initialize, schema_version


def test_initialize_fresh_database_records_schema_version(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "state.sqlite3")) as connection:
        initialize(connection)

        assert schema_version(connection) == SCHEMA_VERSION
        assert _table_exists(connection, "tasks")
        assert _table_exists(connection, "runs")
        assert _table_exists(connection, "run_queue")
        assert _table_exists(connection, "schema_migrations")


def test_initialize_is_idempotent_for_current_schema(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "state.sqlite3")) as connection:
        initialize(connection)
        initialize(connection)

        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        assert [row["version"] for row in rows] == [SCHEMA_VERSION]


def test_initialize_upgrades_legacy_pr_database_without_version_table(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "state.sqlite3")) as connection:
        connection.executescript(
            """
            CREATE TABLE tasks (
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
                next_run_at TEXT NOT NULL,
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE runs (
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

            CREATE TABLE run_queue (
                queue_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                due_at TEXT NOT NULL,
                enqueued_at TEXT NOT NULL
            );
            """
        )
        connection.commit()

        initialize(connection)

        assert schema_version(connection) == SCHEMA_VERSION
        assert _column_exists(connection, "tasks", "enabled")


def test_initialize_rejects_newer_schema_version(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "state.sqlite3")) as connection:
        initialize(connection)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 1, "2026-04-21T00:00:00Z"),
        )
        connection.commit()

        with pytest.raises(RuntimeError, match="newer than supported"):
            initialize(connection)


def test_initialize_rejects_newer_schema_before_baseline_ddl(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "state.sqlite3")) as connection:
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 1, "2026-04-21T00:00:00Z"),
        )
        connection.commit()

        with pytest.raises(RuntimeError, match="newer than supported"):
            initialize(connection)

        assert not _table_exists(connection, "tasks")


def _table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)
