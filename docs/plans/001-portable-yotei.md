# 001 Portable Yotei Plan

## Goal

Make `yotei` portable across machines as a dedicated, installable CLI while preserving the working scheduler behavior researched from Yolobox PR #2.

Implementation must stay ticket-sized: one ticket maps to one small chunk, commit, or PR.

## Source Context

Primary research: `docs/research/001-yolobox-pr2-scheduled-agent-runner.md`.

The Yolobox PR already has a mostly reusable Python package, CLI, SQLite state model, tests, schedule parser, Codex execution contract, and Telegram notification support. The portability gaps are concentrated around:

- checkout-local config discovery and missing `config init`
- repository-shaped `.automation` defaults
- missing user-level config and XDG path handling
- missing per-task workspace persistence
- unclear single-runner ownership for SQLite state
- repo-neutral packaging, docs, and install verification
- minimal migration strategy for future schema changes

## Target Contract

- Repository name: `yotei`
- Package name: `yotei`
- Python import package: `yotei`
- Executable: `yotei`
- Supported install path: `uv tool install -U yotei`
- Python version: keep `>=3.12` initially unless packaging tests show a lower version is needed
- Default config path: `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- Default data path: `${XDG_STATE_HOME:-~/.local/state}/yotei`
- Repository-local config path: discover `.automation/yotei/config.toml` from the current directory upward
- Legacy compatibility config path: discover `.automation/scheduled-agent-runner/config.toml` after the new repo-local path
- Discovery order:
  1. explicit `--config`
  2. `YOTEI_CONFIG`
  3. legacy `SCHEDULED_AGENT_RUNNER_CONFIG`
  4. repository-local `.automation/yotei/config.toml`
  5. legacy repository-local `.automation/scheduled-agent-runner/config.toml`
  6. user config path
- Config creation: `yotei config init`
- Config init custom path: `yotei config init --path <path>`; global `--config` remains a config read/discovery override
- Workspace semantics: capture schedule-time current directory by default, persist it per task, allow `--workspace`, and refuse to run if the workspace no longer exists
- Legacy workspace semantics: tasks without `workspace_root` are not guessed; they are shown as needing migration and must be fixed with `edit --workspace`
- Runner ownership: one active scheduler loop per state database for the first portable release; this is documented first, with enforcement deferred to a later ticket
- Schedule grammar: keep `once in <int>m|h` as a documented alias for one-time relative schedules
- Backward compatibility: preserve repository-local config discovery and avoid leaking resolved secrets when rewriting config

## Ticket Plan

### Ticket 1: Import Baseline Package

Priority: P0

Dependencies: none

Parallelizable: no; this establishes the baseline for later tickets.

Chunk:

- Copy the reusable scheduler package from Yolobox PR #2 into this repo and rename it to Yotei:
  - source package `src/scheduled_agent_runner` becomes `src/yotei`
  - `tests`
  - `pyproject.toml`
  - relevant specs/docs that describe scheduler behavior
- Do not copy Yolobox-only project structure such as `.devcontainer`, `.takopi`, `.agents`, or checkout-specific workflow files.
- Keep any local `bin/yotei` wrapper only if useful for development, and document that the console script is the install path.

Acceptance:

- `uv run --extra dev pytest` passes.
- `uv run python -m compileall src` passes.
- Existing CLI behavior from the PR is available through the renamed package entry point.

Risks:

- Imported docs may still contain Yolobox-specific instructions.
- The copied package may assume repository-local paths before portability tickets land.

Confidence: 90

### Ticket 2: Repo-Neutral Package Metadata And README Skeleton

Priority: P0

Dependencies: Ticket 1

Parallelizable: yes, after Ticket 1; can run alongside test-only tickets that do not touch package metadata.

Chunk:

- Set final `pyproject.toml` metadata for the dedicated package.
- Ensure the console script is `yotei = "yotei.cli:main"`.
- Replace copied Yolobox README content with a minimal dedicated-repo skeleton:
  - project purpose
  - install command target
  - note that full usage docs land after portable config/workspace behavior is implemented
- Avoid detailed schedule/config/workspace examples in this ticket to reduce churn.

Acceptance:

- README no longer requires a Yolobox checkout or `bin/` wrapper.
- Package metadata does not mention Yolobox as the installable project.
- The README makes no claims that depend on later portability tickets.

Risks:

- The README remains intentionally thin until the final documentation pass.

Confidence: 90

### Ticket 3: XDG Paths And Config Discovery

Priority: P0

Dependencies: Ticket 1

Parallelizable: no with Ticket 4 because both touch config internals.

Chunk:

- Implement config discovery in the target order:
  - explicit `--config`
  - `YOTEI_CONFIG`
  - legacy `SCHEDULED_AGENT_RUNNER_CONFIG`
  - parent search for `.automation/yotei/config.toml`
  - legacy parent search for `.automation/scheduled-agent-runner/config.toml`
  - `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`
- Add default state/log paths under `${XDG_STATE_HOME:-~/.local/state}/yotei`.
- Preserve the existing behavior where relative `paths.state_db` and `paths.logs_dir` resolve relative to the config file directory.
- Keep legacy `.automation/scheduled-agent-runner` discovery for compatibility.

Acceptance:

- Tests cover env var discovery, parent-directory repo config discovery, XDG config discovery, XDG state defaults, and relative path resolution.
- Running outside a repo checkout uses the user config path.
- Tests cover invalid timezone handling with a clear configuration error.

Risks:

- Existing users with `.automation` configs may be surprised if a user-level config shadows it. The target discovery order avoids that by checking repo-local before user config.

Confidence: 85

### Ticket 4: `config init`

Priority: P0

Dependencies: Ticket 3

Parallelizable: no with Ticket 3.

Chunk:

- Add `yotei config init`.
- By default, write `${XDG_CONFIG_HOME:-~/.config}/yotei/config.toml`.
- Support an explicit output path with `config init --path <path>`.
- Keep global `--config` as a read/discovery override for commands that load an existing config, not as the init write target.
- Add an overwrite guard.
- Add a force flag only if needed by tests or practical CLI ergonomics.
- Print the written config path.
- Render secrets as references such as `env:TG_BOT_TOKEN`, not resolved values.

Acceptance:

- Init succeeds when parent directories do not exist.
- Init refuses to overwrite an existing config unless an explicit force option is used.
- Init output tells the user where the config was written.
- Tests prove the config template can be loaded immediately.

Risks:

- Users may expect global `--config` to affect init. Mitigation: make `config init --help` explicit and print the target path.

Confidence: 85

### Ticket 5: Schema Version Foundation

Priority: P0

Dependencies: Ticket 1

Parallelizable: yes with docs and CLI metadata work; no with workspace schema work.

Chunk:

- Add a minimal schema version table before widening the state model.
- Record the current baseline version.
- Provide a migration function that runs idempotently.
- Keep existing `CREATE TABLE IF NOT EXISTS` behavior where possible.
- Document how future migrations are added.

Acceptance:

- Existing empty DB initialization works.
- Existing PR-style DBs without a version table are upgraded to the baseline version.
- Tests cover fresh DB and legacy DB initialization.

Risks:

- The exact baseline version for copied PR state must be chosen carefully to avoid mislabeling partially migrated databases.

Confidence: 80

### Ticket 6: Persist Workspace On New Tasks

Priority: P0

Dependencies: Tickets 1 and 5

Parallelizable: no with schema migration work; yes with docs after the interface is agreed.

Chunk:

- Add `workspace_root` to task state.
- Add the column through the migration framework from Ticket 5, with legacy DB coverage.
- Default `schedule` to `Path.cwd()` at registration time.
- Add `schedule --workspace <path>`.
- Resolve and persist an absolute path.
- Validate that the workspace exists when scheduling.
- Allow the column to be nullable only for legacy rows created before this ticket.

Acceptance:

- New tasks store an absolute workspace path.
- Tests cover default workspace capture, explicit workspace, and missing workspace rejection.
- Existing legacy rows can still be read without crashing.

Risks:

- Legacy rows do not yet have a repair flow; Ticket 7 owns visibility and editing.

Confidence: 84

### Ticket 7: Workspace Repair And Legacy Handling

Priority: P0

Dependencies: Ticket 6

Parallelizable: no; this completes the workspace state contract.

Chunk:

- Add `edit --workspace <path>`.
- Show workspace state in `status`.
- For legacy tasks with missing `workspace_root`, show a clear `needs workspace` or equivalent status.
- Do not guess a legacy workspace from scheduler startup directory.
- Block execution of tasks missing `workspace_root` with a clear failed run that tells the user to run `edit --workspace`.

Acceptance:

- Tests cover `edit --workspace`.
- Tests cover status output for normal and legacy missing-workspace tasks.
- Tests cover execution refusal for legacy tasks missing `workspace_root`.

Risks:

- This is a stricter migration path than silently guessing. It may require manual repair for existing users, but it avoids running tasks in the wrong directory.

Confidence: 86

### Ticket 8: Execute Codex In The Persisted Workspace

Priority: P0

Dependencies: Ticket 7

Parallelizable: no; depends on workspace state.

Chunk:

- Change Codex subprocess execution to use the task's persisted `workspace_root` as `cwd`.
- Refuse execution with a clear failed run if the workspace path no longer exists.
- Ensure fresh and resumed Codex invocations use the same workspace behavior.
- Keep combined stdout/stderr logging unchanged.

Acceptance:

- Tests assert the Codex subprocess receives the expected `cwd`.
- Missing workspace creates a failed run with actionable error text and does not crash the scheduler loop.
- Existing session resume behavior still stores and reuses `session_id`.
- Missing Codex binary creates a failed run with actionable error text and does not crash the scheduler loop.

Risks:

- Codex resume may have workspace expectations tied to the original session. Persisting workspace per task is the cleanest available contract.

Confidence: 82

### Ticket 9: Single-Runner Ownership Contract

Priority: P0

Dependencies: Ticket 1

Parallelizable: yes after baseline import.

Chunk:

- Document the first-release policy: one active `run --loop` process per state database.
- Document `run --once` semantics under this policy.
- Add a startup warning or help text if there is an obvious place to surface the policy without adding locking.
- Do not implement lock files or DB-backed leases in this ticket.

Acceptance:

- Docs state the single-runner contract.
- `run --loop --help` or equivalent docs mention the single-runner policy.
- One-shot `run --once` behavior is explicitly documented.

Risks:

- Documentation-only ownership gives weaker protection than enforcement, but avoids introducing brittle cross-platform locking in the portability baseline.

Confidence: 87

### Ticket 10: Notification Failure Visibility

Priority: P2

Dependencies: Ticket 1

Parallelizable: yes.

Chunk:

- Preserve the non-fatal Telegram behavior.
- Append concise notification failure details to `runs.error_text`.
- Avoid storing bot tokens in logs or run summaries.
- Do not add a structured scheduler logging system in this ticket.

Acceptance:

- Tests prove notification exceptions do not fail Codex tasks.
- Tests prove failure details are recorded without leaking the token.

Risks:

- Run metadata can become noisy if notification failures are frequent. Keep entries concise.
- If `runs.error_text` starts to blur successful-run semantics, add a dedicated `notification_error` field in a later schema ticket.

Confidence: 84

### Ticket 11: Schedule Grammar Alignment

Priority: P1

Dependencies: Ticket 1

Parallelizable: yes.

Chunk:

- Keep `once in <int>m|h` as a supported and documented alias for one-time relative schedules.
- Align specs, README, parser tests, and help text.
- Document cron limitations:
  - five fields only
  - `*`, comma lists, ranges, and slash steps
  - no names, `?`, `L`, `W`, `#`, wraparound ranges, or advanced semantics
  - AND semantics for day-of-month and day-of-week
