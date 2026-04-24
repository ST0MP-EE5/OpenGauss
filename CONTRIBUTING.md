# Contributing to OpenGauss

OpenGauss is now maintained as a Lean/FormalQual workspace, not as a broad multi-surface agent platform. Changes should support one of these areas:

- Lean project/runtime flow
- native OpenGauss Lean workflows
- FormalQualBench evaluation
- auth/runtime bridge and environment substrate for those flows
- installer and local operating documentation

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,pty,mcp]
```

## Test Contract

The default suite is the actual remaining suite:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Run focused checks while iterating:

```bash
source .venv/bin/activate
python -m pytest tests/gauss_cli/test_autoformalize.py -q
python -m pytest tests/test_formalqualbench_env.py -q
python -m pytest tests/test_environment_auth_bridge.py -q
```

## Repo Shape

The expected core tree is:

- `gauss_cli/`
- `environments/`
- `tools/`
- `agent/`
- `tests/`
- `scripts/`
- `docs/`

Do not reintroduce deleted surfaces such as gateway/messaging adapters, ACP integration, bundled skill catalogs, voice/transcription flows, or non-FormalQual benchmark families without an explicit product decision.

## Docs

Keep documentation repo-local. New onboarding or operating docs belong under `docs/`, not in a website or landing-page stack.

## Installers

Installer work should keep the default path focused on:

- local CLI install
- Lean workspace bootstrap
- OpenAI Codex auth setup for the native `openai-codex` provider

Do not add references to deleted platform integrations or background services.

## Pull Requests

Keep PRs scoped and explain:

- which core surface changed
- what user-facing behavior changed
- which tests were run
