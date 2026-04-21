"""Where: config tests. What: verify discovery and path defaults. Why: keep machine-local behavior portable."""

from pathlib import Path

import pytest

from yotei.config import discover_config_path, load_config, user_config_path, user_state_dir


MINIMAL_CONFIG = """
[codex]
default_model = "gpt-5.4"
allowed_models = ["gpt-5.4"]

[telegram]
bot_token = "replace-me"
""".strip()


def test_yotei_config_env_wins_over_legacy_env(tmp_path: Path, monkeypatch) -> None:
    preferred = tmp_path / "preferred.toml"
    legacy = tmp_path / "legacy.toml"
    monkeypatch.setenv("YOTEI_CONFIG", str(preferred))
    monkeypatch.setenv("SCHEDULED_AGENT_RUNNER_CONFIG", str(legacy))

    assert discover_config_path() == preferred


def test_legacy_config_env_is_supported(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / "legacy.toml"
    monkeypatch.delenv("YOTEI_CONFIG", raising=False)
    monkeypatch.setenv("SCHEDULED_AGENT_RUNNER_CONFIG", str(legacy))

    assert discover_config_path() == legacy


def test_repo_config_wins_over_legacy_repo_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YOTEI_CONFIG", raising=False)
    monkeypatch.delenv("SCHEDULED_AGENT_RUNNER_CONFIG", raising=False)
    current = tmp_path / "workspace" / "nested"
    current.mkdir(parents=True)
    preferred = tmp_path / ".automation" / "yotei" / "config.toml"
    legacy = tmp_path / ".automation" / "scheduled-agent-runner" / "config.toml"
    preferred.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    preferred.write_text(MINIMAL_CONFIG, encoding="utf-8")
    legacy.write_text(MINIMAL_CONFIG, encoding="utf-8")

    assert discover_config_path(current) == preferred


def test_user_config_path_is_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YOTEI_CONFIG", raising=False)
    monkeypatch.delenv("SCHEDULED_AGENT_RUNNER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))

    assert discover_config_path(tmp_path / "empty") == tmp_path / "xdg-config" / "yotei" / "config.toml"


def test_user_paths_honor_xdg_and_home_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    assert user_config_path() == tmp_path / "xdg-config" / "yotei" / "config.toml"
    assert user_state_dir() == tmp_path / "xdg-state" / "yotei"

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert user_config_path() == tmp_path / "home" / ".config" / "yotei" / "config.toml"
    assert user_state_dir() == tmp_path / "home" / ".local" / "state" / "yotei"


@pytest.mark.parametrize("xdg_value", ["", "relative/path"])
def test_empty_or_relative_xdg_values_fall_back_to_home(tmp_path: Path, monkeypatch, xdg_value: str) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg_value)
    monkeypatch.setenv("XDG_STATE_HOME", xdg_value)

    assert user_config_path() == tmp_path / "home" / ".config" / "yotei" / "config.toml"
    assert user_state_dir() == tmp_path / "home" / ".local" / "state" / "yotei"


def test_missing_paths_default_to_xdg_state(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(MINIMAL_CONFIG, encoding="utf-8")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))

    config = load_config(config_path)

    assert config.paths.state_db == tmp_path / "state-home" / "yotei" / "state.sqlite3"
    assert config.paths.logs_dir == tmp_path / "state-home" / "yotei" / "logs"
    assert config.paths.state_db.parent.exists()
    assert config.paths.logs_dir.exists()


def test_relative_paths_still_resolve_from_config_parent(tmp_path: Path) -> None:
    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[paths]",
                'state_db = "relative/state.sqlite3"',
                'logs_dir = "relative/logs"',
                "",
                MINIMAL_CONFIG,
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.paths.state_db == config_dir / "relative" / "state.sqlite3"
    assert config.paths.logs_dir == config_dir / "relative" / "logs"


def test_invalid_timezone_has_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        MINIMAL_CONFIG + '\n\n[scheduler]\ntimezone = "Not/AZone"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid timezone"):
        load_config(config_path)
