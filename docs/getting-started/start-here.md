# Start Here

OpenGauss has one maintained local entrypoint:

```bash
gauss
```

When run from `/Users/agambirchhina/Documents/OpenGauss`, `gauss` selects the checked-in `Lean4` project, stages a project-scoped Codex profile, and opens stock Codex with OpenGauss instructions and tools. Use `gauss --project FoM` to open the Foundations of Mathematics project instead.

## Ownership Model

- Codex is the UI and model runtime.
- OpenGauss owns the Lean harness, project state, AXLE, Comparator, retries, artifacts, and benchmark scoring.
- MCP is only an adapter so stock Codex can call OpenGauss services.
- FormalQualBench calls OpenGauss services directly rather than going through MCP or the Codex UI.

## Daily Use

```bash
gauss
gauss --project FoM
gauss status
gauss doctor
gauss config show
```

Inside Codex, use the OpenGauss tool surface for Lean work: diagnostics, goals, hover/context, symbol search, file checks, Lake builds, sorry reports, AXLE, controlled project inspection, and Comparator.

## Benchmarks

```bash
gauss bench formalqual run --config environments/benchmarks/formalqualbench/opengauss_verified8.yaml
```

The maintained FormalQualBench lane uses `openai-codex:gpt-5.5` with reasoning effort `high`, preserves run artifacts, and treats Comparator as the final scoring authority.
