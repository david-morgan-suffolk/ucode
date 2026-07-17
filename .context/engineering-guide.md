# Engineering Guide

Operational standards for working in this Python CLI. Read before changing code.

## Commands

Environment + dependency manager: `uv`. Python: 3.12+ (pinned in `pyproject.toml`
`requires-python`). Build backend: `uv_build` (not hatchling); ucode is not published
to PyPI, so there is no release/twine flow.

| Command | Scope |
|---|---|
| `uv sync` | Install/update from `uv.lock`. Creates `.venv/` if missing. |
| `uv run ucode ...` | Run the CLI from the current checkout. |
| `uv run pytest` | Run the full test suite. |
| `uv run pytest tests/<file>.py` | Run one test file. |
| `uv run pytest -k <expr>` | Filter by expression. |
| `UCODE_TEST_WORKSPACE=<db_workspace_url> uv run pytest tests/test_e2e.py -v` | Run e2e tests against a real workspace. |
| `uv run ruff check .` | Lint. |
| `uv run ruff check --fix .` | Lint + autofix safe changes. |
| `uv run ruff format .` | Format. |
| `uv run ty check` | Static type check. |
| `uv tool install --reinstall .` | Reinstall the local checkout as the `ucode` tool. |
| `uv lock --upgrade` | Refresh `uv.lock` (intentional dep upgrade). |

State command scope exactly. Do not say "tests pass" if `-k` filtered out coverage you
needed. Do not claim a command runs every test unless `pyproject.toml` proves it
(`[tool.pytest.ini_options] testpaths = ["tests"]`).

## Python Standards

- `from __future__ import annotations` at the top of every module.
- Type hints on every public function, method, and module-level value. Internal helpers
  should be typed too unless trivially obvious.
- `ty check` strict. No implicit `Any`. Annotate generics fully (`list[int]`, not `list`).
- Prefer composition over inheritance. Inheritance is for type substitutability, not reuse.
- No mutable default arguments. No mutable module-level state (immutable constants are fine).
- Imports: stdlib, third-party, first-party — three groups, each sorted. `ruff` enforces
  (`I` rules). Line length 100; `E501` is delegated to the formatter.

## Data Contracts

Internal value objects use `@dataclass` (e.g. `ToolSpec` in `config_io.py`) — prefer
`@dataclass(frozen=True, slots=True)` for new value types. External data (agent config
files, Databricks API responses, dotenv) is parsed and validated at the boundary
(`config_io.py`, `databricks.py`) and handed downstream as typed values. ucode does not
use `pydantic` — parsing is explicit.

## Layout

```
src/ucode/
  cli.py               # typer app, command orchestration, composition root
  agents/
    __init__.py        # registry + uniform dispatchers
    <name>.py          # one coding agent each (SPEC, write_tool_config, default_model,
                       #   launch, validate_cmd)
  databricks.py        # workspace integration (auth, discovery, gateway, warehouse)
  config_io.py         # file I/O, dry-run, backup/restore, deep-merge, dotenv
  state.py             # per-workspace versioned state
  ui.py                # Rich/questionary presentation primitives (no project knowledge)
  launcher.py          # cross-platform process replacement
  ...                  # bootstrap, mcp, templates, telemetry, tracing, usage, agent_updates
tests/
  conftest.py          # shared fixtures
  test_<module>.py     # mirrors src/ucode/ module-by-module
```

- Follow the existing module boundaries. Reach agents only through the
  `agents/__init__.py` dispatchers; do not import `agents/<name>.py` internals elsewhere.
- Prefer existing helpers for config file writes (`config_io.py`), state persistence
  (`state.py`), UI messages (`ui.py`), and Databricks auth (`databricks.py`).

## UI Conventions

`ui.py` owns all presentation. Use its helpers, do not `print()` directly:

- `print_warning` for recoverable setup problems; `print_err` for launch/runtime blockers.
- `print_success`, `print_section`, and `spinner` per existing Rich conventions.
- Keep user-facing CLI errors **actionable** — tell the user the next step, not just the
  failure.

## Testing

- Pytest under `tests/`, one `test_<module>.py` per source module.
- Fixtures in `conftest.py`. No global mutable state — every fixture explicit per-test.
- `tmp_path` for filesystem; the `monkeypatch` fixture for env vars (ucode reads env for
  auth, so setting env in tests is expected).
- e2e tests are gated on `UCODE_TEST_WORKSPACE` and hit a real workspace — keep them out
  of the default fast path.
- Prefer a thin adapter you can replace with a fake over patching first-party modules.
- Add or update focused tests for every behavior change.

## Search Scope

When grepping/finding within the repo, exclude dependency, cache, and build output:

- `.venv/`, `venv/`
- `__pycache__/`
- `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.tox/`
- `dist/`, `build/`, `*.egg-info/`

```bash
rg --hidden -g '!{.venv,venv,__pycache__,.pytest_cache,.ruff_cache,dist,build,*.egg-info}/**' '<pattern>'
```

Metadata reads inside excluded dirs are fine when the file is the source of truth
(e.g. `uv.lock`).

## Safety: Do Not Read

- `.env`, `.env.*` (except `.env.example`)
- `.secrets/`, `secrets.toml`, `.envrc`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`
- Cloud credential files (`~/.aws/credentials`, service-account JSON), Databricks tokens
- Local DSNs, connection strings, bearer headers checked in by accident
- Tokens, API keys, session cookies, and provider response payloads containing user data

Metadata reads are fine: `pyproject.toml`, `uv.lock`, `pytest.ini`, `ruff.toml`, and
public config files. Preserve unrelated dirty work — never revert files you did not
intentionally change.

## Commits

- **One concern per commit.** Do not bundle a refactor with a feature with a dep bump.
- **Subject ≤ 72 chars, imperative mood.** Conventional prefix when useful
  (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`).
- **Body explains *why*, not *what*.** The diff shows what.
- **Lockfile updates commit with the source change that triggered them.** `uv.lock`
  rides with the `pyproject.toml` edit.
- **Never commit secrets.** Real tokens, DSNs, bearer headers, Databricks credentials.
- **Preserve unrelated dirty work.** Never restage or revert files you did not touch.

## Local Agent Scratch

Transient working files at repo root (`PLAN.md`, `TODO.md`, `NOTES.md`, `SCRATCH.md`)
are one session's in-flight reasoning — not durable docs, and git-ignored. `AGENTS.md`
is durable and stays committed. Durable architecture and decisions belong in the
`.context/` guides (committed); ephemeral implementation docs (TDDs, design docs) belong
in `.context/active/`, deleted by the PR that completes the work. Plans worth keeping
graduate into a guide, an active doc, or the PR description before the scratch file is
discarded.

## Context Maintenance

- Keep `AGENTS.md` compact. Push detail into these files.
- Update `Commands` above when `pyproject.toml` scripts change.
- Update `.context/project-context.md` when architecture, integrations, or ownership
  shift, or when a durable decision (new agents, gateway/auth changes, distribution
  mechanics) lands.
- Guides never carry development progress. Roadmaps, TDDs, and design docs go in
  `.context/active/` as `YYYYMMDD-<doc-title>.md`; the completing PR deletes them. See
  `.context/README.md` and `.context/writing-tdds.md`.