- Add tests for invalid clock forms and malformed day lists.

Acceptance:

- Help text, specs, README, and tests describe the same grammar.
- Invalid schedules fail with clear messages.

Risks:

- Keeping `once in` is a small grammar expansion, but it avoids breaking anyone who already used the PR behavior.

Confidence: 88

### Ticket 12: Early Installed Tool Smoke Test

Priority: P1

Dependencies: Tickets 2, 3, and 4

Parallelizable: no; verifies the first portability milestone.

Chunk:

- Add a smoke test or documented verification script for installed-tool behavior outside a repo checkout.
- Exercise:
  - console script invocation
  - `config init`
  - config discovery from user-level path
  - basic `config get-default-model`
- Keep it hermetic with temporary `XDG_CONFIG_HOME` and `XDG_STATE_HOME`.

Acceptance:

- The smoke path works from a temporary directory that has no `.automation` parent.
- The test does not depend on a real Codex invocation.

Risks:

- Full `uv tool install` inside automated tests can be slow. A console-script smoke using an isolated environment may be more maintainable.

Confidence: 83

### Ticket 13: Locking Or Lease Enforcement Design

Priority: P2

Dependencies: Tickets 5 and 9

Parallelizable: yes after the single-runner contract is documented.

Chunk:

- If this ticket is selected for the release, design and implement enforcement for one active scheduler loop per state database.
- Prefer a DB-backed lease or carefully scoped lock file only after evaluating cross-platform behavior.
- Define stale lock/lease recovery explicitly.
- Keep this separate from the first portable release if the design is not straightforward.

