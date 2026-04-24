# OpenGauss FormalQualBench Hyper Campaign

This directory contains an OpenGauss-owned HyperAgents setup for the native FormalQualBench sanity campaign.

Architecture:

- OpenGauss is the runtime and benchmark owner.
- The inner benchmark lane is the native OpenGauss Lean workflow runner.
- Hermes HyperAgents is an offline optimizer over benchmark prompts and hints.
- Comparator remains the only pass/fail authority.

The mutable benchmark surface lives under:

- `task_seed_profile/workspace/opengauss_formalqualbench/instructions.md`
- `task_seed_profile/workspace/opengauss_formalqualbench/startup_context.md`
- `task_seed_profile/workspace/opengauss_formalqualbench/theorem_hints/*.md`

Run the campaign with:

```bash
source .venv/bin/activate
python scripts/run_formalqualbench_hyper_campaign.py
```
