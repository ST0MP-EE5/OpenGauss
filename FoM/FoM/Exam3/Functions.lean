import Mathlib
import FoM.Methodology

/-!
# Exam 3 Topic: Functions

This file matches the exam outline items on functions, injective/surjective
maps, composition, inverses, images, and preimages.
-/

open Function Set

namespace FoM.Exam3

section BasicExamples

theorem succ_injective : Injective (fun n : ℕ => n + 1) := by
  intro a b h
  exact Nat.add_right_cancel h

theorem comp_injective {α β γ : Type*} {f : β → γ} {g : α → β} (hf : Injective f)
    (hg : Injective g) : Injective (f ∘ g) := by
  intro a b h
  exact hg (hf h)

end BasicExamples

section Inverses

def swapPair {α β : Type*} : α × β → β × α := fun p => (p.2, p.1)

def swapPairBack {α β : Type*} : β × α → α × β := fun p => (p.2, p.1)

theorem swapPair_leftInverse {α β : Type*} :
    LeftInverse (swapPairBack (α := α) (β := β)) (swapPair (α := α) (β := β)) := by
  intro p
  cases p
  rfl

theorem swapPair_rightInverse {α β : Type*} :
    RightInverse (swapPairBack (α := α) (β := β)) (swapPair (α := α) (β := β)) := by
  intro p
  cases p
  rfl

theorem swapPair_bijective {α β : Type*} : Bijective (swapPair (α := α) (β := β)) := by
  exact ⟨swapPair_leftInverse.injective, swapPair_rightInverse.surjective⟩

end Inverses

section ImagesAndPreimages

theorem image_mono {α β : Type*} {f : α → β} {s t : Set α} (h : s ⊆ t) :
    f '' s ⊆ f '' t := by
  intro y hy
  rcases hy with ⟨x, hx, rfl⟩
  exact ⟨x, h hx, rfl⟩

theorem preimage_union {α β : Type*} (f : α → β) (u v : Set β) :
    f ⁻¹' (u ∪ v) = f ⁻¹' u ∪ f ⁻¹' v := by
  ext x
  rfl

theorem preimage_inter {α β : Type*} (f : α → β) (u v : Set β) :
    f ⁻¹' (u ∩ v) = f ⁻¹' u ∩ f ⁻¹' v := by
  ext x
  rfl

end ImagesAndPreimages

/-!
## Practice prompts

Use the methodology each time:

- Understand: what is the domain, codomain, and target property?
- Plan: should you unfold `Injective`, `Surjective`, `Bijective`, `image`, or `preimage`?
- Carry out: build witnesses explicitly when proving surjectivity.
- Look back: ask whether the proof reused only definitions or needed a deeper lemma.

Suggested next exercises:

1. Show that if `g ∘ f` is injective, then `f` is injective.
2. Show that if `g ∘ f` is surjective, then `g` is surjective.
3. Prove `f ⁻¹' (u \\ v) = f ⁻¹' u \\ f ⁻¹' v`.
-/

end FoM.Exam3
