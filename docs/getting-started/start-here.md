# Start Here

OpenGauss is a project-scoped Lean workspace. It gives you a local CLI, a project model, and managed theorem workflows backed by `forge` or `codex`.

## What OpenGauss Does

OpenGauss is responsible for:

- detecting or initializing the active Lean project
- staging managed backend state for `forge` and `codex`
- forwarding Lean workflow commands into child sessions
- running the FormalQualBench benchmark environment

OpenGauss is not a messaging bot, ACP server, skills marketplace, or voice product in this repository.

## Fastest Local Path

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
./scripts/install.sh
gauss
```

## First Session

Inside `gauss`:

1. `/chat`
2. `/project init`
3. `/autoformalize`
4. `/swarm`

If you already have a Lean repo open, run `gauss` from that repo root and then `/project init`.

## Managed Backends

The retained managed backends are:

- `forge`
- `codex`

The default OpenGauss backend for the FormalQual path is `forge`.

Use:

```text
/autoformalize-backend
/autoformalize-backend forge
/autoformalize-backend codex
```

## FormalQualBench

FormalQualBench runs through the OpenGauss environment layer, not through a separate harness:

`FormalQualBench env -> OpenGauss runtime -> forge/codex -> Lean workspace -> Comparator`

Hermes Hyper is used only offline to optimize the OpenGauss-managed Forge benchmark surface.

## Verification

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Useful focused runs:

```bash
python -m pytest tests/gauss_cli/test_autoformalize.py -q
python -m pytest tests/test_formalqualbench_env.py -q
python -m pytest tests/test_environment_auth_bridge.py -q
```
