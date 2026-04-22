# ADR 001: Internal Scheduler With SQLite State

## Status

Accepted

## Context

The scheduled agent runner needs durable task state, queued same-task overlaps, per-task session IDs, and recoverable run history inside a container.

## Decision

Use an internal scheduler loop backed by SQLite for tasks, runs, enabled/paused state, and queue state. Use log files for full run output. Use Codex JSONL events as the runtime source of session IDs.

Schema ownership is tracked in `schema_migrations`. Version `1` is the imported
baseline scheduler schema. Version `2` adds nullable per-task `workspace_root`
storage for newly scheduled tasks while preserving legacy rows. Version `3`
adds nullable `runs.notification_error` for non-fatal notification failures.
Future schema changes must add a new migration function in `yotei.db`, increment
`SCHEMA_VERSION`, and include tests for both a fresh database and an upgraded
database from the previous version.

Runtime ownership is intentionally documented rather than enforced in the first
portable release: one active scheduler loop per state database. Persisted task
workspaces are part of the state contract, so restoring or moving the state DB
across machines may require repairing `workspace_root` with `yotei edit
--workspace`.

## Consequences

- Good: state survives restarts and can be queried cheaply
- Good: same-task queueing is explicit and portable
- Good: pause, resume, and edit operate against one task state model
- Good: unexpected scheduler-loop errors are logged and retried with short backoff
- Good: the runner does not need cron glue or internal Codex file scraping
- Good: persisted workspaces make installed-tool runs portable across checkouts
- Good: notification-only failures no longer look like task failures
- Trade-off: the scheduler run loop must remain active inside the container
- Trade-off: SQLite schema ownership is now part of the application contract
- Trade-off: scheduler ownership is still a documented operational contract, not
  a lock or lease enforced by the runtime
