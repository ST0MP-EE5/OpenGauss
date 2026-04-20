# OpenGauss

OpenGauss is a Lean-first workspace for managed theorem work. The retained product surface in this repository is:

- the OpenGauss CLI and project model
- managed `forge` and `codex` backend lanes
- the FormalQualBench benchmark environment
- the auth/runtime bridge and environment substrate that those flows need
- installer scripts and minimal operating documentation

This repository no longer carries the old messaging, ACP, voice, skills-hub, or non-FormalQual benchmark surfaces.

## Start Here

Read the local guide at [docs/getting-started/start-here.md](docs/getting-started/start-here.md).

The short version:

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
./scripts/install.sh
gauss
```

Inside the CLI:

```text
/chat
/project init
/autoformalize
/swarm
```

## Core Product Boundary

OpenGauss is now explicitly scoped to:

- Lean project/runtime flow through the Gauss CLI
- managed backend staging for `forge` and `codex`
- FormalQualBench evaluation
- Hermes Hyper as an offline optimizer for the OpenGauss-managed Forge benchmark lane

The repository is not a general-purpose agent platform in this branch.

## Install

### macOS and Linux

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
./scripts/install.sh
```

### Windows via WSL2

```powershell
.\scripts\install.ps1 -WithWorkspace
```

## Managed Workflows

OpenGauss forwards Lean workflow commands into managed child sessions inside the active project:

- `/prove`
- `/draft`
- `/review`
- `/checkpoint`
- `/refactor`
- `/golf`
- `/autoprove`
- `/formalize`
- `/autoformalize`
- `/swarm`

The maintained managed backends are:

- `forge`
- `codex`

The default managed backend for the FormalQual path is `forge`.

## FormalQualBench

The retained benchmark environment lives at:

- `environments/benchmarks/formalqualbench`

The OpenGauss-native benchmark path is:

`FormalQualBench env -> OpenGauss runtime -> forge/codex managed backend -> Lean workspace -> Comparator`

Hermes Hyper is kept out of the runtime path and only optimizes the OpenGauss-managed Forge benchmark surface offline.

## Verification

The default suite is the real remaining full suite for this repo:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Useful targeted checks:

```bash
source .venv/bin/activate
python -m pytest tests/gauss_cli/test_autoformalize.py -q
python -m pytest tests/test_formalqualbench_env.py -q
python -m pytest tests/test_environment_auth_bridge.py -q
```

## Repository Layout

The core directories are:

- `gauss_cli/`
- `environments/`
- `tools/`
- `agent/`
- `tests/`
- `scripts/`
- `docs/`

## Origin

This repository was forked from `nousresearch/hermes-agent`, then contracted around the Lean/FormalQual/OpenGauss product.
