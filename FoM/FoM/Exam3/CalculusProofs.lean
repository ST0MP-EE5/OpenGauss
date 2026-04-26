import Mathlib
import FoM.Methodology

/-!
# Exam 3 Topic: Proofs in Calculus

This file gives a small Lean bridge from the course's epsilon-delta language to
mathlib's `Tendsto` language. It also includes a few starter theorems around
absolute values, continuity, and limits.
-/

namespace FoM.Exam3

open Filter Real Topology

/-- Course-language alias: `f` approaches `L` as `x` approaches `a`. -/
def Approaches (f : ℝ → ℝ) (a L : ℝ) : Prop :=
  Tendsto f (𝓝 a) (𝓝 L)

/-- Course-language alias: `f` approaches `L` as `x → ∞`. -/
def ApproachesAtTop (f : ℝ → ℝ) (L : ℝ) : Prop :=
  Tendsto f atTop (𝓝 L)

theorem triangle_inequality (x y : ℝ) : |x + y| ≤ |x| + |y| := by
  exact abs_add_le x y

theorem constant_limit (a c : ℝ) : Approaches (fun _ : ℝ => c) a c := by
  simp [Approaches]

theorem identity_limit (a : ℝ) : Approaches (fun x : ℝ => x) a a := by
  simpa [Approaches] using tendsto_id

theorem continuous_square_plus_one : Continuous fun x : ℝ => x ^ 2 + 1 := by
  continuity

/-!
## Practice prompts

1. Translate a statement of the form `lim x→a (f x + g x) = L + M` into `Tendsto`.
2. Reprove `triangle_inequality` by finding the relevant theorem in mathlib.
3. Use `continuity` or existing lemmas to show `Continuous fun x : ℝ => x^3 - 7 * x`.
4. State, in words, how the epsilon-delta definition corresponds to `Tendsto`.

For exam preparation, you should still practice handwritten epsilon-delta proofs.
This Lean file is a translation aid, not a replacement for that work.
-/

end FoM.Exam3
