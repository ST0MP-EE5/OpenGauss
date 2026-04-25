# Start Here

OpenGauss is a project-scoped Lean workspace. It gives you a local CLI, a project model, native Lean workflows, AXLE tools, and FormalQualBench evaluation.

## What OpenGauss Does

OpenGauss is responsible for:

- detecting or initializing the active Lean project
- running Lean workflow commands in-process through OpenGauss
- using `openai-codex:gpt-5.5` as the default native Lean model runtime
- exposing controlled local Lean operations, native Lean context tools, AXLE proof-service tools, and Comparator audit tools
- running FormalQualBench through the same native runner
- serving MCP adapters for external clients

## Fastest Local Path

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
./scripts/install.sh
gauss
```

From the OpenGauss repo root, bare `gauss` automatically uses `Lean4`, `openai-codex:gpt-5.5`, and the `opengauss-lean` toolset.

## First Session

Inside `gauss`:

1. `/project status`
2. `/prove`
3. `/autoprove`
4. `/formalize`
5. `/autoformalize`

If you already have another Lean repo open, run `gauss` from that repo root and then `/project init` or `/project use <path>`.

## Native Lean Tools

Native workflow commands use file tools, AXLE tools, and controlled local Lean operations:

- `lean_project_status`
- `lean_check_file`
- `lean_lake_build`
- `lean_sorry_report`
- `lean_lsp_diagnostics`
- `lean_lsp_goals`
- `lean_lsp_hover`
- `lean_lsp_definition`
- `lean_lsp_references`
- `lean_lsp_symbols`
- `lean_proof_context`
- `lean_comparator_check`

Generic terminal execution is not the proof interface.

AXLE environment resolution is project-first:

1. `.gauss/project.yaml`
2. `lean-toolchain`
3. global `gauss.lean_service.*` config

## MCP

MCP is retained for external clients through `gauss mcp-server`. Those MCP tools call the same Python services as the native CLI; they are adapters, not the canonical workflow path.

## FormalQualBench

FormalQualBench runs directly through OpenGauss:

`FormalQualBench env -> native OpenGauss Lean runner -> Lean workspace -> Comparator`

Native runs report `mcp_call_count = 0`, preserve artifacts, and leave comparator validation as the final scoring authority.

```bash
gauss bench formalqual run --config environments/benchmarks/formalqualbench/opengauss_verified8.yaml
gauss bench formalqual resume --run-id <run-id-or-artifact-dir>
gauss bench formalqual summarize --run-id <run-id-or-artifact-dir>
```

## Verification

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Useful focused runs:

```bash
python -m pytest tests/gauss_cli/test_lean_service.py -q
python -m pytest tests/gauss_cli/test_mcp_server.py -q
python -m pytest tests/test_formalqualbench_env.py -q
```
