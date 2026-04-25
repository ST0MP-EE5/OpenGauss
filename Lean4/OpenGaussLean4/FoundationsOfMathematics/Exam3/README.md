# Foundations of Mathematics Exam 3 Study Project

This study track was created from:

- `/Users/agambirchhina/Documents/OpenGauss/Sources/FoundationsOfMathematics/exam3_topics.pdf`

## Modules

- `OpenGaussLean4.FoundationsOfMathematics.Exam3.Functions`
- `OpenGaussLean4.FoundationsOfMathematics.Exam3.Calculus`
- `OpenGaussLean4.FoundationsOfMathematics.Exam3.Cardinality`

## Topic map

### Functions

- function type = domain/codomain in Lean
- injective, surjective, bijective
- composition
- inverse functions via `Function.LeftInverse` and `Function.RightInverse`
- image and preimage
- image/preimage set proofs

### Proofs in Calculus

- triangle inequality
- epsilon-delta limits as `Metric.tendsto_nhds_nhds`
- limit laws through `Tendsto`
- continuity and differentiability
- limits at infinity through `Metric.tendsto_atTop`

### Cardinality

- same cardinality as equivalence `α ≃ β`
- finite and countable sets
- countably infinite types via `Denumerable`
- `|ℕ| = |ℤ| = |ℚ| < |ℝ|`

## How to use it with OpenGauss

From the repo root:

```bash
cd /Users/agambirchhina/Documents/OpenGauss
gauss
```

From the Lean workspace:

```bash
cd /Users/agambirchhina/Documents/OpenGauss/Lean4
lake build
```

## Suggested learning workflow

1. Open one module at a time.
2. Read the theorem statement before the proof.
3. Try deleting the proof body locally and re-prove it yourself.
4. Use mathlib search and OpenGauss proof context when you get stuck.
5. After you can re-prove the examples, add your own variants beside them.
