# DigitalOcean FormalQualBench Verified8 Run

This runbook reproduces the eight Comparator-verified FormalQualBench tasks reported for OpenGauss.

## Runtime Contract

- Harness/runtime owner: OpenGauss native Lean workflow runner
- Model provider: `openai-codex`
- Model: `gpt-5.5`
- Reasoning effort: `high`
- API mode: `codex_responses`
- Benchmark backend: `native`
- MCP call count: `0`
- Comparator remains the scoring authority

Hermes HyperAgents is not part of this direct reproducibility lane. It is only an offline prompt/hint optimizer for separate benchmark campaigns.

## Tasks

The run uses:

- `DeBruijnErdos`
- `JordanDerangementTheorem`
- `ParisHarringtonPrinciple`
- `ColorfulCaratheodoryTheorem`
- `DLOQuantifierElimination`
- `BanachStoneTheorem`
- `GleasonKahaneZelazkoTheorem`
- `VonNeumannDoubleCommutantTheorem`

The tracked config is:

```bash
environments/benchmarks/formalqualbench/opengauss_verified8.yaml
```

## GitHub Setup

The repository is expected at:

```text
https://github.com/math-inc/OpenGauss
```

The tracked workflow is:

```text
.github/workflows/formalqualbench-verified8.yml
```

Because each task may run for up to four hours, use a DigitalOcean self-hosted GitHub Actions runner rather than a hosted GitHub runner.

Store the Gauss Codex auth store as a repository or environment secret:

```bash
base64 -i ~/.gauss/auth.json | pbcopy
```

Secret name:

```text
GAUSS_AUTH_JSON_BASE64
```

## DigitalOcean Host

Use an Ubuntu 24.04 droplet with enough disk for Mathlib, FormalQualBench, and Comparator build artifacts. A practical starting point is:

- image: Ubuntu 24.04 LTS
- size: at least 4 vCPU / 8 GB RAM
- disk: at least 80 GB

Install base dependencies:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl git golang-go jq pkg-config unzip xz-utils zstd
```

Install the GitHub self-hosted runner on the droplet, attach it to `math-inc/OpenGauss`, and give it a label such as:

```text
opengauss-formalqualbench-do
```

Then dispatch the workflow with:

```bash
gh workflow run formalqualbench-verified8.yml \
  --repo math-inc/OpenGauss \
  -f runner=opengauss-formalqualbench-do \
  -f run_id=do-verified8-$(date -u +%Y%m%d-%H%M%S)
```

## Direct SSH Run

You can also run the same lane directly on the droplet:

```bash
git clone https://github.com/math-inc/OpenGauss.git
cd OpenGauss
export GAUSS_AUTH_JSON_BASE64='<base64 ~/.gauss/auth.json>'
scripts/run_formalqualbench_verified8.sh
```

Artifacts are written under:

```text
$GAUSS_HOME/benchmarks/formalqualbench/verified8/<run-id>
```

The summary JSON records the task list, solve count, comparator results, artifact paths, `total_mcp_call_count`, and `total_tool_call_count`.
