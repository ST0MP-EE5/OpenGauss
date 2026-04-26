# FoM Project Agent Guide

Instructions for AI coding assistants working inside the FoM Lean project.

## Learning Workflow

When the user is using this project to learn Lean 4 or study Foundations of
Mathematics topics, preserve durable teaching context in Lean source files, not
Markdown tracker files.

For this workflow:

1. Record source context in nearby Lean comments/docstrings when a theorem or
   exercise comes from local material, especially:
   - `Sources/FoundationsOfMathematics/exam3_topics.pdf`
   - `Sources/FoundationsOfMathematics/Book Of Proofs.pdf`
2. Keep explanations aligned with the OpenGauss methodology:
   understand -> devise_plan -> carry_out -> look_back.
3. For theorem-by-theorem teaching, prefer pedagogical notes inline in the
   relevant `.lean` file as comments/docstrings near the theorem being studied.
4. Explain both proof ideas and Lean syntax directly in place when useful:
   `:`, `:=`, `by`, `{}` vs `()`, `->`, `forall`, `exists`, `and`, `or`,
   subset notation, `funext`, `ext`, tuple/constructor notation such as
   `⟨_, _⟩`, and field access such as `.1`/`.2`.
5. Keep chat responses short summaries of what changed; durable explanations
   should live next to the proof.
6. For learning-oriented Lean files, add nearby reusable mini-lemmas,
   counterexamples to tempting false statements, and toy models/special cases
   when they clarify the concept.

Do not create Markdown progress trackers for this workflow unless the user asks
for them explicitly.
