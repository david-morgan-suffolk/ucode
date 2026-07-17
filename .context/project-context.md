# Project Context

Durable architecture and ownership. Update when the shape of the codebase changes, not on every commit.

## What This Repo Is

`ucode` is a Python 3.12+ command-line **application** that configures and launches
coding agents (`claude`, `codex`, `copilot`, `gemini`, `opencode`, `pi`) against a
Databricks AI Gateway. It authenticates to a Databricks workspace, discovers the
model-serving endpoints exposed through the gateway, writes each agent's native config
files to point at those endpoints, and then execs the chosen agent CLI.

It is distributed as a developer tool via `uv tool install` (and via curated bundles
on Unity Catalog Volumes), not as a PyPI package. Reading environment/auth state,
writing agent config files, and launching subprocesses are its core job — it is not a
pure library.

## Architecture (Control Flow)

```
ucode CLI (typer app: src/ucode/cli.py)          ← command entry / composition root
  → agents dispatch (agents/__init__.py registry) ← uniform dispatch over per-agent modules
      → agents/<name>.py                          ← per-agent config layout, overlay, writer,
                                                     default model, launch, validate
  → Databricks integration (databricks.py)        ← CLI auth, token, model discovery,
                                                     AI Gateway v2 enforcement, SQL warehouse
  → config writers (config_io.py)                 ← file I/O, dry-run, backup/restore, deep-merge
  → state (state.py)                              ← per-workspace versioned persistence
  → Rich UI (ui.py)                               ← presentation primitives only
  → launcher.py                                   ← cross-platform process replacement (exec)
```

Source of truth for runtime config: the agent config files ucode writes plus the
resolved Databricks workspace/gateway. Source of truth for ucode's own persisted
choices: `state.py` (per-workspace, versioned). Per-agent behavior is isolated to its
module; the rest of the codebase talks to agents only through the `agents/__init__.py`
dispatchers.

## Ownership Map

| Path | Owns |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, `[project.scripts]` (`ucode`), tool config (ruff, ty, pytest). Build backend: `uv_build`. |
| `uv.lock` | Resolved dependency lockfile. Do not hand-edit. |
| `src/ucode/cli.py` | `typer` app. Command orchestration and composition root. |
| `src/ucode/agents/__init__.py` | Agent registry + uniform dispatchers (config, validate, launch, model resolution). |
| `src/ucode/agents/<name>.py` | One coding agent each. Exposes `SPEC`, `write_tool_config`, `default_model`, `launch`, `validate_cmd`. |
| `src/ucode/databricks.py` | Workspace integration: CLI auth, token retrieval, model discovery, AI Gateway v2 enforcement, SQL warehouse discovery, URL builders. |
| `src/ucode/config_io.py` | File I/O, dry-run flag, backup/restore, deep-merge, dotenv parsing. |
| `src/ucode/state.py` | Per-workspace, versioned ucode state. |
| `src/ucode/ui.py` | Rich/questionary presentation primitives. No project knowledge. |
| `src/ucode/launcher.py` | Cross-platform process replacement for launching agents. |
| `src/ucode/bootstrap.py` | Best-effort runtime/bootstrap installer for ucode dependencies. |
| `src/ucode/mcp.py`, `src/ucode/mcp_web_search.py` | MCP server registration; stdio `web_search` MCP server backed by a Databricks-hosted model. |
| `src/ucode/templates.py` | Role/project template distribution (agent-resource bundles from a UC Volume). |
| `src/ucode/telemetry.py`, `src/ucode/tracing.py`, `src/ucode/usage.py` | Outbound `User-Agent`; MLflow tracing to a Databricks experiment; usage report query/render. |
| `src/ucode/agent_updates.py` | Update checks for npm-installed agent CLIs. |
| `tests/` | Pytest suite. Mirrors `src/ucode/` module-by-module (`test_<module>.py`). |
| `.context/` | Agent-readable durable context. |
| `README.md` | Human-facing install, usage, commands. |

## External Integrations

- **Databricks workspace** — CLI/OAuth auth and PAT fallback, AI Gateway v2 model
  serving, model discovery, SQL warehouse discovery, and UC Volumes for template
  distribution. Credentials come from the Databricks CLI/SDK auth chain and env;
  ucode never persists raw secrets.
- **Coding agent CLIs** — `claude`, `codex`, `copilot`, `gemini`, `opencode`, `pi`.
  ucode writes their config files and launches them; it does not vendor them.
- **MCP servers** — registered into agent configs; ucode ships a `web_search` stdio
  MCP server. MCP config is applied **additively** — never clobbering user-defined
  servers.
- **MLflow tracing** — optional (`ucode[tracing]` extra); routes Claude Code sessions
  to a pre-provisioned Databricks experiment.

## Durable Decisions

Architecture and distribution choices that outlive any single change. Tooling rationale
(`uv`/`ruff`/`ty`/`pytest`) lives in `engineering-guide.md`.

- **`typer`** for the CLI surface. Typed subcommands with minimal boilerplate.
- **`uv_build`** build backend (not hatchling). Single-tool build matching `uv`; ucode
  ships no wheel to PyPI.
- **Distribution via `uv tool install` + Unity Catalog Volume bundles, not PyPI.** ucode
  is an internal developer tool tied to a Databricks workspace, not a public library.
- **Per-agent isolation.** Agent behavior lives only in `agents/<name>.py` and is reached
  through the `agents/__init__.py` dispatchers. Adding an agent is one new module plus one
  registry entry, with no cross-agent coupling.
- **MCP config applied additively.** ucode augments agent config and never clobbers
  user-defined servers; `config_io.py` backs up before writing.
- **MLflow tracing is an optional `[tracing]` extra.** A plain `ucode` install stays lean;
  only the Claude Code tracing path needs the Python MLflow runtime.

## Non-Goals

- No broad refactors while fixing a narrow bug; keep changes scoped to requested behavior.
- Do not bypass the module boundaries: agent-specific behavior stays in `agents/<name>.py`,
  reached only through `agents/__init__.py` dispatchers; Databricks calls stay in
  `databricks.py`; presentation stays in `ui.py`.
- Do not clobber user-owned config. Config application is additive (notably MCP servers)
  with backup/restore via `config_io.py`.
- No hard-coded model or workspace assumptions — discover from the gateway.
