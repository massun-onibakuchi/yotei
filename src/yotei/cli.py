"""Where: CLI module. What: expose task management and scheduler-run commands. Why: keep the user-facing workflow scriptable inside a container."""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from time import sleep
import json
import sqlite3
import sys
import traceback
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__
from .config import CONFIG_ENV_VAR, load_config, update_default_model
from .db import (
    TaskRecord,
    advance_task_schedule,
    connect,
    create_task,
    delete_task,
    disable_task,
    dequeue_next,
    due_tasks,
    enqueue_run,
    finish_run,
    has_running_run,
    initialize,
    list_tasks,
    mark_interrupted_runs,
    remove_queue_item,
    get_task,
    set_task_enabled,
    start_run,
    update_task,
    update_run_log_path,
    utc_now,
)
from .notify import format_notification, send_telegram_message
from .runner import run_codex_task
from .schedule import is_one_time, next_run_at, parse_schedule


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="yotei",
        description="Schedule coding-agent tasks inside a Linux container.",
    )
    parser.add_argument(
        "--config",
        help=f"Path to config.toml. Defaults to {CONFIG_ENV_VAR}, then .automation/yotei/config.toml.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    schedule_parser = subparsers.add_parser("schedule", help="Register a scheduled task")
    schedule_parser.add_argument("--task", required=True, help="Unique task identifier")
    schedule_parser.add_argument("--when", required=True, help="Human-friendly schedule string")
    schedule_parser.add_argument("--prompt", required=True, help="Inline prompt to send to Codex")
    schedule_parser.add_argument("--agent", default="codex", choices=["codex"], help="Agent to run")
    schedule_parser.add_argument("--model", help="Override the default model")
    schedule_parser.add_argument("--session-mode", choices=["fresh", "resume"], default="fresh")
    schedule_parser.add_argument("--chat-id", required=True, help="Telegram chat id for notifications")

    status_parser = subparsers.add_parser("status", help="Show scheduled task status")
    status_parser.add_argument("--json", action="store_true", help="Render task output as JSON")

    pause_parser = subparsers.add_parser("pause", help="Pause a scheduled task")
    pause_parser.add_argument("--task", required=True, help="Task identifier to pause")

    resume_parser = subparsers.add_parser("resume", help="Resume a paused scheduled task")
    resume_parser.add_argument("--task", required=True, help="Task identifier to resume")

    edit_parser = subparsers.add_parser("edit", help="Edit editable fields on a scheduled task")
    edit_parser.add_argument("--task", required=True, help="Task identifier to edit")
    edit_parser.add_argument("--when", help="Replacement schedule string")
    edit_parser.add_argument("--prompt", help="Replacement inline prompt")
    edit_parser.add_argument("--agent", choices=["codex"], help="Replacement agent")
    edit_parser.add_argument("--model", help="Replacement model")
    edit_parser.add_argument("--session-mode", choices=["fresh", "resume"], help="Replacement session mode")
    edit_parser.add_argument("--chat-id", help="Replacement Telegram chat id")

    remove_parser = subparsers.add_parser("remove", help="Remove a scheduled task")
    remove_parser.add_argument("--task", required=True, help="Task identifier to remove")

    config_parser = subparsers.add_parser("config", help="Read or update config defaults")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("get-default-model", help="Print the default model")
    set_model = config_subparsers.add_parser("set-default-model", help="Update the default model")
    set_model.add_argument("model", help="Model name from the allowlist")

    run_parser = subparsers.add_parser("run", help="Run the scheduler loop")
    run_parser.add_argument("--once", action="store_true", help="Process one scheduling pass and exit")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    connection = None
    try:
        config = load_config(Path(args.config) if args.config else None)
        connection = connect(config.paths.state_db)
        initialize(connection)

        if args.command == "schedule":
            return _handle_schedule(args, config, connection)
        if args.command == "status":
            return _handle_status(args, connection)
        if args.command == "pause":
            return _handle_pause(args, connection)
        if args.command == "resume":
            return _handle_resume(args, config, connection)
        if args.command == "edit":
            return _handle_edit(args, config, connection)
        if args.command == "remove":
            return _handle_remove(args, connection)
        if args.command == "config":
            return _handle_config(args)
        if args.command == "run":
            return _handle_run(args, config, connection, Path.cwd())
        parser.error(f"Unknown command {args.command!r}")
        return 2
    except (FileNotFoundError, KeyError, OSError, ValueError, sqlite3.Error, ZoneInfoNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


def _handle_schedule(args, config, connection) -> int:
    schedule_spec = parse_schedule(args.when)
    model = args.model or config.codex.default_model
    if model not in config.codex.allowed_models:
        raise ValueError(f"Model {model!r} is not allowed. Allowed models: {', '.join(config.codex.allowed_models)}")
    now = datetime.now(ZoneInfo(config.scheduler.timezone))
    first_run = next_run_at(schedule_spec, now, config.scheduler.timezone)
    task = TaskRecord(
        task_id=args.task,
        schedule_text=args.when,
        schedule_kind=schedule_spec.kind,
        schedule_value=schedule_spec.value,
        prompt=args.prompt,
        agent=args.agent,
        model=model,
        session_mode=args.session_mode,
        session_id=None,
        chat_id=args.chat_id,
        next_run_at=_to_utc_iso(first_run),
        last_run_at=None,
        enabled=True,
    )
    create_task(connection, task)
    print(f"Scheduled task {task.task_id} with next run at {task.next_run_at}.")
    return 0


def _handle_status(args, connection) -> int:
    rows = list_tasks(connection)
    if args.json:
        print(json.dumps([dict(row) for row in rows], indent=2))
        return 0
    if not rows:
        print("No scheduled tasks.")
        return 0
    for row in rows:
        print(
            " | ".join(
                [
                    row["task_id"],
                    f"next={row['next_run_at']}",
                    f"model={row['model']}",
                    f"session_mode={row['session_mode']}",
                    f"session_id={row['session_id'] or '-'}",
                    f"enabled={bool(row['enabled'])}",
                    f"queued={row['queued_runs']}",
                    f"last_status={row['last_status'] or 'never'}",
                ]
            )
        )
    return 0


def _handle_remove(args, connection) -> int:
    deleted = delete_task(connection, args.task)
    if deleted == 0:
        print(f"Task {args.task} was not found.")
        return 1
    print(f"Removed task {args.task}.")
    return 0


def _handle_pause(args, connection) -> int:
    updated = set_task_enabled(connection, args.task, False)
    if updated == 0:
        print(f"Task {args.task} was not found.")
        return 1
    print(f"Paused task {args.task}.")
    return 0


def _handle_resume(args, config, connection) -> int:
    row = get_task(connection, args.task)
    if row is None:
        print(f"Task {args.task} was not found.")
        return 1
    spec = parse_schedule(row["schedule_text"])
    next_run = next_run_at(spec, datetime.now(ZoneInfo(config.scheduler.timezone)), config.scheduler.timezone)
    set_task_enabled(connection, args.task, True, _to_utc_iso(next_run))
    print(f"Resumed task {args.task} with next run at {_to_utc_iso(next_run)}.")
    return 0


def _handle_edit(args, config, connection) -> int:
    row = get_task(connection, args.task)
    if row is None:
        print(f"Task {args.task} was not found.")
        return 1

    schedule_text = args.when or row["schedule_text"]
    schedule_spec = parse_schedule(schedule_text)
    model = args.model or row["model"]
    if model not in config.codex.allowed_models:
        raise ValueError(f"Model {model!r} is not allowed. Allowed models: {', '.join(config.codex.allowed_models)}")

    session_mode = args.session_mode or row["session_mode"]
    session_id = row["session_id"]
    if args.model and args.model != row["model"]:
        session_id = None
    if args.session_mode == "fresh":
        session_id = None

    next_run_at = row["next_run_at"]
    if args.when:
        next_run = next_run_at_for_edit(schedule_spec, config)
        next_run_at = _to_utc_iso(next_run)

    update_task(
        connection,
        args.task,
        schedule_text=schedule_text,
        schedule_kind=schedule_spec.kind,
        schedule_value=schedule_spec.value,
        prompt=args.prompt or row["prompt"],
        agent=args.agent or row["agent"],
        model=model,
        session_mode=session_mode,
        session_id=session_id,
        chat_id=args.chat_id or row["chat_id"],
        next_run_at=next_run_at,
    )
    print(f"Edited task {args.task}.")
    return 0


def _handle_config(args) -> int:
    if args.config_command == "get-default-model":
        config = load_config(Path(args.config) if args.config else None)
        print(config.codex.default_model)
        return 0
    if args.config_command == "set-default-model":
        config = update_default_model(Path(args.config) if args.config else None, args.model)
        print(config.codex.default_model)
        return 0
    raise AssertionError("Unreachable config command.")


def _handle_run(args, config, connection, workspace_root: Path) -> int:
    mark_interrupted_runs(connection)
    while True:
        try:
            _process_due_tasks(config, connection, workspace_root)
        except KeyboardInterrupt:
            return _handle_user_interrupt()
        except Exception as exc:
            _log_scheduler_error(config, exc)
            if args.once:
                return 1
            if _sleep_or_interrupted(config.scheduler.error_backoff_seconds):
                return _handle_user_interrupt()
            continue
        if args.once:
            return 0
        if _sleep_or_interrupted(config.scheduler.poll_seconds):
            return _handle_user_interrupt()


def _process_due_tasks(config, connection, workspace_root: Path) -> None:
    now_iso = utc_now()
    for row in due_tasks(connection, now_iso):
        spec = parse_schedule(row["schedule_text"])
        if has_running_run(connection, row["task_id"]):
            enqueue_run(connection, row["task_id"], row["next_run_at"])
        else:
            _execute_task(config, connection, row, workspace_root)

        if is_one_time(spec):
            disable_task(connection, row["task_id"])
        else:
            next_due = next_run_at(
                spec,
                datetime.fromisoformat(row["next_run_at"].replace("Z", "+00:00")),
                config.scheduler.timezone,
            )
            advance_task_schedule(connection, row["task_id"], _to_utc_iso(next_due))

    queued = dequeue_next(connection)
    if queued and not has_running_run(connection, queued["task_id"]):
        _execute_task(config, connection, queued, workspace_root)
        remove_queue_item(connection, queued["queue_id"])


def _execute_task(config, connection, row, workspace_root: Path) -> None:
    run_id = start_run(connection, row["task_id"], str(config.paths.logs_dir / "pending.log"))
    if config.notifications.send_on_start:
        notification_error = send_telegram_message(
            config,
            row["chat_id"],
            format_notification("start", row["task_id"], row["model"], "Run started.", row["session_id"]),
        )
        if notification_error:
            _log_notification_error(config, run_id, notification_error)
    try:
        result = run_codex_task(
            config,
            task_id=row["task_id"],
            prompt=row["prompt"],
            model=row["model"],
            session_mode=row["session_mode"],
            session_id=row["session_id"],
            workspace_root=workspace_root,
            run_id=run_id,
        )
    except Exception as exc:
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_path = config.paths.logs_dir / f"{run_id}.log"
        try:
            log_path.write_text(error_text, encoding="utf-8")
            update_run_log_path(connection, run_id, str(log_path))
        except OSError as log_exc:
            print(f"failed to write task crash log: {log_exc}", file=sys.stderr)
        finish_run(
            connection,
            run_id,
            status="failed",
            summary=f"Task execution crashed: {exc}",
            exit_code=1,
            session_id=row["session_id"],
            error_text=error_text,
        )
        if config.notifications.send_on_failure:
            notification_error = send_telegram_message(
                config,
                row["chat_id"],
                format_notification("failure", row["task_id"], row["model"], str(exc), row["session_id"]),
            )
            if notification_error:
                _log_notification_error(config, run_id, notification_error)
        return
    update_run_log_path(connection, run_id, str(result.log_path))
    finish_run(
        connection,
        run_id,
        status="success" if result.success else "failed",
        summary=result.summary,
        exit_code=result.exit_code,
        session_id=result.session_id,
        error_text=result.error_text,
    )
    should_notify = (result.success and config.notifications.send_on_success) or (
        not result.success and config.notifications.send_on_failure
    )
    if should_notify:
        notification_error = send_telegram_message(
            config,
            row["chat_id"],
            format_notification(
                "success" if result.success else "failure",
                row["task_id"],
                row["model"],
                result.summary,
                result.session_id,
            ),
        )
        if notification_error:
            _log_notification_error(config, run_id, notification_error)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(ZoneInfo("UTC")).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sleep_or_interrupted(seconds: int) -> bool:
    try:
        sleep(seconds)
    except KeyboardInterrupt:
        return True
    return False


def _handle_user_interrupt() -> int:
    print("scheduler interrupted by user.", file=sys.stderr)
    return 130


def next_run_at_for_edit(schedule_spec, config) -> datetime:
    now = datetime.now(ZoneInfo(config.scheduler.timezone))
    return next_run_at(schedule_spec, now, config.scheduler.timezone)


def _log_scheduler_error(config, exc: Exception) -> None:
    message = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_entry = f"[{utc_now()}] unexpected scheduler loop error\n{message}\n"
    try:
        config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        with (config.paths.logs_dir / "scheduler.log").open("a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
    except OSError as log_exc:
        print(f"failed to write scheduler log: {log_exc}", file=sys.stderr)
    print(
        f"unexpected scheduler loop error; retrying after {config.scheduler.error_backoff_seconds}s: {exc}",
        file=sys.stderr,
    )


def _log_notification_error(config, run_id: str, message: str) -> None:
    log_entry = f"[{utc_now()}] notification failure for run {run_id}: {message}\n"
    try:
        config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        with (config.paths.logs_dir / "scheduler.log").open("a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
    except OSError as log_exc:
        print(f"failed to write notification log: {log_exc}", file=sys.stderr)
