# ucode

Launch coding agents through Databricks AI Gateway. No API keys. Workspace creds only.

Agents: Codex, Claude Code, Gemini CLI, OpenCode, GitHub Copilot CLI, Pi.

## Install

```bash
uv tool install git+https://github.com/david-morgan-suffolk/ucode
```

Need Python 3.12+ (via [uv](https://docs.astral.sh/uv/getting-started/installation/)). `npm` if agent CLIs auto-install.

## Run

Pick agent, run:

```bash
ucode codex      # OpenAI Codex
ucode claude     # Claude Code
ucode gemini     # Gemini CLI
ucode opencode   # OpenCode
ucode copilot    # GitHub Copilot CLI
ucode pi         # Pi
```

First launch → prompts workspace URL, authenticates, configures agent. Later launches go straight in.

Flags pass through to underlying tool:

```bash
ucode claude -r          # resume last session
ucode codex --full-auto
```

Skip per-launch auth + gateway re-check (trust prior configure):

```bash
ucode claude --skip-preflight
```

## Configure

All tools at once:

```bash
ucode configure
```

Specific tools, no picker:

```bash
ucode configure --agents claude,codex 
# supported: codex,claude,gemini,opencode,copilot
```

Skip picker, pass workspaces:
```bash
# Multiple workspaces → logs into each. Launch commands use first.
ucode configure --workspaces https://first.databricks.com,https://second.databricks.com

# Use existing Databricks CLI profiles (host = workspace URL) instead:
ucode configure --profiles DEFAULT --agents claude,codex
```

Auth same as `--workspaces`: OAuth login forced by default.

## Templates

Org publishes a **template store** (a UC Volume of curated agent bundles) → `ucode configure` fetches + applies the ones for you. Bundle can hold: MCP tool sets (additive — your MCPs kept), Claude skills, `CLAUDE.md` instructions, permission policies, hooks.

Auto-selected from Databricks group membership, or named:

```bash
ucode configure                       # auto-detect from groups
ucode configure --role data-engineer  # named role (skips auto-detect)
ucode configure --template shared --template data-engineer
```

Point at a store, or opt out:

```bash
ucode configure --templates-volume /Volumes/<catalog>/<schema>/<volume>
ucode configure --skip-templates
```

Store unreachable → configure still succeeds. Unavailable tool/model in a template → skipped. Everything applied is tracked; `ucode revert` removes it.


### Headless / CI

Profile holds a PAT (`auth_type = pat` in `~/.databrickscfg`) → add `--use-pat`. Requires `--profiles`. No browser. Access checked against AI Gateway.

```bash
# --skip-validate also skips the post-configure test message. Fully non-interactive
ucode configure --profiles DEFAULT --agents claude,codex --use-pat --skip-validate --skip-upgrade
```

## Model Provider routing

`ucode claude` and `ucode codex` take `--provider <catalog>.<schema>.<name>` → route through a Unity Catalog Model Provider Service (external Anthropic/OpenAI models). Skips Databricks model pinning. Pass before any `--`:

```bash
ucode claude --provider my_catalog.my_schema.anthropic
```

## MCP servers

Adds Databricks MCP servers to MCP-capable tools (Codex, Claude, Gemini, OpenCode, Copilot). Picker sources: external MCP connections, Databricks SQL, Genie spaces, Databricks Apps, managed MCPs (Vector Search, UC Functions, ...), custom URL. Auth uses a Databricks token ucode sets at launch.

```bash
ucode configure mcp
```


## Tracing

Send coding-session traces to an MLflow experiment in your workspace:

```bash
ucode configure --tracing   # enable while configuring
ucode configure tracing     # enable standalone
ucode configure tracing --disable
ucode status                # shows the tracing block.

# Claude tracing needs the extra:
uv tool install "ucode[tracing]"
```


## Commands

| Command | Does |
|---------|------|
| `ucode status` | Show workspace, base URLs, config files, models, tracing |
| `ucode usage` | AI Gateway usage summary (last 7 days) |
| `ucode revert` | Clear state, restore backed-up config files |
| `ucode upgrade` | Upgrade ucode from GitHub |
| `ucode configure --dry-run` | Preview config files, don't write |
| `ucode configure --tracing` | Enable MLflow tracing while configuring |
| `ucode configure tracing` | Configure tracing (`--disable` turns off) |

## Managed files

ucode manages these (backs up first; `ucode revert` restores):

| File | Tool |
|------|------|
| `~/.codex/config.toml` | Codex |
| `~/.claude/settings.json` | Claude Code |
| `~/.gemini/.env` | Gemini CLI |
| `~/.config/opencode/opencode.json` | OpenCode |
| `~/.copilot/.env` | GitHub Copilot CLI |
| `~/.pi/agent/models.json` | Pi |

## Docs

- [AI Gateway overview](https://docs.databricks.com/aws/en/ai-gateway/overview-beta)
- [Coding agent integration](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta)
- [Databricks CLI auth](https://docs.databricks.com/aws/en/dev-tools/cli/authentication)
- [Monitor gateway usage](https://docs.databricks.com/aws/en/ai-gateway/configure-ai-gateway-endpoints#track-usage-of-an-endpoint)

## Contributing

```bash
git clone https://github.com/david-morgan-suffolk/ucode
cd ucode
uv sync
```

Workflow: branch off `main` → change → test → PR.

```bash
uv run pytest          # unit tests
uv run ruff check .    # lint
```

E2E against a real workspace:

```bash
UCODE_TEST_WORKSPACE=<db_workspace_url> uv run pytest tests/test_e2e.py -v
```

Add an agent:

- Add `src/ucode/agents/<name>.py` with `write_tool_config`, `launch`, `default_model`, `validate_cmd`.
- Register in `src/ucode/agents/__init__.py`.
- Add tests under `tests/`.

## Security

Report vulnerabilities to security@databricks.com. Don't open a public issue.

## License

See [LICENSE.md](./LICENSE.md) and [NOTICE.md](./NOTICE.md).
