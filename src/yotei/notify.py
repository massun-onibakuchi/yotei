"""Where: notification module. What: send Telegram notifications for task lifecycle events. Why: keep operational visibility separate from execution logic."""

from __future__ import annotations

from urllib import parse, request

from .config import AppConfig


def send_telegram_message(config: AppConfig, chat_id: str, text: str) -> str | None:
    if not config.telegram.bot_token or config.telegram.bot_token == "replace-me":
        return None
    data = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{config.telegram.bot_token}/sendMessage"
    req = request.Request(url, data=data, method="POST")
    try:
        with request.urlopen(req, timeout=10):
            return None
    except Exception as exc:
        return f"Telegram notification failed: {type(exc).__name__}."


def format_notification(event: str, task_id: str, model: str, summary: str, session_id: str | None) -> str:
    lines = [
        f"[task: {task_id}]",
        f"event: {event}",
        f"model: {model}",
    ]
    if session_id:
        lines.append(f"session: {session_id}")
    if summary:
        lines.append(f"summary: {summary}")
    return "\n".join(lines)
