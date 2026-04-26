# FoM Project Guide

Instructions for AI coding assistants working inside the FoM Lean project.

The generalized Gauss project learning workflow is defined in the repository
root `AGENTS.md` and applies here. This file only adds FoM-specific source
context.

## Source Context

When a theorem, exercise, definition, or explanation comes from FoM source
material, record the relevant source path in nearby Lean comments/docstrings.
Common sources:

- `Sources/FoundationsOfMathematics/exam3_topics.pdf`
- `Sources/FoundationsOfMathematics/Book Of Proofs.pdf`

FoM learning files should remain topic-focused Lean files with inline pedagogy,
toy models, counterexamples, and reusable mini-lemmas where they clarify the
mathematical concept.
