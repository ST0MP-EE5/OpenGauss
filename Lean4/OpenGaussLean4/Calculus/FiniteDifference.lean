import Mathlib.Tactic

/-!
# Finite Difference Identities

Calculus-facing algebraic identities for discrete changes of low-degree
polynomials.
-/

namespace OpenGaussLean4
namespace Calculus

variable {R : Type*} [CommRing R]

theorem quadratic_forward_difference (x h : R) :
    (x + h) ^ 2 - x ^ 2 = 2 * x * h + h ^ 2 := by
  ring

theorem cubic_forward_difference (x h : R) :
    (x + h) ^ 3 - x ^ 3 = 3 * x ^ 2 * h + 3 * x * h ^ 2 + h ^ 3 := by
  ring

end Calculus
end OpenGaussLean4