Acceptance:

- Tests cover second-runner refusal.
- Tests cover lock or lease release on normal exit.
- Tests cover stale lock or lease recovery if implemented.

Risks:

- Locking behavior can differ across filesystems and operating systems.
- A weak lock can create false confidence. Documentation-only ownership remains the baseline until this ticket lands.

Confidence: 72

Confidence below 80 reason: cross-platform locking and stale lease recovery require design validation.

### Ticket 14: Final Installed Tool Smoke Test

Priority: P1

Dependencies: Tickets 8, 11, and 12

Parallelizable: no; verifies integrated packaging, config, schedule, and workspace behavior.

Chunk:

- Extend the early smoke path to cover:
  - scheduling with default workspace
  - scheduling with explicit `--workspace`
  - status output with workspace information
  - a runner path that uses a fake Codex binary so no real Codex auth is needed

Acceptance:

- The smoke path works from a temporary directory that has no `.automation` parent.
- It verifies user-level config/state and persisted workspace behavior together.
- It does not depend on a real Codex invocation.

Risks:

- Overly broad smoke tests can become slow or flaky. Keep the full unit test suite responsible for edge cases.

Confidence: 82

### Ticket 15: Final Portability Documentation Pass

Priority: P2

Dependencies: Tickets 1 through 14, except Ticket 13 if lock enforcement is deferred

