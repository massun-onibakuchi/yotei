# 001 Yolobox PR #2 Scheduled Agent Runner Research

## Status

Research complete for the source PR and portability requirements. Implementation has not been copied into this repository yet.

## Research Target

- Source PR: https://github.com/massun-onibakuchi/yolobox/pull/2
- PR title: `Add scheduled agent runner`
- Source branch: `massun-onibakuchi/yolobox:scheduled-agent-runner`
- Head commit: `b95ec68145d9d8b36623e00a7c8ce3f3076e01fe`
- Merge commit reported by GitHub API: `f0bed8398a7ebdbcd9dad4505c0a1666ad9cf0bc`
- Base branch at merge time: `main`
- Merged at: `2026-04-21T15:17:34Z`
- Later reference: PR #3 reverted the merge on the same day.

The PR body says the work ported the final automation state from `yolo-asobi` through commit `5a46e74`, included the automation sequence beginning at `e3c2603`, added config, a CLI wrapper, a Python package, specs/docs/tests, and fixed review issues around Telegram secret preservation, package entry points/config discovery, and queued-run durability.

## Source Material Read

- GitHub PR page and file list.
- GitHub Pulls API response for PR #2.
- Raw PR patch from `https://patch-diff.githubusercontent.com/raw/massun-onibakuchi/yolobox/pull/2.patch`.
- Local clone of `https://github.com/massun-onibakuchi/yolobox.git` at branch `scheduled-agent-runner` into `/tmp/yolobox-pr2`.
- Existing local specs and docs in the current workspace for the scheduled-agent-runner concept.

## Verification Commands

The PR branch was cloned and tested locally:

```sh
git clone --depth 1 --branch scheduled-agent-runner https://github.com/massun-onibakuchi/yolobox.git /tmp/yolobox-pr2
uv run --project /tmp/yolobox-pr2 --extra dev pytest
uv run --project /tmp/yolobox-pr2 python -m compileall src
```

Results:

- `pytest`: 23 tests passed.
- `compileall`: all source files compiled.

## PR Contents

The PR added these scheduler-specific files:

- `.automation/scheduled-agent-runner/config.toml`
- `bin/scheduled-agent-runner`
- `docs/adr/001-internal-scheduler-state-store.md`
- `docs/plans/001-scheduled-agent-runner.md`
- `docs/research/001-codex-session-contract.md`
- `pyproject.toml`
- `specs/spec.md`
- `specs/user-flow.md`
- `src/scheduled_agent_runner/__init__.py`
- `src/scheduled_agent_runner/__main__.py`
- `src/scheduled_agent_runner/cli.py`
- `src/scheduled_agent_runner/config.py`
- `src/scheduled_agent_runner/db.py`
- `src/scheduled_agent_runner/notify.py`
- `src/scheduled_agent_runner/runner.py`
- `src/scheduled_agent_runner/schedule.py`
- `tests/test_cli.py`
- `tests/test_runner.py`
- `tests/test_schedule.py`

The PR also changed Yolobox docs and `.gitignore`, which are coupling points rather than reusable scheduler implementation.

## Product Contract In The PR

The tool is a container-local scheduler for unattended Codex tasks. It supports:

- Registering scheduled tasks.
- Showing task status.
- Pausing and resuming tasks.
- Editing task schedule, prompt, agent, model, session mode, and Telegram chat id.
- Removing tasks and their associated history.
- Running a scheduler loop or a single scheduler pass.
- Reading and setting the default model.
- Sending Telegram notifications for start, success, and failure events.

The public command is `scheduled-agent-runner`.

Supported subcommands in the PR:

- `schedule`
- `status`
- `pause`
- `resume`
- `edit`
- `remove`
- `config get-default-model`
- `config set-default-model`
- `run`

The current dedicated-repo target should add `config init` before copying implementation, because an installed tool needs a way to create its user-level config without requiring a Yolobox checkout.

## Schedule Grammar

The parser accepts a constrained grammar:

- `in <int>m`
- `in <int>h`
- `once in <int>m`
- `once in <int>h`
- `every <int>m`
- `every <int>h`
- `daily HH:MM`
- `weekdays HH:MM`
- `<day-list> HH:MM`, where days are `mon,tue,wed,thu,fri,sat,sun`
- `cron "<5-field-expression>"`

The specs mention only `in`, not `once in`; the implementation accepts both. The dedicated repo should either document `once in` or remove it for spec alignment.

Time handling:

