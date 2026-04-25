import Mathlib.Analysis.Calculus.Deriv.Pow
import Mathlib.Analysis.SpecificLimits.Basic
import Mathlib.Tactic

/-!
# Exam 3 Proofs in Calculus

This module packages Lean versions of the exam themes:

- the triangle inequality;
- epsilon-delta limits;
- proving a limit does not exist using uniqueness;
- limit laws;
- continuity and differentiability;
- limits at infinity.
-/

namespace OpenGaussLean4
namespace FoundationsOfMathematics
namespace Exam3
namespace Calculus

open Filter
open scoped Topology

variable {α β : Type*}

theorem real_triangle_inequality (x y : ℝ) : |x + y| ≤ |x| + |y| := by
  simpa using abs_add_le x y

theorem real_dist_triangle (x y z : ℝ) : dist x z ≤ dist x y + dist y z := by
  simpa using dist_triangle x y z

theorem tendsto_real_at_iff {f : ℝ → ℝ} {a L : ℝ} :
    Tendsto f (𝓝 a) (𝓝 L) ↔
      ∀ ε > 0, ∃ δ > 0, ∀ ⦃x : ℝ⦄, dist x a < δ → dist (f x) L < ε := by
  simpa using (Metric.tendsto_nhds_nhds : _)

theorem tendsto_real_at_iff_abs {f : ℝ → ℝ} {a L : ℝ} :
    Tendsto f (𝓝 a) (𝓝 L) ↔
      ∀ ε > 0, ∃ δ > 0, ∀ ⦃x : ℝ⦄, |x - a| < δ → |f x - L| < ε := by
  simpa [Real.dist_eq] using (Metric.tendsto_nhds_nhds : _)

theorem tendsto_atTop_real_iff {u : β → ℝ} [Nonempty β] [SemilatticeSup β] {L : ℝ} :
    Tendsto u atTop (𝓝 L) ↔ ∀ ε > 0, ∃ N, ∀ n ≥ N, |u n - L| < ε := by
  simpa [Real.dist_eq] using (Metric.tendsto_atTop : _)

theorem tendsto_add_limit_law {f g : α → ℝ} {l : Filter α} {a b : ℝ}
    (hf : Tendsto f l (𝓝 a)) (hg : Tendsto g l (𝓝 b)) :
    Tendsto (fun x ↦ f x + g x) l (𝓝 (a + b)) :=
  hf.add hg

theorem tendsto_mul_limit_law {f g : α → ℝ} {l : Filter α} {a b : ℝ}
    (hf : Tendsto f l (𝓝 a)) (hg : Tendsto g l (𝓝 b)) :
    Tendsto (fun x ↦ f x * g x) l (𝓝 (a * b)) :=
  hf.mul hg

theorem limit_unique {f : α → ℝ} {l : Filter α} [NeBot l] {L M : ℝ}
    (hL : Tendsto f l (𝓝 L)) (hM : Tendsto f l (𝓝 M)) : L = M :=
  tendsto_nhds_unique hL hM

theorem no_limit_if_two_limits {f : α → ℝ} {l : Filter α} [NeBot l] {L M : ℝ}
    (hL : Tendsto f l (𝓝 L)) (hM : Tendsto f l (𝓝 M)) (hLM : L ≠ M) : False :=
  hLM (limit_unique hL hM)

example : Tendsto (fun x : ℝ ↦ x + 3) (𝓝 2) (𝓝 5) := by
  convert (tendsto_id.add tendsto_const_nhds : Tendsto (fun x : ℝ ↦ x + 3) (𝓝 2) (𝓝 (2 + 3)))
  norm_num

example : Continuous (fun x : ℝ ↦ x ^ 2 + 3 * x + 1) := by
  fun_prop

example : Differentiable ℝ (fun x : ℝ ↦ x ^ 2 + 3 * x + 1) := by
  fun_prop

theorem square_hasDerivAt (x : ℝ) : HasDerivAt (fun y : ℝ ↦ y ^ 2) (2 * x) x := by
  simpa [pow_two, two_mul, mul_comm, mul_left_comm, mul_assoc] using hasDerivAt_pow 2 x

theorem differentiableAt_implies_continuousAt {f : ℝ → ℝ} {x : ℝ}
    (hf : DifferentiableAt ℝ f x) : ContinuousAt f x :=
  hf.continuousAt

theorem inverse_tendsto_zero_atTop : Tendsto (fun x : ℝ ↦ x⁻¹) atTop (𝓝 0) := by
  simpa using tendsto_inv_atTop_zero

theorem one_div_tendsto_zero_atTop : Tendsto (fun x : ℝ ↦ 1 / x) atTop (𝓝 0) := by
  simpa [one_div] using inverse_tendsto_zero_atTop

end Calculus
end Exam3
end FoundationsOfMathematics
end OpenGaussLean4
