import Mathlib.Algebra.Module.Basic

/-!
# Linear Combinations

Small module-level facts about scalar combinations in modules.
-/

namespace OpenGaussLean4
namespace LinearAlgebra

variable {R M : Type*} [Semiring R] [AddCommMonoid M] [Module R M]

theorem combine_same_vector (a b : R) (x : M) :
    a • x + b • x = (a + b) • x := by
  rw [add_smul]

theorem zero_left_combination (a : R) (x : M) :
    0 • x + a • x = a • x := by
  simp

end LinearAlgebra
end OpenGaussLean4
