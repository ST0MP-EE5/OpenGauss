import Mathlib.Data.Set.Function
import Mathlib.Tactic

/-!
# Exam 3 Functions

This module mirrors the exam topics on functions:

- function types as domain/codomain data;
- injective, surjective, and bijective functions;
- composition;
- inverse functions;
- image and preimage;
- set-theoretic proofs about image and preimage.
-/

namespace OpenGaussLean4
namespace FoundationsOfMathematics
namespace Exam3
namespace Functions

open Function Set

variable {α β γ : Type*}

/-- In Lean, the type of `f` already records its domain and codomain. -/
theorem domain_and_codomain_are_in_the_type (f : α → β) : MapsTo f univ univ := by
  intro x hx
  simp

theorem natSucc_injective : Injective Nat.succ := by
  intro m n h
  exact Nat.succ.inj h

theorem natSucc_not_surjective : ¬ Surjective Nat.succ := by
  intro h
  rcases h 0 with ⟨n, hn⟩
  exact Nat.succ_ne_zero n hn

theorem boolNot_bijective : Bijective (fun b : Bool ↦ !b) := by
  constructor
  · intro b₁ b₂ h
    simpa using congrArg not h
  · intro b
    exact ⟨!b, by simp⟩

theorem comp_injective {f : β → γ} {g : α → β}
    (hf : Injective f) (hg : Injective g) : Injective (f ∘ g) :=
  hf.comp hg

theorem comp_surjective {f : β → γ} {g : α → β}
    (hf : Surjective f) (hg : Surjective g) : Surjective (f ∘ g) :=
  hf.comp hg

def addOne : ℤ → ℤ := fun z ↦ z + 1

def subOne : ℤ → ℤ := fun z ↦ z - 1

theorem subOne_leftInverse : LeftInverse subOne addOne := by
  intro z
  simp [addOne, subOne]

theorem subOne_rightInverse : RightInverse subOne addOne := by
  intro z
  simp [addOne, subOne]

theorem addOne_bijective : Bijective addOne :=
  ⟨subOne_leftInverse.injective, subOne_rightInverse.surjective⟩

theorem image_union (f : α → β) (s t : Set α) : f '' (s ∪ t) = f '' s ∪ f '' t := by
  ext y
  constructor
  · rintro ⟨x, hx | hx, rfl⟩
    · exact Or.inl ⟨x, hx, rfl⟩
    · exact Or.inr ⟨x, hx, rfl⟩
  · rintro (⟨x, hx, rfl⟩ | ⟨x, hx, rfl⟩)
    · exact ⟨x, Or.inl hx, rfl⟩
    · exact ⟨x, Or.inr hx, rfl⟩

theorem preimage_inter (f : α → β) (u v : Set β) :
    f ⁻¹' (u ∩ v) = f ⁻¹' u ∩ f ⁻¹' v := by
  ext x
  simp

theorem image_preimage_subset (f : α → β) (u : Set β) : f '' (f ⁻¹' u) ⊆ u := by
  intro y hy
  rcases hy with ⟨x, hx, rfl⟩
  exact hx

theorem preimage_image_eq_of_injective {f : α → β} (hf : Injective f) (s : Set α) :
    f ⁻¹' (f '' s) = s :=
  hf.preimage_image s

theorem image_preimage_eq_of_surjective {f : α → β} (hf : Surjective f) (u : Set β) :
    f '' (f ⁻¹' u) = u :=
  hf.image_preimage u

theorem image_monotone {f : α → β} {s t : Set α} (hst : s ⊆ t) : f '' s ⊆ f '' t := by
  intro y hy
  rcases hy with ⟨x, hxs, rfl⟩
  exact ⟨x, hst hxs, rfl⟩

end Functions
end Exam3
end FoundationsOfMathematics
end OpenGaussLean4
