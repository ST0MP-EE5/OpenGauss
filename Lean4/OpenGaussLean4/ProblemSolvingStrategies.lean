import Mathlib.Data.Set.Basic

/-!
# Reusable Proof Strategies

This module contains small cross-domain proof patterns used by the OpenGauss
Lean workspace. Domain-specific mathematics should live in the relevant domain
folder instead of accumulating here.
-/

namespace OpenGaussLean4
namespace ProblemSolvingStrategies

variable {α β : Type*}

theorem set_ext_of_mutual_membership {s t : Set α}
    (hst : ∀ ⦃x⦄, x ∈ s -> x ∈ t)
    (hts : ∀ ⦃x⦄, x ∈ t -> x ∈ s) : s = t := by
  ext x
  exact Iff.intro (fun hx => hst hx) (fun hx => hts hx)

theorem exists_unique_of_witness_and_all_equal {p : α -> Prop} {w : α}
    (hw : p w)
    (huniq : ∀ x, p x -> x = w) : ∃! x, p x := by
  refine ⟨w, hw, ?_⟩
  intro y hy
  exact huniq y hy

theorem image_eq_of_inverse_on {f : α -> β} {g : β -> α} {s : Set α} {t : Set β}
    (h_into : ∀ x, x ∈ s -> f x ∈ t)
    (h_back : ∀ y, y ∈ t -> g y ∈ s)
    (h_right : ∀ y, y ∈ t -> f (g y) = y) : f '' s = t := by
  ext y
  constructor
  · rintro ⟨x, hxs, rfl⟩
    exact h_into x hxs
  · intro hyt
    exact ⟨g y, h_back y hyt, h_right y hyt⟩

end ProblemSolvingStrategies
end OpenGaussLean4
