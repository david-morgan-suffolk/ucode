# AGENTS.md

Canonical agent entry for this repo. Compact and operational. Deeper durable context
lives in `.context/`.

## Project Context

`ucode` is a Python CLI that configures and launches coding agents through Databricks
AI Gateway. The package code lives in `src/ucode/`; tests live in `tests/`.

Additional durable context lives in `.context/` (conventions in `.context/README.md`):

- Guides at the `.context/` root are durable tooling/workflow reference and never carry development progress:
  - [.context/project-context.md](.context/project-context.md) — product purpose, control flow, module ownership, durable decisions.
  - [.context/engineering-guide.md](.context/engineering-guide.md) — commands, Python standards, UI conventions, testing, safety, commits.
  - [.context/writing-tdds.md](.context/writing-tdds.md) — how to write a Technical Design Document for this repo.
- `.context/active/` holds ephemeral implementation docs (TDDs, design docs), named `YYYYMMDD-<doc-title>.md`. When implementing from an active doc, delete the doc in the PR that completes the work; active docs never persist past their implementation.

## Stack

Python 3.12+. `uv` for environment and dependencies, `ruff` for lint/format, `ty` for
static type checking, `pytest` for tests. `typer` for the CLI, `tomlkit` for config
writes, `questionary` + Rich for interactive UI, and the Databricks CLI/SDK for
workspace auth and model discovery. Build backend: `uv_build`. Distributed via
`uv tool install` and Unity Catalog Volume bundles — not published to PyPI.

## Commands

- Run the full test suite with `uv run pytest`.
- Run focused tests with `uv run pytest tests/<file>.py`.
- Run e2e tests with `UCODE_TEST_WORKSPACE=<db_workspace_url> uv run pytest tests/test_e2e.py -v`.
- Run lint with `uv run ruff check .`.
- Run static type checking with `uv run ty check`.
- Run the CLI from the current checkout with `uv run ucode ...`.
- Reinstall the local checkout as the `ucode` tool with `uv tool install --reinstall .`.

Cite exact command scope. Do not claim a command runs every test unless
`pyproject.toml` proves it.

## Standards

- Use Python 3.12+.
- Keep changes scoped to the requested behavior.
- Follow the existing module boundaries: CLI orchestration in `cli.py`, agent-specific behavior in `agents/<name>.py`, shared agent dispatch in `agents/__init__.py`, Databricks calls in `databricks.py`, and presentation helpers in `ui.py`.
- Prefer existing helpers for config file writes, state persistence, UI messages, and Databricks authentication.
- Add or update focused tests for behavior changes.
- Do not modify generated or lock files unless the dependency graph intentionally changes.
- Avoid broad refactors while fixing a narrow bug.
- Keep user-facing CLI errors actionable. Use warnings for recoverable setup problems and
  errors for launch/runtime blockers.
- Preserve existing Rich UI conventions, including `print_warning`, `print_err`,
  `print_success`, `print_section`, and `spinner`.

## Safety

Do not read `.env`, `.secrets`, certs, tokens, DSNs, or Databricks/cloud credentials.
Full list, search scope, and commit style live in
[`.context/engineering-guide.md`](.context/engineering-guide.md).

## Where To Edit

| File | Owns |
|---|---|
| `pyproject.toml` | Package metadata, deps, `[project.scripts]`, tool config (ruff, ty, pytest). |
| `uv.lock` | Resolved dependency lockfile. Do not hand-edit. |
| `src/ucode/cli.py` | `typer` app. Command orchestration + composition root. |
| `src/ucode/agents/__init__.py` | Agent registry + uniform dispatchers. |
| `src/ucode/agents/<name>.py` | One coding agent each (`SPEC`, `write_tool_config`, `default_model`, `launch`, `validate_cmd`). |
| `src/ucode/databricks.py` | Workspace auth, model discovery, AI Gateway v2, SQL warehouse, URL builders. |
| `src/ucode/config_io.py` | File I/O, dry-run, backup/restore, deep-merge, dotenv. |
| `src/ucode/state.py` | Per-workspace versioned state. |
| `src/ucode/ui.py` | Rich/questionary presentation primitives. |
| `tests/` | Pytest suite, mirroring `src/ucode/` module-by-module. |
| `.context/` | Durable architecture, decisions, debt. |
| `AGENTS.md` | This file. Keep compact; push detail into `.context/`. |

## Maintenance

Update `Commands` here when `pyproject.toml` scripts change. Update
`.context/project-context.md` when architecture, integrations, or ownership shift, or
when a durable decision (new agents, gateway/auth changes, distribution mechanics)
lands. Development progress and design docs belong in `.context/active/`, not in the
guides — see `.context/README.md`.
