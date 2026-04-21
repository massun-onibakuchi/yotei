"""Where: installed-tool smoke tests. What: verify console-script config flow outside the repo. Why: catch portability regressions early."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import pytest


def test_console_script_config_init_and_user_config_discovery() -> None:
    yotei_bin = shutil.which("yotei")
    assert yotei_bin is not None, "yotei console script must be on PATH during the smoke test"

    with tempfile.TemporaryDirectory(prefix="yotei-smoke-") as smoke_root_text:
        smoke_root = Path(smoke_root_text)
        outside_repo = smoke_root / "outside-repo"
        outside_repo.mkdir()
        _assert_no_parent_automation(outside_repo)
        xdg_config_home = smoke_root / "xdg-config"
        xdg_state_home = smoke_root / "xdg-state"
        env = _smoke_env(xdg_config_home, xdg_state_home)

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
            config_path.read_text(encoding="utf-8").replace(
                'default_model = "gpt-5.4"',
                'default_model = "gpt-5.4-mini"',
            ),
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


def _smoke_env(xdg_config_home: Path, xdg_state_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("YOTEI_CONFIG", None)
    env.pop("SCHEDULED_AGENT_RUNNER_CONFIG", None)
    env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    env["XDG_STATE_HOME"] = str(xdg_state_home)
    return env


def _assert_no_parent_automation(path: Path) -> None:
    for directory in [path, *path.parents]:
        if directory.joinpath(".automation").exists():
            pytest.fail(f"smoke cwd has parent .automation directory: {directory}")
