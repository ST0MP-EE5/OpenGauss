# OpenGauss

OpenGauss is a focused Lean 4 autoformalization workspace. The maintained local entrypoint is:

```bash
gauss
```

From this repository root, `gauss` auto-selects the checked-in `Lean4` project, stages a project-scoped Codex profile, and opens the stock Codex CLI with OpenGauss tools and instructions. Codex is the interface and model runtime; OpenGauss owns the Lean harness, project state, AXLE, Comparator, FormalQualBench retries, and artifacts.

To open another OpenGauss project in this repository, pass it explicitly:

```bash
gauss --project FoM
gauss --project Lean4
```

## Local Workflow

```bash
gauss
gauss --project FoM
```

The generated Codex profile uses:

- provider/runtime: `openai-codex`
- model: `gpt-5.5`
- reasoning effort: `high`
- project: `Lean4`
- tool bridge: `gauss mcp-server --transport stdio`

MCP is used only as the local transport adapter so stock Codex can call OpenGauss services. It is not the owner of proof workflow behavior.

Useful non-interactive commands:

```bash
gauss setup
gauss status
gauss doctor
gauss config show
gauss mcp-server
gauss bench formalqual run --config environments/benchmarks/formalqualbench/opengauss_verified8.yaml
```

## OpenGauss Harness

OpenGauss keeps the Lean workflow first-class:

- project discovery and `.gauss/project.yaml`
- Lean file checks, Lake builds, diagnostics, goals, hover/context, symbol lookup, and sorry reports
- AXLE tools
- Comparator proof audit
- controlled project inspection
- FormalQualBench workspace preparation, retries, artifacts, summaries, and scoring

The canonical Lean toolset is `opengauss-lean`. It intentionally avoids a generic terminal proof interface; local builds and checks go through OpenGauss service methods.

## FormalQualBench

The maintained benchmark path is:

```bash
gauss bench formalqual run --config environments/benchmarks/formalqualbench/opengauss_verified8.yaml
```

FormalQualBench calls OpenGauss harness services directly. It does not launch the Codex UI and does not use MCP as the scoring path. Comparator validation remains the final authority.

Artifacts are preserved per run under the configured output root, including backend logs, Lake build logs, Comparator logs, `Solution.lean`, `summary.json`, `samples.jsonl`, and `run_config.resolved.json`.

## Development

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

The old prompt_toolkit OpenGauss CLI, duplicate launch aliases, Forge/Claude launchers, and parity/reference benchmark lanes are not maintained in this cleaned-up workflow.
