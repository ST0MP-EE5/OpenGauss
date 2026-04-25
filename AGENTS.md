# Gauss Agent - Development Guide

Instructions for AI coding assistants and developers working on this OpenGauss codebase.

## Development Environment

```bash
source .venv/bin/activate
```

Always activate the virtual environment before running Python commands or tests.

## Maintained Architecture

```text
gauss-agent/
├── gauss_cli/main.py          # `gauss` entrypoint and non-interactive subcommands
├── gauss_cli/codex_frontend.py# stock Codex profile staging/launch
├── gauss_cli/project.py       # OpenGauss project discovery and manifests
├── gauss_cli/lean_service.py  # local Lean project operations and LSP-style context
├── gauss_cli/lean_workflow.py # OpenGauss-owned Lean workflow runner
├── gauss_cli/mcp_server.py    # MCP adapter over OpenGauss services
├── toolsets.py                # canonical toolset definitions
├── tools/                     # registered tool implementations
├── run_agent.py               # AIAgent runtime used by harness services
├── environments/benchmarks/formalqualbench/
│   └── formalqualbench_env.py # OpenGauss-owned FormalQualBench harness
└── tests/
```

The maintained local UX is `gauss` -> stock Codex CLI with an OpenGauss-generated profile. Codex is the frontend/model runtime. OpenGauss owns the Lean harness, project state, AXLE, Comparator, retries, artifacts, and benchmark scoring.

## Entry Points

- `gauss`: stages a project-scoped Codex profile and launches stock Codex.
- `gauss setup`, `gauss status`, `gauss doctor`, `gauss config`: retained non-interactive OpenGauss commands.
- `gauss mcp-server`: adapter for external clients, including the local Codex profile.
- `gauss bench formalqual ...`: OpenGauss-owned FormalQualBench campaigns.

Do not reintroduce the old prompt_toolkit interactive CLI, duplicate launcher aliases, Forge/Claude launchers, or parity/reference benchmark lanes.

## Toolsets

The canonical Lean toolset is `opengauss-lean`. It includes file tools, AXLE, Lean local operations, Lean LSP-style context, Comparator, and controlled project inspection. It must not inherit arbitrary MCP tools or generic terminal as the proof interface.

## Adding Tools

1. Create `tools/your_tool.py` and register handlers through `tools.registry`.
2. Import the module in `model_tools.py` discovery.
3. Add the tool to `toolsets.py` under the correct OpenGauss-owned toolset.

All tool handlers must return JSON strings.

## Configuration

User config lives in `~/.gauss/config.yaml`; secrets live in `~/.gauss/.env`.

For persistent config changes:

1. Update `DEFAULT_CONFIG` in `gauss_cli/config.py`.
2. Bump the config version if existing users need migration.
3. Add tests that use the isolated `GAUSS_HOME` fixture; tests must not write to real `~/.gauss/`.

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Focused suites:

```bash
python -m pytest tests/gauss_cli/test_codex_frontend.py -q
python -m pytest tests/gauss_cli/test_lean_service.py -q
python -m pytest tests/gauss_cli/test_mcp_server.py -q
python -m pytest tests/test_formalqualbench_env.py -q
python -m pytest tests/test_toolsets.py -q
```

Run the full suite before pushing changes.
