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

## Schedule Grammar

`yotei schedule --when` and `yotei edit --when` accept these forms:

- `in <int>m`, `in <int>h`, `once in <int>m`, `once in <int>h`
- `every <int>m`, `every <int>h`
- `daily H:MM`, `weekdays H:MM`
- `<day-list> H:MM`, where days are `mon,tue,wed,thu,fri,sat,sun`
- `cron "<minute> <hour> <day-of-month> <month> <day-of-week>"`

Clock times must use 24-hour `H:MM` or `HH:MM` form. Cron expressions use five numeric
fields. Supported cron field syntax is `*`, comma lists, ranges, and slash
steps. Names, `?`, `L`, `W`, `#`, wraparound ranges, and advanced cron
semantics are not supported. Day-of-month and day-of-week both have to match.

Full usage documentation will be expanded as the remaining portable install
contracts are implemented.
