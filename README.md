# Yotei

Yotei is a small scheduler for unattended Codex tasks.

The current codebase contains the baseline scheduler package and tests. The portable
configuration, workspace, and install-flow work is being completed in small tickets
tracked in [docs/plans/001-portable-yotei.md](docs/plans/001-portable-yotei.md).

Target install command:

```sh
uv tool install -U yotei
```

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

Full usage documentation will be expanded as the remaining portable install
contracts are implemented.
