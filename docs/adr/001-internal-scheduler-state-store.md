# ADR 001: Internal Scheduler With SQLite State

## Status

Accepted

## Context

The scheduled agent runner needs durable task state, queued same-task overlaps, per-task session IDs, and recoverable run history inside a container.

## Decision

Use an internal scheduler loop backed by SQLite for tasks, runs, enabled/paused state, and queue state. Use log files for full run output. Use Codex JSONL events as the runtime source of session IDs.

Schema ownership is tracked in `schema_migrations`. Version `1` is the imported
baseline scheduler schema. Future schema changes must add a new migration
function in `yotei.db`, increment `SCHEMA_VERSION`, and include tests for both a
fresh database and an upgraded database from the previous version.

## Consequences

- Good: state survives restarts and can be queried cheaply
- Good: same-task queueing is explicit and portable
- Good: pause, resume, and edit operate against one task state model
- Good: unexpected scheduler-loop errors are logged and retried with short backoff
- Good: the runner does not need cron glue or internal Codex file scraping
- Trade-off: the scheduler run loop must remain active inside the container
- Trade-off: SQLite schema ownership is now part of the application contract