Parallelizable: no; this should follow behavior changes.

Chunk:

- Update README, specs, ADRs, and migration notes after implementation.
- Include:
  - install flow
  - config discovery order
  - XDG paths
  - workspace semantics
  - single-runner ownership
  - Codex prerequisites
  - Telegram setup
  - cron limitations
  - backup/restore guidance for state DB and logs

Acceptance:

- A new user can install, initialize config, schedule a task, run one pass, and understand where state/logs live without reading source code.
- Docs avoid Yolobox-only assumptions.

Risks:

- Documentation-only changes can miss subtle behavior introduced in earlier tickets unless cross-checked with CLI help and tests.

Confidence: 88

## Dependency Map

Sequential path:

1. Ticket 1
2. Ticket 2
3. Ticket 3
4. Ticket 4
5. Ticket 12
6. Ticket 5
7. Ticket 6
8. Ticket 7
9. Ticket 8
10. Ticket 14
11. Ticket 15

Can run after Ticket 1 in parallel:

- Ticket 2, because it is now only metadata plus a README skeleton
- Ticket 9
- Ticket 10
- Ticket 11

Must remain sequential:

- Ticket 3 before Ticket 4 because init depends on final config path rules
- Ticket 5 before Ticket 6 because workspace persistence changes schema
- Ticket 6 before Ticket 7 because legacy repair needs the new field
- Ticket 7 before Ticket 8 because execution depends on a complete workspace contract
- Ticket 12 after config and packaging behavior exists
- Ticket 14 after workspace execution exists
- Ticket 15 after all baseline behavior is settled

## Proposed Implementation Order

1. Import baseline package and tests.
2. Establish dedicated package metadata and repo-neutral README skeleton.
3. Add XDG discovery and portable defaults.
4. Add `config init`.
5. Add early installed-tool smoke verification for config portability.
6. Add schema version foundation.
7. Add persisted workspace for new tasks.
8. Add workspace repair and legacy handling.
9. Execute Codex from persisted workspace.
10. Align schedule grammar and cron docs/tests.
11. Add single-runner ownership documentation.
12. Improve notification failure visibility.
13. Add final installed-tool smoke verification.
14. Complete final documentation pass.
15. Design and implement lock or lease enforcement only if needed for this release.

## Risks And Mitigations

- Backward compatibility: repo-local `.automation` configs must keep working. Mitigation: preserve parent search before user config fallback.
- Secret safety: config rewrites must not write resolved Telegram tokens. Mitigation: keep source-preserving config rendering and add tests around every config-mutating command.
- Workspace portability: machine paths can disappear or differ. Mitigation: persist absolute workspaces, show them in status, and fail runs clearly when missing.
- Forward compatibility: schema changes will continue. Mitigation: add a version table before workspace migration.
- Multi-process safety: SQLite state is not enough for multiple active loops. Mitigation: document one-runner ownership in the baseline and keep enforcement as a separate design ticket.
- Cron compatibility: custom cron behavior differs from common cron implementations. Mitigation: document limitations and test edge cases.
- Maintainability: too many behavior changes in one PR would be hard to review. Mitigation: keep each ticket as one small commit or PR with focused tests.

## Open Decisions

- Is Ticket 13 required for the first portable release, or can the documented one-runner contract ship first?
