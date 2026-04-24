import Mathlib.Tactic

/-!
# Divisibility

Elementary divisibility lemmas that provide a concrete arithmetic surface for
OpenGauss Lean workflow checks.
-/

namespace OpenGaussLean4
namespace NumberTheory

theorem dvd_sum {a b c : Nat} (hab : a ∣ b) (hac : a ∣ c) :
    a ∣ b + c := by
  rcases hab with ⟨m, rfl⟩
  rcases hac with ⟨n, rfl⟩
  exact ⟨m + n, by rw [Nat.mul_add]⟩

theorem dvd_linear_combination {a b c m n : Nat}
    (hab : a ∣ b)
    (hac : a ∣ c) : a ∣ m * b + n * c := by
  rcases hab with ⟨r, rfl⟩
  rcases hac with ⟨s, rfl⟩
  exact ⟨m * r + n * s, by ring⟩

theorem even_mul_left {a b : Nat} (ha : 2 ∣ a) :
    2 ∣ a * b := by
  rcases ha with ⟨m, rfl⟩
  exact ⟨m * b, by ring⟩

end NumberTheory
end OpenGaussLean4
