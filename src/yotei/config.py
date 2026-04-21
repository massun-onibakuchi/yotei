"""Where: config module. What: load and save runner configuration. Why: keep runtime tunables centralized."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CONFIG_ENV_VAR = "YOTEI_CONFIG"
LEGACY_CONFIG_ENV_VAR = "SCHEDULED_AGENT_RUNNER_CONFIG"
REPO_CONFIG_PATH = Path(".automation/yotei/config.toml")
LEGACY_REPO_CONFIG_PATH = Path(".automation/scheduled-agent-runner/config.toml")


@dataclass(slots=True)
class PathsConfig:
    state_db: Path
    logs_dir: Path


@dataclass(slots=True)
class CodexConfig:
    binary: str
    default_model: str
    allowed_models: list[str]


@dataclass(slots=True)
class SchedulerConfig:
    timezone: str
    poll_seconds: int
    error_backoff_seconds: int


@dataclass(slots=True)
class TelegramConfig:
    bot_token: str
    bot_token_source: str


@dataclass(slots=True)
class NotificationsConfig:
    send_on_start: bool
    send_on_success: bool
    send_on_failure: bool
    summary_chars: int


@dataclass(slots=True)
class AppConfig:
    config_path: Path
    paths: PathsConfig
    codex: CodexConfig
    scheduler: SchedulerConfig
    telegram: TelegramConfig
    notifications: NotificationsConfig


def _resolve_path(config_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def load_config(config_path: Path | None = None) -> AppConfig:
    config_path = (config_path or discover_config_path()).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}. Create a config file or pass --config.")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    codex = data["codex"]
    scheduler = data.get("scheduler", {})
    telegram = data["telegram"]
    raw_bot_token = telegram.get("bot_token", "")
    notifications = data.get("notifications", {})
    timezone = scheduler.get("timezone", "UTC")
    _validate_timezone(timezone)
    default_state_dir = user_state_dir()

    app_config = AppConfig(
        config_path=config_path,
        paths=PathsConfig(
            state_db=_resolve_config_path(config_path, paths.get("state_db"), default_state_dir / "state.sqlite3"),
            logs_dir=_resolve_config_path(config_path, paths.get("logs_dir"), default_state_dir / "logs"),
        ),
        codex=CodexConfig(
            binary=codex.get("binary", "codex"),
            default_model=codex["default_model"],
            allowed_models=list(codex.get("allowed_models", [codex["default_model"]])),
        ),
        scheduler=SchedulerConfig(
            timezone=timezone,
            poll_seconds=int(scheduler.get("poll_seconds", 30)),
            error_backoff_seconds=int(scheduler.get("error_backoff_seconds", 5)),
        ),
        telegram=TelegramConfig(bot_token=_resolve_secret(raw_bot_token), bot_token_source=raw_bot_token),
        notifications=NotificationsConfig(
            send_on_start=bool(notifications.get("send_on_start", True)),
            send_on_success=bool(notifications.get("send_on_success", True)),
            send_on_failure=bool(notifications.get("send_on_failure", True)),
            summary_chars=int(notifications.get("summary_chars", 1200)),
        ),
    )
    app_config.paths.state_db.parent.mkdir(parents=True, exist_ok=True)
    app_config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
    return app_config


def discover_config_path(start_dir: Path | None = None) -> Path:
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)
    legacy_env_path = os.environ.get(LEGACY_CONFIG_ENV_VAR)
    if legacy_env_path:
        return Path(legacy_env_path)

    current = (start_dir or Path.cwd()).resolve()
    search_dirs = [current, *current.parents]
    for directory in search_dirs:
        candidate = directory / REPO_CONFIG_PATH
        if candidate.exists():
            return candidate
    for directory in search_dirs:
        candidate = directory / LEGACY_REPO_CONFIG_PATH
        if candidate.exists():
            return candidate
    return user_config_path()


def user_config_path() -> Path:
    base = _xdg_base_path("XDG_CONFIG_HOME", Path.home() / ".config")
    return base / "yotei" / "config.toml"


def user_state_dir() -> Path:
    base = _xdg_base_path("XDG_STATE_HOME", Path.home() / ".local" / "state")
    return base / "yotei"


def _xdg_base_path(env_var: str, default: Path) -> Path:
    raw_value = os.environ.get(env_var)
    if not raw_value:
        return default
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        return default
    return candidate


def _resolve_config_path(config_path: Path, raw_path: str | None, default_path: Path) -> Path:
    if raw_path is None:
        return default_path
    return _resolve_path(config_path, raw_path)


def _validate_timezone(timezone: str) -> None:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone {timezone!r}. Use an IANA timezone such as 'UTC'.") from exc


def save_config(config: AppConfig) -> None:
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(render_config(config), encoding="utf-8")


def render_config(config: AppConfig) -> str:
    allowed_models = ", ".join(f'"{item}"' for item in config.codex.allowed_models)
    return "\n".join(
        [
            "[paths]",
            f'state_db = "{_render_relative(config.config_path, config.paths.state_db)}"',
            f'logs_dir = "{_render_relative(config.config_path, config.paths.logs_dir)}"',
            "",
            "[codex]",
            f'binary = "{config.codex.binary}"',
            f'default_model = "{config.codex.default_model}"',
            f"allowed_models = [{allowed_models}]",
            "",
            "[scheduler]",
            f'timezone = "{config.scheduler.timezone}"',
            f"poll_seconds = {config.scheduler.poll_seconds}",
            f"error_backoff_seconds = {config.scheduler.error_backoff_seconds}",
            "",
            "[telegram]",
            f'bot_token = "{config.telegram.bot_token_source}"',
            "",
            "[notifications]",
            f"send_on_start = {str(config.notifications.send_on_start).lower()}",
            f"send_on_success = {str(config.notifications.send_on_success).lower()}",
            f"send_on_failure = {str(config.notifications.send_on_failure).lower()}",
            f"summary_chars = {config.notifications.summary_chars}",
            "",
        ]
    )


def update_default_model(config_path: Path | None, model: str) -> AppConfig:
    config = load_config(config_path)
    if config.codex.allowed_models and model not in config.codex.allowed_models:
        raise ValueError(
            f"Model {model!r} is not allowed. Allowed models: {', '.join(config.codex.allowed_models)}"
        )
    config.codex.default_model = model
    save_config(config)
    return config


def _render_relative(config_path: Path, target_path: Path) -> str:
    try:
        return str(target_path.relative_to(config_path.parent))
    except ValueError:
        return str(target_path)


def _resolve_secret(raw_value: str) -> str:
    if raw_value.startswith("env:"):
        return os.environ.get(raw_value.removeprefix("env:"), "")
    return raw_value
