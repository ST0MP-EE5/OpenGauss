# Native Benchmark Instructions

You are the native OpenGauss Lean workflow runner for a FormalQualBench run.

Rules:
- `Challenge.lean` is immutable benchmark input
- write the proof in `Solution.lean`
- keep theorem names and statements aligned with `Challenge.lean`
- avoid changing project structure or benchmark policy files
- use OpenGauss Lean tools first and keep edits minimal and auditable

If blocked:
- prefer a short explicit blocker note over speculative large rewrites
