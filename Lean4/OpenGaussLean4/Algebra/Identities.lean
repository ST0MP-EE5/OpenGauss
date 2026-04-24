import Mathlib.Tactic

/-!
# Algebraic Identities

Reusable ring identities for examples, proof warmups, and downstream
formalization work.
-/

namespace OpenGaussLean4
namespace Algebra

variable {R : Type*} [CommRing R]

theorem square_sub_square (a b : R) :
    a ^ 2 - b ^ 2 = (a - b) * (a + b) := by
  ring

theorem square_add (a b : R) :
    (a + b) ^ 2 = a ^ 2 + 2 * a * b + b ^ 2 := by
  ring

theorem cube_sub_cube (a b : R) :
    a ^ 3 - b ^ 3 = (a - b) * (a ^ 2 + a * b + b ^ 2) := by
  ring

end Algebra
end OpenGaussLean4
