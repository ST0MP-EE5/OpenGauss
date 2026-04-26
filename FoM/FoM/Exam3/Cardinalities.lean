import Mathlib
import FoM.Methodology

/-!
# Exam 3 Topic: Cardinalities

This file starts a Lean workspace for finite, infinite, and countable objects.
It is intentionally modest: the goal is to give you a clean place to practice
explicit injections, surjections, and equivalences.
-/

namespace FoM.Exam3

section CoreFacts

example : Infinite ℕ := by infer_instance

example : Countable ℤ := by infer_instance

example : Countable ℚ := by infer_instance

def succEmbedding : ℕ ↪ ℕ where
  toFun n := n + 1
  inj' := by
    intro a b h
    exact Nat.add_right_cancel h

theorem succEmbedding_formula (n : ℕ) : succEmbedding n = n + 1 := rfl

end CoreFacts

/-!
## Practice prompts

1. Build an explicit bijection between `ℕ` and the positive naturals.
2. Show that a finite set cannot be in bijection with `ℕ`.
3. Formalize one proof that two sets have the same cardinality by constructing a
   bijection directly.
4. Record, in comments or a notebook, where your proof used injectivity,
   surjectivity, or both.

Course reminder from the exam outline:

- know why `|ℕ| = |ℤ| = |ℚ|`
- know that `|ℚ| < |ℝ|`

Those statements are good targets for later files once the Lean basics feel
comfortable.
-/

end FoM.Exam3
