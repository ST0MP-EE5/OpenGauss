import Mathlib.Analysis.Real.Cardinality
import Mathlib.Data.Rat.Denumerable
import Mathlib.Data.Set.Countable
import Mathlib.Logic.Denumerable

/-!
# Exam 3 Cardinality

This module gathers representative Lean statements for:

- same cardinality via equivalences;
- finite versus countable sets;
- countably infinite types;
- the comparison `|ℕ| = |ℤ| = |ℚ| < |ℝ|`.
-/

namespace OpenGaussLean4
namespace FoundationsOfMathematics
namespace Exam3
namespace Cardinality

open Set

variable {α β : Type*}

theorem finite_sets_are_countable {s : Set α} (hs : s.Finite) : s.Countable :=
  hs.countable

theorem countable_image {f : α → β} {s : Set α} (hs : s.Countable) : (f '' s).Countable :=
  hs.image f

theorem countable_union {s t : Set α} (hs : s.Countable) (ht : t.Countable) :
    (s ∪ t).Countable :=
  hs.union ht

noncomputable def natEquivInt : ℕ ≃ ℤ := Denumerable.equiv₂ ℕ ℤ

noncomputable def natEquivRat : ℕ ≃ ℚ := Denumerable.equiv₂ ℕ ℚ

noncomputable def intEquivRat : ℤ ≃ ℚ := Denumerable.equiv₂ ℤ ℚ

theorem real_uncountable : Uncountable ℝ :=
  Set.not_countable_univ_iff.mp Cardinal.not_countable_real

theorem countably_infinite_of_denumerable (γ : Type*) [Denumerable γ] : Nonempty (γ ≃ ℕ) := by
  exact ⟨Denumerable.eqv γ⟩

theorem not_same_cardinality_nat_real : ¬ Nonempty (ℕ ≃ ℝ) := by
  intro h
  rcases h with ⟨e⟩
  have hcount : Countable ℝ := e.symm.injective.countable
  exact Cardinal.not_countable_real (Set.countable_univ_iff.mpr hcount)

end Cardinality
end Exam3
end FoundationsOfMathematics
end OpenGaussLean4
