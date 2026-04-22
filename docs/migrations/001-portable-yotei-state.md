# Portable Yotei State Migration

Use this note when moving an existing Yotei installation to another machine,
home directory, or checkout.

## Copy These Files

- config: `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- state DB: `${XDG_STATE_HOME:-~/.local/state}/yotei/state.sqlite3`
- logs: `${XDG_STATE_HOME:-~/.local/state}/yotei/logs/`

Copy all three together when possible. The state DB stores task schedules,
session IDs, queue state, persisted workspaces, and run history. The log
directory stores full run output referenced by the DB.

## Before You Move

1. Stop any long-running `yotei run` process.
2. Back up the config file, state DB, and logs directory.
3. Confirm the target machine has a working `codex` CLI and any required
   Telegram environment variables.

## After You Restore

1. Install the same or newer compatible `yotei-runner` build.
2. Put the config, state DB, and logs back into the same XDG locations, or run
   Yotei with `--config <path>` if you are restoring elsewhere.
3. Run `yotei status`.
4. Repair any task whose workspace no longer exists on the new machine:

```sh
yotei edit --task <task-id> --workspace <path>
```

5. Run `yotei run --once` before starting the long-running scheduler.

## Notes

- Yotei preserves legacy config discovery for `.automation/yotei/config.toml`
  and `.automation/scheduled-agent-runner/config.toml`, but new installs should
  prefer `yotei config init` and user-level XDG paths.
- Workspace paths are machine-local. Yotei does not guess replacements.
- The first portable release still expects one active scheduler loop per state
  DB. Do not restore the same state DB into multiple concurrent runners.