- `next_run_at` converts the reference time into the configured timezone using `zoneinfo.ZoneInfo`.
- Daily and weekly schedules search up to seven days ahead and require the next candidate to be strictly greater than the reference time.
- Cron schedules use a custom minute-by-minute scan for up to 525,600 minutes, approximately one year.
- Cron weekday conversion maps Python Monday-zero weekdays to cron Sunday-zero weekdays.

Cron caveats:

- The parser only validates that cron has five fields.
- The matcher supports `*`, comma lists, ranges, and slash steps.
- It does not support names, `?`, `L`, `W`, `#`, wraparound ranges, or advanced cron semantics.
- It also uses AND semantics across day-of-month and day-of-week because every field must match. Some cron implementations use special OR behavior for those two fields. This must be documented if retained.

## Runtime Data Model

SQLite is the durable state backend. The PR creates three tables:

- `tasks`
- `runs`
- `run_queue`

`tasks` fields:

- `task_id`
- `schedule_text`
- `schedule_kind`
- `schedule_value`
- `prompt`
- `agent`
- `model`
- `session_mode`
- `session_id`
- `chat_id`
- `next_run_at`
- `last_run_at`
- `enabled`
- `created_at`
- `updated_at`

`runs` fields:

- `run_id`
- `task_id`
- `status`
- `summary`
- `exit_code`
- `log_path`
- `session_id`
- `error_text`
- `started_at`
- `finished_at`

`run_queue` fields:

- `queue_id`
- `task_id`
- `due_at`
- `enqueued_at`

Foreign keys are enabled and run history is deleted when the parent task is deleted.

Migration support is minimal:

- Tables are created with `CREATE TABLE IF NOT EXISTS`.
- The `enabled` column is added if missing.
- There is no schema version table, migration registry, or compatibility story for future changes.

The dedicated repo should add a schema version strategy before widening the state contract.

## Scheduler Loop Behavior

The scheduler starts by marking any previous `running` runs as failed. This is a recovery step for scheduler crashes or interrupted processes.

Each scheduler pass:

1. Reads enabled tasks with `next_run_at <= now`.
2. Parses each task schedule text.
3. If a run for that task is already marked `running`, it enqueues a run at the task's current due time.
4. If no run is running, it executes the task immediately.
5. If the schedule is one-time, it disables the task.
6. Otherwise it advances `next_run_at` from the previous due time, not from wall-clock now.
7. After processing due tasks, it dequeues one queued run and executes it if that task is not running.

Important durability behavior:

- Queue inserts are idempotent for the same task and due time.
- Queued executions are only removed after `_execute_task` returns successfully.
- A crash while executing a queued item keeps the queue item.
- A crash while enqueueing a running task leaves the due task unadvanced.

Potential issue:

- The scheduler records a `running` row before spawning Codex. Since execution is synchronous, same-task overlap only exists across separate scheduler processes or stale running rows. On startup, stale running rows are marked failed.
- The implementation is not designed for multiple active scheduler processes against the same SQLite database. Two loops could race on due task selection or queue dequeue. The dedicated repo should document single-runner ownership or introduce locking.

## Codex Execution Contract

Fresh runs use:

```sh
codex exec --json --skip-git-repo-check -m <model> <prompt>
```

Resume runs with an existing session id use:

```sh
codex exec resume --json <session_id> -m <model> <prompt>
```

The runner reads JSONL events from stdout:

- `thread.started` supplies `thread_id`, stored as `session_id`.
- `item.completed` with `agent_message` updates the final summary.
- `item.completed` with `error` appends to error text.
- Non-JSON output is treated as error text.

The runner writes combined stdout/stderr to a per-run log file in the configured logs directory.

Execution caveats:

- Codex is invoked by external binary name from config, defaulting to `codex`.
- The runtime assumes Codex is installed and authenticated on the target machine.
- `--skip-git-repo-check` is used for fresh runs. Resume runs do not include it.
- The working directory for Codex is `Path.cwd()` at `scheduled-agent-runner run` startup.
- The PR does not store a per-task workspace path. That means all tasks execute in the directory where the scheduler loop was launched, not necessarily where the task was registered.

For a portable installed CLI, per-task workspace handling is the most important missing contract. A machine-level tool should probably capture a `workspace_root` at schedule time, expose an override, and refuse to run if the path no longer exists.

## Configuration Contract

The PR config path is repository-local by default:

```text
.automation/scheduled-agent-runner/config.toml
```

Config fields:

