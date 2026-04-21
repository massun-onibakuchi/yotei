"""Where: config module. What: load and save runner configuration. Why: keep runtime tunables centralized."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


CONFIG_ENV_VAR = "YOTEI_CONFIG"
DEFAULT_CONFIG_PATH = Path(".automation/yotei/config.toml")


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
        raise FileNotFoundError(
            f"Config file not found at {config_path}. Copy or edit .automation/yotei/config.toml first."
        )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    paths = data["paths"]
    codex = data["codex"]
    scheduler = data.get("scheduler", {})
    telegram = data["telegram"]
    raw_bot_token = telegram.get("bot_token", "")
    notifications = data.get("notifications", {})

    app_config = AppConfig(
        config_path=config_path,
        paths=PathsConfig(
            state_db=_resolve_path(config_path, paths["state_db"]),
            logs_dir=_resolve_path(config_path, paths["logs_dir"]),
        ),
        codex=CodexConfig(
            binary=codex.get("binary", "codex"),
            default_model=codex["default_model"],
            allowed_models=list(codex.get("allowed_models", [codex["default_model"]])),
        ),
        scheduler=SchedulerConfig(
            timezone=scheduler.get("timezone", "UTC"),
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

    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / DEFAULT_CONFIG_PATH
        if candidate.exists():
            return candidate
    return current / DEFAULT_CONFIG_PATH


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
