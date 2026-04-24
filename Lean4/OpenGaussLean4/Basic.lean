import Mathlib.Data.Nat.Basic
import Mathlib.Data.Set.Basic

/-!
# OpenGauss Lean4 Core

Foundational declarations and checks shared by the local OpenGauss Lean
workspace.
-/

namespace OpenGaussLean4

def ClosedUnder {α : Type*} (op : α -> α -> α) (s : Set α) : Prop :=
  ∀ ⦃x y⦄, x ∈ s -> y ∈ s -> op x y ∈ s

theorem ClosedUnder.apply {α : Type*} {op : α -> α -> α} {s : Set α}
    (h : ClosedUnder op s) {x y : α} (hx : x ∈ s) (hy : y ∈ s) :
    op x y ∈ s :=
  h hx hy

theorem nat_two_add_two : (2 : Nat) + 2 = 4 := by
  decide

end OpenGaussLean4
