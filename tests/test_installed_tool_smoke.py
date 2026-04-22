"""Where: installed-tool smoke tests. What: verify console-script config flow outside the repo. Why: catch portability regressions early."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import os
import shutil
import sqlite3
import subprocess
import tempfile

import pytest


def test_console_script_portable_smoke_flow() -> None:
    yotei_bin = shutil.which("yotei")
    assert yotei_bin is not None, "yotei console script must be on PATH during the smoke test"

    with tempfile.TemporaryDirectory(prefix="yotei-smoke-") as smoke_root_text:
        smoke_root = Path(smoke_root_text)
        outside_repo = smoke_root / "outside-repo"
        outside_repo.mkdir()
        _assert_no_parent_automation(outside_repo)
        explicit_workspace = smoke_root / "explicit-workspace"
        explicit_workspace.mkdir()
        xdg_config_home = smoke_root / "xdg-config"
        xdg_state_home = smoke_root / "xdg-state"
        fake_cwd_log = smoke_root / "fake-cwd.log"
        fake_codex = _write_fake_codex(smoke_root, fake_cwd_log)
        env = _smoke_env(xdg_config_home, xdg_state_home, fake_cwd_log)

        init_result = subprocess.run(
            [yotei_bin, "config", "init"],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        assert init_result.returncode == 0, init_result.stderr
        config_path = xdg_config_home / "yotei" / "config.toml"
        assert config_path.exists()
        assert str(config_path) in init_result.stdout
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            .replace('default_model = "gpt-5.4"', 'default_model = "gpt-5.4-mini"')
            .replace('binary = "codex"', f'binary = "{fake_codex}"'),
            encoding="utf-8",
        )

        get_result = subprocess.run(
            [yotei_bin, "config", "get-default-model"],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        assert get_result.returncode == 0, get_result.stderr
        assert get_result.stdout.strip() == "gpt-5.4-mini"
        assert xdg_state_home.joinpath("yotei").exists()

        default_schedule = subprocess.run(
            [
                yotei_bin,
                "schedule",
                "--task",
                "default-workspace-task",
                "--when",
                "once in 5m",
                "--prompt",
                "run from default workspace",
                "--chat-id",
                "0",
            ],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert default_schedule.returncode == 0, default_schedule.stderr

        explicit_schedule = subprocess.run(
            [
                yotei_bin,
                "schedule",
                "--task",
                "explicit-workspace-task",
                "--when",
                "once in 5m",
                "--prompt",
                "run from explicit workspace",
                "--chat-id",
                "0",
                "--workspace",
                str(explicit_workspace),
            ],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert explicit_schedule.returncode == 0, explicit_schedule.stderr

        status_result = subprocess.run(
            [yotei_bin, "status"],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert status_result.returncode == 0, status_result.stderr
        assert f"workspace={outside_repo}" in status_result.stdout
        assert f"workspace={explicit_workspace}" in status_result.stdout

        state_db = xdg_state_home / "yotei" / "state.sqlite3"
        _force_tasks_due(state_db, "default-workspace-task", "explicit-workspace-task")

        run_result = subprocess.run(
            [yotei_bin, "run", "--once"],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert run_result.returncode == 0, run_result.stderr

        cwd_lines = fake_cwd_log.read_text(encoding="utf-8").splitlines()
        assert cwd_lines == [str(outside_repo), str(explicit_workspace)]

        final_status = subprocess.run(
            [yotei_bin, "status"],
            cwd=outside_repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert final_status.returncode == 0, final_status.stderr
        assert "default-workspace-task" in final_status.stdout
        assert "explicit-workspace-task" in final_status.stdout
        assert "last_status=success" in final_status.stdout


def _smoke_env(xdg_config_home: Path, xdg_state_home: Path, fake_cwd_log: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("YOTEI_CONFIG", None)
    env.pop("SCHEDULED_AGENT_RUNNER_CONFIG", None)
    env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    env["XDG_STATE_HOME"] = str(xdg_state_home)
    env["YOTEI_FAKE_CWD_LOG"] = str(fake_cwd_log)
    return env


def _write_fake_codex(smoke_root: Path, fake_cwd_log: Path) -> Path:
    fake_codex = smoke_root / "fake-codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf '%s\\n' \"$PWD\" >> \"$YOTEI_FAKE_CWD_LOG\"",
                "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"fake-session\"}'",
                "printf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"fake run ok\"}}'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    assert fake_cwd_log.parent.exists()
    return fake_codex


def _force_tasks_due(state_db: Path, *task_ids: str) -> None:
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    connection = sqlite3.connect(state_db)
    try:
        connection.executemany(
            "UPDATE tasks SET next_run_at = ? WHERE task_id = ?",
            [(now_iso, task_id) for task_id in task_ids],
        )
        connection.commit()
    finally:
        connection.close()


def _assert_no_parent_automation(path: Path) -> None:
    for directory in [path, *path.parents]:
        if directory.joinpath(".automation").exists():
            pytest.fail(f"smoke cwd has parent .automation directory: {directory}")
