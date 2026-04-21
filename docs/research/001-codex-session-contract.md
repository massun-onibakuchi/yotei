# 001 Codex Session Contract

## Summary

This research verifies how the installed `codex` CLI exposes and resumes session identity in non-interactive mode. The goal is to reduce uncertainty for the scheduled agent runner plan before implementation.

## Environment

- Date: `2026-04-21`
- CLI binary: `/usr/local/share/npm-global/bin/codex`
- CLI version: `codex-cli 0.116.0`
- Runtime context: existing Linux container with authenticated `codex`

## Questions

- Can a non-interactive scheduled run obtain a stable session identifier without scraping internal files?
- Can a later scheduled run resume the same session in non-interactive mode?
- Does model selection affect session resume behavior?

## Commands Run

```sh
which codex
codex --version
codex --help
codex exec --help
codex exec resume --help
codex resume --help
codex exec --json --skip-git-repo-check -m gpt-5.4-mini "Reply with exactly OK."
codex exec resume --json 019daea1-00cf-7403-9a1a-8b05ec6f4809 "Reply with exactly AGAIN."
```

## Findings

### 1. Non-interactive execution is supported

`codex exec` is the non-interactive command intended for automation. It supports:

- `--json` for JSONL event output
- `-m, --model` for explicit model selection
- `-o, --output-last-message` for writing the final assistant message to a file
- `--ephemeral` for runs that should not persist session files

This is sufficient for a scheduler-style integration.

### 2. Session ID is exposed at runtime through JSON output

Running:

```sh
codex exec --json --skip-git-repo-check -m gpt-5.4-mini "Reply with exactly OK."
```

produced:

```json
{"type":"thread.started","thread_id":"019daea1-00cf-7403-9a1a-8b05ec6f4809"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}
{"type":"turn.completed","usage":{"input_tokens":10883,"cached_input_tokens":9088,"output_tokens":21}}
```

Implication:

- The scheduler does not need to scrape internal files to discover the session ID.
- The scheduler can persist `thread_id` directly from the `thread.started` event.

### 3. Non-interactive resume by session ID is supported

`codex exec resume --help` documents:

- positional `SESSION_ID`
- `--last`
- `--json`

Running:

```sh
codex exec resume --json 019daea1-00cf-7403-9a1a-8b05ec6f4809 "Reply with exactly AGAIN."
```

produced:

```json
{"type":"thread.started","thread_id":"019daea1-00cf-7403-9a1a-8b05ec6f4809"}
{"type":"item.completed","item":{"id":"item_0","type":"error","message":"This session was recorded with model `gpt-5.4-mini` but is resuming with `gpt-5.4`. Consider switching back to `gpt-5.4-mini` as it may affect Codex performance."}}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"AGAIN"}}
{"type":"turn.completed","usage":{"input_tokens":24804,"cached_input_tokens":12544,"output_tokens":38}}
```

Implication:

- Resume works in non-interactive mode with the previously stored session ID.
- The resumed run reused the same `thread_id`.
- Resume still succeeded despite model mismatch, but emitted a warning event.

### 4. Model drift is a real operational concern

The first run used `-m gpt-5.4-mini`. The resume run omitted `-m`, so Codex fell back to the configured default model `gpt-5.4` and emitted a warning.

Implication:

- The scheduler should persist both `session_id` and the model associated with that session.
- Resume runs should pass the stored model explicitly unless the user intentionally changes it.
- If a user changes models for an existing multi-turn task, the tool should default to a fresh session unless an explicit resume override is given.

### 5. Internal files also confirm stable session identity

Local files provide corroborating evidence:

- `~/.codex/history.jsonl` contains top-level `session_id`
- `~/.codex/sessions/.../*.jsonl` starts with `session_meta.payload.id`

Implication:

- Internal files are useful for debugging and forensic review.
- They are not required for the scheduler's core runtime contract because JSONL events already expose the needed ID.

## Confidence Update

- `95%`: a new scheduled run can capture a stable Codex session ID from `thread.started`
- `95%`: a later scheduled run can resume that session via `codex exec resume <session_id>`
- `90%`: the scheduler can avoid resume drift by persisting the task model and reusing it on resume
- `70%`: behavior around intentional model changes on an existing multi-turn task still needs product policy, not technical discovery

## Design Impact

- Session persistence should store the Codex `thread_id` exactly as returned.
- Resume mode should use `codex exec resume --json <session_id>`.
- Fresh mode should use `codex exec --json`.
- The task record should persist `model` alongside `session_id`.
- The CLI should expose a session option during scheduling, with `fresh` as the default and `resume` as the explicit opt-in mode.
- The CLI should treat model changes on resumed tasks as a policy-controlled action, not a silent update.

## Recommendation

For the first implementation:

- Persist `session_id` from `thread.started`
- Persist the model used to create that session
- Resume with `codex exec resume --json <session_id> -m <stored-model>`
- Default scheduled tasks to `session_mode=fresh`
- If the user changes model on a task with `session_mode=resume`, default to starting a fresh session unless an explicit override is given
