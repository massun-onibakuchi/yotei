"""Where: notification tests. What: verify Telegram notification formatting and non-fatal sends. Why: avoid leaking delivery details into scheduler behavior."""

from pathlib import Path
from urllib import request

from yotei.config import AppConfig, CodexConfig, NotificationsConfig, PathsConfig, SchedulerConfig, TelegramConfig
from yotei.notify import format_notification, send_telegram_message


def test_format_notification_includes_optional_session_and_summary() -> None:
    text = format_notification("success", "task-1", "gpt-5.4", "done", "session-1")

    assert "[task: task-1]" in text
    assert "event: success" in text
    assert "model: gpt-5.4" in text
    assert "session: session-1" in text
    assert "summary: done" in text


def test_format_notification_omits_empty_optional_fields() -> None:
    text = format_notification("start", "task-1", "gpt-5.4", "", None)

    assert "session:" not in text
    assert "summary:" not in text


def test_send_telegram_message_posts_payload(tmp_path: Path, monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_urlopen(req: request.Request, timeout: int):
        calls.append((req, timeout))
        return FakeResponse()

    monkeypatch.setattr(request, "urlopen", fake_urlopen)

    error = send_telegram_message(_config(tmp_path, token="token-123"), "chat-1", "hello")

    assert error is None
    req, timeout = calls[0]
    assert timeout == 10
    assert req.full_url == "https://api.telegram.org/bottoken-123/sendMessage"
    assert req.data == b"chat_id=chat-1&text=hello"


def test_send_telegram_message_ignores_disabled_and_delivery_errors(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(request, "urlopen", lambda *args, **kwargs: calls.append(args))

    assert send_telegram_message(_config(tmp_path, token="replace-me"), "chat-1", "hello") is None
    assert send_telegram_message(_config(tmp_path, token=""), "chat-1", "hello") is None

    assert calls == []

    def fail_urlopen(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(request, "urlopen", fail_urlopen)
    assert send_telegram_message(_config(tmp_path, token="token-123"), "chat-1", "hello") == (
        "Telegram notification failed: OSError."
    )


def _config(tmp_path: Path, *, token: str) -> AppConfig:
    return AppConfig(
        config_path=tmp_path / "config.toml",
        paths=PathsConfig(state_db=tmp_path / "state.sqlite3", logs_dir=tmp_path / "logs"),
        codex=CodexConfig(binary="codex", default_model="gpt-5.4", allowed_models=["gpt-5.4"]),
        scheduler=SchedulerConfig(timezone="UTC", poll_seconds=1, error_backoff_seconds=1),
        telegram=TelegramConfig(bot_token=token, bot_token_source=token),
        notifications=NotificationsConfig(
            send_on_start=True,
            send_on_success=True,
            send_on_failure=True,
            summary_chars=1200,
        ),
    )
