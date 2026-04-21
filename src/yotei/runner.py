"""Where: runner module. What: execute Codex runs and parse JSONL events. Why: keep external CLI integration isolated and testable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess

from .config import AppConfig


@dataclass(slots=True)
class RunResult:
    success: bool
    exit_code: int
    session_id: str | None
    summary: str
    error_text: str | None
    log_path: Path


def build_command(
    *,
    codex_binary: str,
    prompt: str,
    model: str,
    session_mode: str,
    session_id: str | None,
) -> list[str]:
    if session_mode == "resume" and session_id:
        return [codex_binary, "exec", "resume", "--json", session_id, "-m", model, prompt]
    return [codex_binary, "exec", "--json", "--skip-git-repo-check", "-m", model, prompt]


def run_codex_task(
    config: AppConfig,
    *,
    task_id: str,
    prompt: str,
    model: str,
    session_mode: str,
    session_id: str | None,
    workspace_root: Path,
    run_id: str,
) -> RunResult:
    log_path = config.paths.logs_dir / f"{run_id}.log"
    command = build_command(
        codex_binary=config.codex.binary,
        prompt=prompt,
        model=model,
        session_mode=session_mode,
        session_id=session_id,
    )
    last_message = ""
    captured_session_id = session_id
    error_lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as log_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        except OSError as exc:
            message = f"Failed to start Codex command: {exc}"
            log_file.write(message + "\n")
            return RunResult(
                success=False,
                exit_code=127,
                session_id=captured_session_id,
                summary=_truncate_summary(message, config.notifications.summary_chars),
                error_text=message,
                log_path=log_path,
            )
        assert process.stdout is not None
        for raw_line in process.stdout:
            log_file.write(raw_line)
            log_file.flush()
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                error_lines.append(line)
                continue
            if payload.get("type") == "thread.started":
                captured_session_id = payload.get("thread_id", captured_session_id)
            if payload.get("type") != "item.completed":
                continue
            item = payload.get("item", {})
            item_type = item.get("type")
            if item_type == "agent_message":
                last_message = item.get("text", last_message)
            elif item_type == "error":
                error_lines.append(item.get("message", "Unknown Codex error."))
        exit_code = process.wait()
    summary = _truncate_summary(last_message or "\n".join(error_lines), config.notifications.summary_chars)
    return RunResult(
        success=exit_code == 0,
        exit_code=exit_code,
        session_id=captured_session_id,
        summary=summary,
        error_text=None if exit_code == 0 else "\n".join(error_lines) or "Codex command failed.",
        log_path=log_path,
    )


def _truncate_summary(summary: str, limit: int) -> str:
    collapsed = " ".join(summary.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 3)] + "..."
