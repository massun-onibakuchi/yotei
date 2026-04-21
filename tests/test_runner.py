"""Where: runner tests. What: verify Codex command construction and output parsing. Why: keep session-mode behavior explicit and stable."""

from pathlib import Path

from yotei.config import AppConfig, CodexConfig, NotificationsConfig, PathsConfig, SchedulerConfig, TelegramConfig
from yotei.runner import build_command
from yotei.runner import run_codex_task


def test_build_command_for_fresh_session() -> None:
    command = build_command(
        codex_binary="codex",
        prompt="Hello",
        model="gpt-5.4",
        session_mode="fresh",
        session_id=None,
    )
    assert command == ["codex", "exec", "--json", "--skip-git-repo-check", "-m", "gpt-5.4", "Hello"]


def test_build_command_for_resume_session() -> None:
    command = build_command(
        codex_binary="codex",
        prompt="Hello again",
        model="gpt-5.4-mini",
        session_mode="resume",
        session_id="session-123",
    )
    assert command == ["codex", "exec", "resume", "--json", "session-123", "-m", "gpt-5.4-mini", "Hello again"]


def test_run_codex_task_parses_jsonl_success(tmp_path: Path) -> None:
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "print('{\"type\":\"thread.started\",\"thread_id\":\"thread-1\"}')",
                "print('not json')",
                "print('{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"finished ok\"}}')",
            ]
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    config = _config(tmp_path, codex_binary=str(fake_codex), summary_chars=20)

    result = run_codex_task(
        config,
        task_id="task-1",
        prompt="hello",
        model="gpt-5.4",
        session_mode="fresh",
        session_id=None,
        workspace_root=tmp_path,
        run_id="run-1",
    )

    assert result.success is True
    assert result.exit_code == 0
    assert result.session_id == "thread-1"
    assert result.summary == "finished ok"
    assert result.error_text is None
    assert "not json" in result.log_path.read_text(encoding="utf-8")


def test_run_codex_task_reports_process_failure(tmp_path: Path) -> None:
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "print('{\"type\":\"item.completed\",\"item\":{\"type\":\"error\",\"message\":\"bad thing\"}}')",
                "sys.exit(42)",
            ]
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    result = run_codex_task(
        _config(tmp_path, codex_binary=str(fake_codex)),
        task_id="task-1",
        prompt="hello",
        model="gpt-5.4",
        session_mode="fresh",
        session_id=None,
        workspace_root=tmp_path,
        run_id="run-2",
    )

    assert result.success is False
    assert result.exit_code == 42
    assert result.error_text == "bad thing"


def test_run_codex_task_reports_missing_binary(tmp_path: Path) -> None:
    result = run_codex_task(
        _config(tmp_path, codex_binary=str(tmp_path / "missing-codex")),
        task_id="task-1",
        prompt="hello",
        model="gpt-5.4",
        session_mode="fresh",
        session_id="existing-session",
        workspace_root=tmp_path,
        run_id="run-3",
    )

    assert result.success is False
    assert result.exit_code == 127
    assert result.session_id == "existing-session"
    assert "Failed to start Codex command" in result.error_text


def _config(tmp_path: Path, *, codex_binary: str, summary_chars: int = 1200) -> AppConfig:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return AppConfig(
        config_path=tmp_path / "config.toml",
        paths=PathsConfig(state_db=tmp_path / "state.sqlite3", logs_dir=logs_dir),
        codex=CodexConfig(binary=codex_binary, default_model="gpt-5.4", allowed_models=["gpt-5.4"]),
        scheduler=SchedulerConfig(timezone="UTC", poll_seconds=1, error_backoff_seconds=1),
        telegram=TelegramConfig(bot_token="replace-me", bot_token_source="replace-me"),
        notifications=NotificationsConfig(
            send_on_start=True,
            send_on_success=True,
            send_on_failure=True,
            summary_chars=summary_chars,
        ),
    )
