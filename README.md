# OpenGauss

OpenGauss is a Lean-first workspace for native theorem work. The maintained product surface in this repository is:

- the OpenGauss CLI and project model
- the native OpenGauss Lean workflow runner
- AXLE-backed Lean proof-service integration
- the FormalQualBench benchmark environment
- Codex auth/runtime support for the direct `openai-codex` model provider
- MCP adapters for external clients
- installer scripts and local operating documentation

External agent launchers are outside the maintained Lean workflow path.

## Start Here

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
./scripts/install.sh
gauss
```

When `gauss` is launched from this repo root, it automatically selects the checked-in `Lean4` project, uses `openai-codex:gpt-5.5`, and enables the `opengauss-lean` toolset.

Inside the CLI:

```text
/project status
/prove
/autoprove
/formalize
/autoformalize
```

## Native Lean Workflows

OpenGauss handles Lean workflow commands in-process:

- `/prove`
- `/draft`
- `/review`
- `/checkpoint`
- `/refactor`
- `/golf`
- `/autoprove`
- `/formalize`
- `/autoformalize`

The native runner constructs an `AIAgent` with:

- provider: `openai-codex`
- model: `gpt-5.5`
- reasoning effort: `medium` by default; the verified8 reproducibility lane sets `high`
- API mode: `codex_responses`
- toolset: `opengauss-lean`

The proof interface does not expose generic shell execution. Local Lean operations go through controlled project tools such as `lean_project_status`, `lean_check_file`, `lean_lake_build`, and `lean_sorry_report`.

## Lean Tooling

The `opengauss-lean` toolset includes:

- file tools for scoped project edits
- AXLE proof-service tools
- local Lean project tools for status, file checks, builds, sorry reports, and verification summaries

AXLE environment resolution is project-first:

1. `lean_service.*` in the active project's `.gauss/project.yaml`
2. the active project's `lean-toolchain` file
3. global `gauss.lean_service.*` config

The checked-in Lean project is at [Lean4](Lean4), with project-local metadata at [Lean4/.gauss/project.yaml](Lean4/.gauss/project.yaml).

## MCP

`gauss mcp-server` remains available for external clients. MCP tools are adapters over the same Python services used by the native CLI; they no longer describe handoff argv/env plans as the maintained workflow contract.

## FormalQualBench

The retained benchmark environment lives at:

- `environments/benchmarks/formalqualbench`

The benchmark path is:

`FormalQualBench env -> native OpenGauss Lean runner -> Lean workspace -> Comparator`

Native benchmark runs record `mcp_call_count = 0`; comparator validation remains the final scoring authority.

For the eight OpenGauss solves reported in the FormalQualBench evaluation, use:

```bash
source .venv/bin/activate
scripts/run_formalqualbench_verified8.sh
```

The tracked config is [opengauss_verified8.yaml](environments/benchmarks/formalqualbench/opengauss_verified8.yaml). It runs `gpt-5.5` with `openai.reasoning_effort: high` and pins FormalQualBench, Comparator, and `lean4export` to Lean `v4.28.0`-compatible commits. The environment refuses to score a run if the Comparator or `lean4export` Lean toolchain differs from the FormalQualBench task toolchain. The DigitalOcean/self-hosted runner setup is documented in [formalqualbench-verified8.md](deploy/digitalocean/formalqualbench-verified8.md).

## Verification

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Useful targeted checks:

```bash
source .venv/bin/activate
python -m pytest tests/gauss_cli/test_lean_service.py -q
python -m pytest tests/gauss_cli/test_mcp_server.py -q
python -m pytest tests/test_formalqualbench_env.py -q
python -m pytest tests/test_runtime_provider_resolution.py tests/test_run_agent_codex_responses.py -q
```