- `paths.state_db`
- `paths.logs_dir`
- `codex.binary`
- `codex.default_model`
- `codex.allowed_models`
- `scheduler.timezone`
- `scheduler.poll_seconds`
- `scheduler.error_backoff_seconds`
- `telegram.bot_token`
- `notifications.send_on_start`
- `notifications.send_on_success`
- `notifications.send_on_failure`
- `notifications.summary_chars`

Relative `paths.state_db` and `paths.logs_dir` are resolved relative to the config file's parent directory, not the process working directory. This is a good portable behavior and should be retained.

Secret handling:

- `telegram.bot_token = "env:TG_BOT_TOKEN"` resolves at runtime from the environment.
- `render_config` preserves the original source string rather than writing the resolved secret.
- Tests cover that `config set-default-model` does not leak the resolved secret into config.

Discovery order in the PR:

1. `SCHEDULED_AGENT_RUNNER_CONFIG`
2. Search current directory and parents for `.automation/scheduled-agent-runner/config.toml`
3. Fall back to current directory plus `.automation/scheduled-agent-runner/config.toml`

Portability gap:

- There is no user-level config path.
- There is no `config init`.
- A tool installed with `uv tool install -U <tool-name>` and run outside a Yolobox checkout will fail until the user manually creates a repository-shaped `.automation` config path or passes `--config`.

The Yotei dedicated repo should support this discovery order:

1. Explicit `--config`
2. `YOTEI_CONFIG`
3. Legacy `SCHEDULED_AGENT_RUNNER_CONFIG`
4. Repository-local `.automation/yotei/config.toml`
5. Legacy repository-local `.automation/scheduled-agent-runner/config.toml`
6. User config, likely `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`

It should add:

- `yotei config init`
- An overwrite guard
- A `--print-path` or clear success output showing where the config was written
- Tests for XDG config discovery

## CLI Entrypoints

The PR has two entry mechanisms:

- Python package console script in `pyproject.toml`: `scheduled-agent-runner = "scheduled_agent_runner.cli:main"`
- Yolobox-local wrapper: `bin/scheduled-agent-runner`, which runs `uv run --project "$ROOT_DIR" python -m scheduled_agent_runner "$@"`

For a dedicated repo and `uv tool install -U <tool-name>`, the console script is the correct entrypoint. The `bin/` wrapper is Yolobox checkout convenience and should not be required.

Current `pyproject.toml` package metadata:

- Project name: `scheduled-agent-runner`
- Version: `0.1.0`
- Python: `>=3.12`
- Dependencies: none
- Dev extra: `pytest>=8.3.0`
- Build backend: `setuptools.build_meta`

The dedicated repo needs a final install target name. The user's requested usage is:

```sh
uv tool install -U <tool-name>
```

Original recommendation before the rename to Yotei:

- Use package name `scheduled-agent-runner` if the package is meant to be only this scheduler.
- Keep executable name `scheduled-agent-runner`.
- Avoid package name `yolobox`, because the goal is to decouple automation from Yolobox.

Current target name:

- Use package name `yotei`.
- Keep executable name `yotei`.
- Use Python import package `yotei`.
- Use config environment variable `YOTEI_CONFIG`, with `SCHEDULED_AGENT_RUNNER_CONFIG` retained only as a legacy compatibility path.

## Telegram Notifications

Telegram delivery is intentionally minimal:

- Uses `urllib.request` from the standard library.
- POSTs to `https://api.telegram.org/bot<TOKEN>/sendMessage`.
- Sends `chat_id` and `text`.
- Timeout is 10 seconds.
- All exceptions are swallowed.
- Empty token or `replace-me` disables delivery.

Notification text includes:

- task id
- event name
- model
- session id if known
- summary if present

Portability impact:

- No third-party dependency is required.
- Silent notification failures make unattended operation harder to debug.
- The dedicated repo should consider recording notification failures in run metadata or a scheduler log without failing the Codex task.

## Tests In The PR

Coverage areas:

- Scheduling and status output.
- Default model mutation.
- Secret reference preservation.
- Config discovery from parent directories.
- Config discovery from environment variable.
- Pause, resume, and edit.
- Rejection of removed legacy commands: `list`, `unregister`, `daemon`.
- One-time task disable after run.
- Queue durability when queued execution crashes.
- Due task is not advanced when enqueue crashes.
- Queue insert idempotency.
- Scheduler error logging and retry behavior.
- User interrupt handling in process pass, normal sleep, and error backoff.
- Schedule parsing and next-run calculation.
- Codex command construction.

Missing tests for the dedicated repo:

