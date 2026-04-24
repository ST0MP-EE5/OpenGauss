import Mathlib.Data.Set.Basic

/-!
# Bounds

Basic order lemmas for moving upper and lower bounds through subset
relationships.
-/

namespace OpenGaussLean4
namespace Order

variable {α : Type*} [Preorder α]

theorem upper_bound_mono {s t : Set α} {b : α}
    (hst : s ⊆ t)
    (hub : ∀ x, x ∈ t -> x ≤ b) : ∀ x, x ∈ s -> x ≤ b := by
  intro x hxs
  exact hub x (hst hxs)

theorem lower_bound_mono {s t : Set α} {a : α}
    (hst : s ⊆ t)
    (hlb : ∀ x, x ∈ t -> a ≤ x) : ∀ x, x ∈ s -> a ≤ x := by
  intro x hxs
  exact hlb x (hst hxs)

theorem bounded_between_mono {s t : Set α} {a b : α}
    (hst : s ⊆ t)
    (hlb : ∀ x, x ∈ t -> a ≤ x)
    (hub : ∀ x, x ∈ t -> x ≤ b) :
    ∀ x, x ∈ s -> a ≤ x ∧ x ≤ b := by
  intro x hxs
  exact ⟨hlb x (hst hxs), hub x (hst hxs)⟩

end Order
end OpenGaussLean4
