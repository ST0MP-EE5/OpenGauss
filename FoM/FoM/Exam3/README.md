# Exam 3 Lean4 Study Workspace

This folder is a Lean 4 learning workspace for the topics listed in
`/Users/agambirchhina/Documents/OpenGauss/Sources/FoundationsOfMathematics/exam3_topics.pdf`.

## OpenGauss methodology to use each session

Apply the project methodology from `FoM/Methodology.lean`:

1. **understand** the target, data, hypotheses, and notation
2. **devise_plan** by unfolding definitions, checking examples, and finding a
   related proof pattern
3. **carry_out** the proof in small Lean-checked steps
4. **look_back** by simplifying, extracting reusable lemmas, and noting what
   really did the work

## File map

- `Lean4Warmup.lean` — proposition/set/function syntax warmup
- `Functions.lean` — injective, surjective, bijective, composition, inverse,
  image, preimage
- `CalculusProofs.lean` — triangle inequality, continuity, and a Lean bridge to
  limit notation
- `Cardinalities.lean` — infinite/countable examples and explicit embeddings

## Exam topic map from the PDF

### Functions

- set definition of a function; domain and codomain
- injective, surjective, bijective
- composition
- inverse functions
- image and preimage
- set-theoretic proofs about image and preimage

### Proofs in Calculus

- triangle inequality
- epsilon-delta definition of limit
- proofs that limits do not exist
- use of limit laws
- continuity and differentiability
- limits at infinity

### Cardinalities

- same cardinality via explicit bijections
- finite vs. countably infinite vs. uncountable
- comparisons such as `|ℕ| = |ℤ| = |ℚ| < |ℝ|`

## Recommended study loop

1. Start in `Lean4Warmup.lean`.
2. Move to one topic file at a time.
3. Solve one commented practice prompt.
4. Run `lake build`.
5. Record one reusable proof pattern as a nearby Lean comment/docstring.

## Build

From the project root:

```bash
lake build
```

Keep durable explanations close to the relevant Lean declarations rather than
in separate Markdown progress trackers.
