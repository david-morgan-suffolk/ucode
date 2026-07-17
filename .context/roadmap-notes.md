# Roadmap Notes

Durable project knowledge. Not a task tracker. Record completed milestones, decisions
that should outlive a single PR, accepted tech debt, and staged work.

## Completed Milestones

Recent, user-facing (see `git log` for the full history):

- `2026-06-14` — UC model discovery became the default; `--enable-uc` removed.
- `2026-06-22` — `configure mcp` surfaces Vector Search and UC Functions.
- `2026-07-01` — Model Provider Service routing for `claude` and `codex`.
- `2026-07-08` — `claude`: merge a caller's `--settings` instead of clobbering ucode's;
  disable built-in WebSearch via `permissions.deny`.
- `2026-07-13` — `--skip-preflight` to skip per-launch auth/gateway re-validation.
- `2026-07-17` — Role/project template distribution: agent-resource bundles served from
  a Unity Catalog Volume, threaded into Claude settings/permissions/hooks; MCP services
  applied additively.

## Durable Decisions

Record decisions here so they survive turnover. **Why** in one line.

- `uv` for environment and dependency management. *Why: fast, lockfile-based, single tool.*
- `ruff` for lint and format. *Why: one fast tool, consistent config.*
- `ty` for static type checking. *Why: catches contract drift before tests run.*
- `pytest`, no `unittest.TestCase` subclassing. *Why: fixtures compose better.*
- `typer` for the CLI surface. *Why: typed subcommands with minimal boilerplate.*
- `uv_build` build backend (not hatchling). *Why: single-tool build matching `uv`; ucode
  ships no wheel to PyPI.*
- Distribution via `uv tool install` + Unity Catalog Volume bundles, **not PyPI**.
  *Why: ucode is an internal developer tool tied to a Databricks workspace, not a public
  library.*
- Per-agent behavior isolated to `agents/<name>.py`, reached only via
  `agents/__init__.py` dispatchers. *Why: adding an agent is one new module + one registry
  entry, with no cross-agent coupling.*
- MCP config applied **additively** — never clobber user-defined servers. *Why: users
  own their config; ucode augments, backing up via `config_io.py`.*
- MLflow tracing is an optional `[tracing]` extra. *Why: keep a plain `ucode` install lean;
  only the Claude Code tracing path needs the Python MLflow runtime.*

## Accepted Tech Debt

- `ty` is a dev dependency and runnable locally but not enforced in CI yet — incremental
  adoption; revisit when type drift causes a regression.

## Staged Work

Pointer, not a backlog. Track active work in `.context/current-focus.md` when needed.
1. Continue the role/project template distribution feature (branch `templates-distribution`).

## Refresh Checklist

When this file is updated, also confirm:
- Commands in `.context/engineering-guide.md` still match `pyproject.toml`.
- Ownership Map in `.context/project-context.md` still matches `src/ucode/` layout.
- Durable decisions above still match what the code does. If a decision was silently
  reversed, fix the code or update the note.
