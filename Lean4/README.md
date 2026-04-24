# OpenGauss Lean4 Library

This is the local Lean 4 library workspace for OpenGauss-driven theorem work.
The root module exposes reusable proof patterns and domain modules for algebra,
finite differences, linear combinations, divisibility, and order bounds.

## What is configured here

- `mathlib` pinned to Lean `v4.28.0`
- project-local OpenGauss manifest at `.gauss/project.yaml`
- AXLE/OpenGauss environment pinned to `lean-4.28.0`
- native OpenGauss Lean workflow support through the repo-root `gauss` command

## Typical Commands

```bash
cd /Users/agambirchhina/Documents/OpenGauss/Lean4
lake build
```

```bash
cd /Users/agambirchhina/Documents/OpenGauss
gauss
```

From the repo root, bare `gauss` selects this `Lean4` project and enables the `opengauss-lean` toolset with `openai-codex:gpt-5.5`.

## Layout

- `OpenGaussLean4.lean`: root module surface
- `OpenGaussLean4/Basic.lean`: shared core declarations
- `OpenGaussLean4/ProblemSolvingStrategies.lean`: cross-domain proof patterns
- `OpenGaussLean4/Algebra/`: algebraic identities
- `OpenGaussLean4/Calculus/`: calculus-facing finite difference identities
- `OpenGaussLean4/LinearAlgebra/`: scalar-combination facts for modules
- `OpenGaussLean4/NumberTheory/`: elementary divisibility lemmas
- `OpenGaussLean4/Order/`: bound-transfer lemmas
- `OpenGaussLean4/FoundationsOfMathematics/`: reserved area for foundations-focused work
