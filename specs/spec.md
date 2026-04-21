# Yotei Specification

## Goal

Provide a container-local scheduler that can register, show status for, and remove Codex tasks, execute them on a schedule, keep per-task session state, and send Telegram notifications.

## Supported Commands

- `yotei schedule`
- `yotei status`
- `yotei pause`
- `yotei resume`
- `yotei edit`
- `yotei remove`
- `yotei config get-default-model`
- `yotei config set-default-model`
- `yotei run`

## Task Fields

- `task_id`
- `schedule_text`
- `prompt`
- `agent`
- `model`
- `session_mode`
- `session_id`
- `chat_id`
- `next_run_at`
- `last_run_at`

## Scheduling Rules

- Default session mode is `fresh`
- `resume` is explicit opt-in
- Same-task overlap is queued, not concurrent
- `pause` disables due-task selection without deleting task history
- `resume` re-enables a task and recalculates `next_run_at` from the current time
- `edit` may change schedule, prompt, agent, model, session mode, and Telegram chat id
- `edit` clears the stored session id when the model changes or session mode is set to `fresh`
- Supported schedule grammar:
  - `in <int>m`
  - `in <int>h`
  - `every <int>m`
  - `every <int>h`
  - `daily HH:MM`
  - `weekdays HH:MM`
  - `<day-list> HH:MM`
  - `cron "<5-field-expression>"`
- One-time `in <duration>` schedules are disabled after the due run is attempted.

## Execution Rules

- Fresh runs use `codex exec --json`
- Resume runs use `codex exec resume --json <session_id>`
- The scheduler persists `thread_id` from `thread.started`
- The scheduler persists the model used for the task
- Unexpected scheduler-loop errors are written to `logs/scheduler.log`
- Continuous `run` mode backs off for `scheduler.error_backoff_seconds` and continues after unexpected loop errors
- `run --once` logs unexpected loop errors and exits non-zero
- User interruption with `Ctrl-C` stops `run` cleanly with exit code `130` and is not retried or logged as a scheduler fault

## Notifications

- Start notifications are sent when enabled
- Success notifications are sent when enabled
- Failure notifications are sent when enabled
- Summary text is truncated to the configured character limit
