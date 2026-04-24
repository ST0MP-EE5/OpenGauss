#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG_PATH="${CONFIG_PATH:-$REPO_ROOT/environments/benchmarks/formalqualbench/opengauss_verified8.yaml}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d-%H%M%S)}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${GAUSS_HOME:-$HOME/.gauss}/benchmarks/formalqualbench/verified8/$RUN_ID}"
SUMMARY_PATH="${SUMMARY_PATH:-$OUTPUT_ROOT/summary.json}"
SAMPLES_PATH="${SAMPLES_PATH:-$OUTPUT_ROOT/samples.jsonl}"

mkdir -p "$OUTPUT_ROOT"

if [ -n "${GAUSS_AUTH_JSON_BASE64:-}" ]; then
  mkdir -p "${GAUSS_HOME:-$HOME/.gauss}"
  printf '%s' "$GAUSS_AUTH_JSON_BASE64" | base64 --decode > "${GAUSS_HOME:-$HOME/.gauss}/auth.json"
  chmod 600 "${GAUSS_HOME:-$HOME/.gauss}/auth.json"
fi

if [ ! -f "${GAUSS_HOME:-$HOME/.gauss}/auth.json" ]; then
  cat >&2 <<'TXT'
Missing OpenAI Codex auth for the native OpenGauss runner.

Provide one of:
  - an existing ~/.gauss/auth.json created by `gauss model` with provider openai-codex
  - GAUSS_AUTH_JSON_BASE64 containing that auth.json payload

The verified8 lane uses provider=openai-codex and model=gpt-5.5.
TXT
  exit 2
fi

cd "$REPO_ROOT"

if [ ! -d ".venv" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv --python 3.11
  else
    python3 -m venv .venv
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if command -v uv >/dev/null 2>&1; then
  uv pip install -e ".[all,dev]"
else
  python -m pip install -e ".[all,dev]"
fi

export HERMES_HYPER_SUMMARY_PATH="$SUMMARY_PATH"
export HERMES_HYPER_SAMPLES_PATH="$SAMPLES_PATH"

python environments/benchmarks/formalqualbench/formalqualbench_env.py \
  evaluate \
  --config "$CONFIG_PATH" \
  --env.output_root "$OUTPUT_ROOT"

printf 'FormalQualBench verified8 summary: %s\n' "$SUMMARY_PATH"
printf 'FormalQualBench verified8 samples: %s\n' "$SAMPLES_PATH"