- `uv tool install` style invocation through the console script outside a repo checkout.
- User-level config discovery.
- `config init`.
- Existing-config overwrite behavior.
- XDG config path behavior.
- Workspace path capture and execution from a scheduled workspace.
- Missing Codex binary behavior through the CLI.
- Invalid timezone handling.
- Invalid clock forms such as missing colon, non-numeric values, or malformed day lists.
- Advanced cron edge cases and invalid numeric ranges.
- SQLite schema migrations.
- Multiple scheduler process behavior, or explicit refusal/locking.

## Yolobox Coupling Points

These are the parts that tie the PR to Yolobox or a checkout-local workflow:

- README tells users to edit `.automation/scheduled-agent-runner/config.toml`.
- README commands use `bin/scheduled-agent-runner`.
- Specs/user-flow refer to `.automation` and `bin/`.
- Config discovery falls back to `.automation/...` under the current working directory.
- No user config path exists.
- No config initializer exists.
- The wrapper uses `uv run --project "$ROOT_DIR"`, which assumes a source checkout.
- The scheduler run workspace is wherever the long-running command is launched.
- The package docs are embedded in the broader Yolobox README with devcontainer and worktrunk material.
- `.gitignore` entries are tied to repository-local `.automation` state.

The actual Python package is mostly reusable. The highest-risk portability work is not the scheduler core; it is config lifecycle, install docs, workspace ownership, and repo-neutral packaging.

## Dedicated Repo Requirements

Before copying implementation, the dedicated repo should define:

- Package name and command name.
- User-level config path.
- Whether repo-local `.automation` config remains supported as a compatibility path.
- Data directory defaults for SQLite and logs.
- Workspace semantics for scheduled Codex runs.
- Single-runner or multi-runner ownership.
- Minimal supported Python version.
- Release/install path for `uv tool install -U <tool-name>`.

Recommended first Yotei dedicated-repo contract:

- Repository: `yotei`
- Package: `yotei`
- Command: `yotei`
- Python import package: `yotei`
- Install: `uv tool install -U yotei`
- Config init: `yotei config init`
- Config default: `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- Data default: `${XDG_STATE_HOME:-~/.local/state}/yotei`
- Repo config: discover `.automation/yotei/config.toml` from current directory upward.
- Legacy compatibility: still discover `.automation/scheduled-agent-runner/config.toml` and `SCHEDULED_AGENT_RUNNER_CONFIG`, but do not require them.
- Task workspace: default to schedule-time current directory; persist it in the task; allow `--workspace`.
- Runner ownership: one active scheduler process per state database unless locking is implemented.

## Copy Plan For Later Implementation

Do not copy implementation until the portability contract above is accepted.

When implementation begins:

1. Copy `src/scheduled_agent_runner`, `tests`, `pyproject.toml`, and scheduler docs/specs into this repo, then rename the import package to `src/yotei`.
2. Remove Yolobox-specific README content, `.devcontainer`, `.takopi`, `.agents`, and checkout wrapper requirements.
3. Keep or replace `bin/yotei` only as a development convenience, not the install path.
4. Add `config init`, XDG discovery, and config template rendering.
5. Add `workspace_root` to task state and CLI scheduling.
6. Add tests for installed-tool use and machine-local config.
7. Update specs and ADRs to describe the dedicated repo behavior.
8. Run `uv run --extra dev pytest`, `python -m compileall src`, and an installed-tool smoke test.

## Risks And Open Questions

- Tool naming was changed to `yotei` after this research. `scheduled-agent-runner` remains the historical source name; `yolobox` would preserve brand but keeps the conceptual coupling.
- The scheduler currently assumes Codex is already installed and authenticated. The dedicated repo should state this explicitly rather than trying to manage Codex authentication.
- Task prompts are stored inline in SQLite. That is simple but may expose sensitive prompts in state backups.
- Telegram errors are swallowed. This avoids breaking runs but hides delivery failures.
- Cron behavior is intentionally limited and not fully compatible with all cron implementations.
- There is no task-level environment model. If scheduled tasks need different environment variables, that requires a separate design.
- Multi-process scheduler safety is not guaranteed.

## Conclusion

PR #2 contains a working, tested scheduler package, but it is packaged as Yolobox automation. The scheduler core can be ported with modest code movement. The dedicated repo should not copy it verbatim without first fixing install-time config creation, machine-local state paths, workspace persistence, repo-neutral docs, and tests that prove the command works after `uv tool install -U <tool-name>`.
