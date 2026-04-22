# Yotei

Yotei is a small scheduler for unattended Codex tasks.

## Install

```sh
uv tool install -U yotei-runner
```

Yotei expects the `codex` CLI to already be installed and authenticated on the
machine where scheduled runs execute. The scheduler invokes the configured Codex
binary directly and does not manage Codex login state for you.

The published package name is `yotei-runner`. The installed command remains
`yotei`.

## Quick Start

Initialize a user-level config file:

```sh
yotei config init
```

Schedule a task in the current directory:

```sh
yotei schedule \
  --task repo-review \
  --when "weekdays 09:30" \
  --prompt "Review the latest repository changes." \
  --chat-id 123456
```

Run one scheduler pass:

```sh
yotei run --once
```

Inspect current tasks:

```sh
yotei status
```

## Config Discovery And Paths

Config discovery order is:

1. `--config <path>`
2. `YOTEI_CONFIG`
3. `SCHEDULED_AGENT_RUNNER_CONFIG`
4. `.automation/yotei/config.toml` in the current directory or a parent
5. `.automation/scheduled-agent-runner/config.toml` in the current directory or a parent
6. `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`

By default, `yotei config init` writes:

- config: `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- state DB: `${XDG_STATE_HOME:-~/.local/state}/yotei/state.sqlite3`
- logs: `${XDG_STATE_HOME:-~/.local/state}/yotei/logs/`

Yotei uses the same XDG-style defaults on Linux and macOS when the XDG
variables are unset. That keeps installs portable and predictable across
machines.

## Workspace Semantics

Each task stores its own absolute `workspace_root`.

- `yotei schedule` defaults `--workspace` to the current directory
- `yotei schedule --workspace <path>` stores an explicit workspace
- `yotei edit --workspace <path>` repairs or changes a task workspace later
- `yotei status` shows each task's stored workspace
- `yotei run` executes Codex with that persisted workspace as `cwd`

If a stored workspace no longer exists on a machine, Yotei fails that run
cleanly and tells you to repair it with `yotei edit --workspace`.

## Scheduler Ownership

Yotei's first portable release expects one active scheduler process per state
database. Do not run multiple long-lived `yotei run` processes against the same
`state.sqlite3`; the current baseline documents this ownership contract instead
of using cross-platform lock files or database leases.

Use `yotei run` for the normal long-running scheduler. It polls for due tasks,
runs them from each task's persisted workspace, writes run logs, and keeps
polling until interrupted.

Use `yotei run --once` for tests, smoke checks, service hooks, or manual
maintenance. It performs one scheduler pass, including due tasks and at most one
queued run, then exits. The same single-runner policy applies while that pass is
running.

## Telegram

Telegram notifications are optional. Set `telegram.bot_token` and keep
`notifications.send_on_start`, `send_on_success`, and `send_on_failure` enabled
only for the events you want.

Use a literal token or an environment reference such as:

```toml
[telegram]
bot_token = "env:TG_BOT_TOKEN"
```

Notification delivery failures do not fail Codex runs. Yotei records concise
notification errors in run metadata and scheduler logs without writing the bot
token back into summaries or logs.

## Schedule Grammar

`yotei schedule --when` and `yotei edit --when` accept these forms:

- `in <int>m`, `in <int>h`, `once in <int>m`, `once in <int>h`
- `every <int>m`, `every <int>h`
- `daily H:MM`, `weekdays H:MM`
- `<day-list> H:MM`, where days are `mon,tue,wed,thu,fri,sat,sun`
- `cron "<minute> <hour> <day-of-month> <month> <day-of-week>"`

Clock times must use 24-hour `H:MM` or `HH:MM` form. Cron expressions use five
numeric fields. Supported cron field syntax is `*`, comma lists, ranges, and
slash steps. Names, `?`, `L`, `W`, `#`, wraparound ranges, and advanced cron
semantics are not supported. Day-of-month and day-of-week both have to match.

## Backup And Restore

Back up these paths together:

- `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- `${XDG_STATE_HOME:-~/.local/state}/yotei/state.sqlite3`
- `${XDG_STATE_HOME:-~/.local/state}/yotei/logs/`

To restore on another machine:

1. Install `yotei-runner` and make sure the target machine has a working `codex` CLI.
2. Restore the config file, state DB, and logs into the same XDG locations or
   pass `--config` explicitly.
3. Run `yotei status` and repair any task whose stored workspace path is no
   longer valid on the new machine with `yotei edit --workspace`.
4. Start the scheduler with `yotei run` or test one pass with `yotei run --once`.
