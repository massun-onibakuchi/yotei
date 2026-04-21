# Yotei User Flow

## Register Task

1. User edits `.automation/yotei/config.toml` with Telegram and model defaults.
2. User runs `bin/yotei schedule ...`.
3. The tool validates the schedule, stores the task, and computes the first run time.

## Run Tasks

1. User runs `bin/yotei run`.
2. The scheduler checks for due tasks.
3. If the task is already running, the scheduler queues the next execution.
4. If the task is idle, the scheduler runs Codex and captures `thread_id`.
5. The scheduler disables one-time tasks after their due run is claimed.
6. The scheduler stores run status and sends Telegram notifications.
7. If an unexpected scheduler-loop error occurs, the scheduler logs it, backs off briefly, and continues.
8. If the user presses `Ctrl-C`, the scheduler exits cleanly with code `130` instead of retrying.

## List Tasks

1. User runs `bin/yotei status`.
2. The tool prints current tasks, next run, session mode, and queue depth.

## Unregister Task

1. User runs `bin/yotei remove --task <id>`.
2. The tool removes the task and associated queue records.
3. Run history is removed automatically through the task foreign-key relationship.

## Pause And Resume Task

1. User runs `bin/yotei pause --task <id>`.
2. The tool marks the task disabled without deleting history.
3. User runs `bin/yotei resume --task <id>`.
4. The tool marks the task enabled and recalculates its next run from the current time.

## Edit Task

1. User runs `bin/yotei edit --task <id> --prompt <text>`.
2. The tool updates only provided editable fields.
3. If the model changes or session mode becomes `fresh`, the stored session id is cleared.
