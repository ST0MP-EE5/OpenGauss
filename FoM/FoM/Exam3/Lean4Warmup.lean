import Mathlib
import FoM.Methodology

/-!
# Lean 4 Warmup for Exam 3

This file is the on-ramp for learning Lean syntax before working through the
exam topics. Use the OpenGauss methodology silently while reading and extending
the proofs:

1. understand
2. devise_plan
3. carry_out
4. look_back
-/

namespace FoM.Exam3

section PropositionalLogic

/-!
`implication_chain` introduces several common pieces of Lean syntax.

Syntax guide:

- `theorem name ... : statement := by`
  means "define a theorem named `name` whose statement is after `:`, and whose
  proof script starts after `by`"
- `{P Q R : Prop}`
  means `P`, `Q`, and `R` are propositions; curly braces indicate these
  arguments are implicit, so Lean usually fills them in automatically
- `(hPQ : P → Q)`
  means `hPQ` is a hypothesis whose type is `P → Q`
- `→`
  means implication ("if ... then ...") or, more generally, a function type
- `:`
  means "has type"

Structure of the statement:

- hypotheses: `hPQ : P → Q` and `hQR : Q → R`
- target: `P → R`

In English: if `P` implies `Q` and `Q` implies `R`, then `P` implies `R`.
-/
theorem implication_chain {P Q R : Prop} (hPQ : P → Q) (hQR : Q → R) : P → R := by
  /- `intro hP`:
     because the goal is an implication `P → R`, we assume `P`.
     After this line:
     - `hP : P`
     - goal: `R` -/
  intro hP
  /- `exact ...` means "the following term exactly matches the goal".
     Here:
     - `hPQ hP` has type `Q`
     - `hQR (hPQ hP)` has type `R`
     so this finishes the proof. -/
  exact hQR (hPQ hP)

/-!
`and_commutes` is a first example of working with conjunction.

Syntax guide:

- `P ∧ Q`
  means "`P` and `Q`"
- `P ∧ Q → Q ∧ P`
  means "if `P and Q`, then `Q and P`"
- `h.1` and `h.2`
  mean "first component" and "second component" of a conjunction proof
- `⟨a, b⟩`
  is constructor notation for building a pair-like object; for conjunction,
  it builds a proof of `A ∧ B` from a proof of `A` and a proof of `B`

Structure of the proof:

1. assume a proof of `P ∧ Q`
2. extract its two pieces
3. rebuild them in the opposite order
-/
theorem and_commutes {P Q : Prop} : P ∧ Q → Q ∧ P := by
  /- Goal shape: implication.
     So we use `intro` to assume the input proof. -/
  intro h
  /- Now:
     - `h : P ∧ Q`
     - `h.1 : P`
     - `h.2 : Q`

     The goal is `Q ∧ P`, so we must provide:
     - first, a proof of `Q`
     - second, a proof of `P`

     `⟨h.2, h.1⟩` does exactly that. -/
  exact ⟨h.2, h.1⟩

/-!
`or_commutes` is a good first example of how to reason with a hypothesis of the
form `P ∨ Q`.

Methodology view:

- understand: the goal is `P ∨ Q → Q ∨ P`
- devise_plan:
  - since the goal is an implication, start with `intro`
  - since the new hypothesis is an `or`, split into cases
  - in each case, build the desired `or` using the matching constructor
- carry_out: handle the `P` case and the `Q` case separately
- look_back: remember the proof pattern "implication -> intro, disjunction
  hypothesis -> cases, disjunction goal -> `Or.inl` or `Or.inr`"
-/
theorem or_commutes {P Q : Prop} : P ∨ Q → Q ∨ P := by
  /- `intro h`:
     To prove an implication, assume the input.
     Now `h : P ∨ Q`, and the remaining goal is `Q ∨ P`. -/
  intro h
  /- `cases h with`:
     A proof of `P ∨ Q` comes in two possible shapes:
     - `Or.inl hP`, meaning we are in the `P` case
     - `Or.inr hQ`, meaning we are in the `Q` case -/
  cases h with
  | inl hP =>
      /- In this branch we know `hP : P`.
         The goal is `Q ∨ P`, so we satisfy it by proving the right side. -/
      exact Or.inr hP
  | inr hQ =>
      /- In this branch we know `hQ : Q`.
         The goal is `Q ∨ P`, so we satisfy it by proving the left side. -/
      exact Or.inl hQ

/-!
## Mini-lemmas, counterexamples, and toy models for propositional logic

OpenGauss methodology note:

- "look back" after a proof means we should ask what reusable lemma was hiding
  inside the proof.
- "test converses" and "use truth-functional examples" mean we should also
  build small counterexamples, not only successful theorems.

The next few declarations are deliberately small. Their purpose is to make the
basic logical shapes feel concrete.
-/

/-!
Reusable lemma: from `P ∧ Q`, we can recover the left side.

Syntax abstraction:

- theorem name: `and_left`
- implicit proposition variables: `{P Q : Prop}`
- input hypothesis: `(h : P ∧ Q)`
- target after `:`: `P`

Because `h` is a conjunction proof, `h.1` is its first component.
-/
theorem and_left {P Q : Prop} (h : P ∧ Q) : P := by
  exact h.1

/-!
Reusable lemma: from `P ∧ Q`, we can recover the right side.

Compare this with `and_left`:

- `and_left` uses `h.1`
- `and_right` uses `h.2`

This is a toy example of "same proof shape, different component".
-/
theorem and_right {P Q : Prop} (h : P ∧ Q) : Q := by
  exact h.2

/-!
Reusable lemma: if we already know `P`, then we can prove `P ∨ Q`.

Syntax abstraction:

- `P ∨ Q` is an "or" goal.
- To prove the left side of an "or" goal, use `Or.inl`.
- `Or.inl hP` says "the left side is true, witnessed by `hP`."
-/
theorem or_from_left {P Q : Prop} (hP : P) : P ∨ Q := by
  exact Or.inl hP

/-!
Reusable lemma: if we already know `Q`, then we can prove `P ∨ Q`.

This is the mirror image of `or_from_left`.

- `Or.inr hQ` says "the right side is true, witnessed by `hQ`."
-/
theorem or_from_right {P Q : Prop} (hQ : Q) : P ∨ Q := by
  exact Or.inr hQ

/-!
Toy model: instantiate `or_commutes` with concrete propositions.

Here:

- `P := True`
- `Q := False`

The theorem becomes:

`True ∨ False → False ∨ True`

This is a tiny truth-functional model of the abstract theorem.
-/
theorem toy_true_or_false_commutes : True ∨ False → False ∨ True := by
  exact or_commutes (P := True) (Q := False)

/-!
Counterexample: from `P ∨ Q`, we cannot generally conclude `P`.

The false proposed rule would be:

`∀ P Q : Prop, P ∨ Q → P`

To refute a universal claim, it is enough to give one model where it fails.
Choose:

- `P := False`
- `Q := True`

Then `P ∨ Q` is true because the right side is true, but `P` is false.
-/
theorem counterexample_or_does_not_give_left : ¬ (∀ P Q : Prop, P ∨ Q → P) := by
  /- To prove a negation `¬ A`, assume `A` and derive `False`.
     So `intro h` assumes the false universal rule. -/
  intro h
  /- Apply the alleged rule to the toy model `P = False`, `Q = True`.
     `Or.inr trivial` proves `False ∨ True`.
     The alleged rule would then produce `False`, which is impossible and
     therefore closes the proof. -/
  exact h False True (Or.inr trivial)

/-!
Counterexample: knowing only `P → R` is not enough to conclude `P → Q`.

This stress-tests a tempting but invalid "converse" of implication chaining.
Choose:

- `P := True`
- `Q := False`
- `R := True`

Then `P → R` is true, but `P → Q` is false.
-/
theorem counterexample_implication_converse :
    ¬ (∀ P Q R : Prop, (P → R) → P → Q) := by
  intro h
  /- The alleged universal rule turns:
     - a proof of `True → True`
     - a proof of `True`
     into a proof of `False`.

     That is the contradiction. -/
  exact h True False True (fun _ => trivial) trivial

end PropositionalLogic

section QuantifiersAndSets

/-!
`forall_transport` is a warmup for universal quantifiers.

Syntax guide:

- `{α : Type*}`
  says `α` is an arbitrary type
- `P Q : α → Prop`
  means `P` and `Q` are predicates on elements of `α`
- `∀ x, P x → Q x`
  means "for every `x`, if `P x` then `Q x`"
- `∀`
  is the universal quantifier, read as "for all" or "for every"
- `P x`
  means "the predicate `P` applied to the object `x`"

Structure of the statement:

- hypothesis: for every `x`, `P x` implies `Q x`
- target: for every `x`, `P x` implies `Q x`

So this theorem is intentionally simple: it teaches how Lean handles nested
`∀` and `→` using repeated `intro`.
-/
theorem forall_transport {α : Type*} {P Q : α → Prop} (h : ∀ x, P x → Q x) :
    ∀ x, P x → Q x := by
  /- `intro x hx` performs two introductions in sequence.

     First `intro x`:
     - because the goal begins with `∀ x, ...`
     - we choose an arbitrary `x`

     Then `intro hx`:
     - because the remaining goal is `P x → Q x`
     - we assume `hx : P x`

     After this line:
     - `x : α`
     - `hx : P x`
     - goal: `Q x` -/
  intro x hx
  /- The hypothesis `h` says this works for every `x`.
     So:
     - `h x : P x → Q x`
     - `h x hx : Q x`

     That exactly matches the goal. -/
  exact h x hx

/-!
`exists_nat_witness` is the first example of an existential proof.

Syntax guide:

- `∃ n : ℕ, n + 1 = 2`
  means "there exists a natural number `n` such that `n + 1 = 2`"
- `∃`
  is the existential quantifier, read as "there exists"
- `ℕ`
  is the type of natural numbers
- `refine`
  means "I want to build the proof in a structured way, leaving subgoals"
- `⟨1, ?_⟩`
  means "use witness `1`, and leave the proof that it works as a hole"
- `?_`
  is a placeholder for a remaining goal

Structure of the proof:

1. choose a witness
2. prove the witness satisfies the required property
-/
theorem exists_nat_witness : ∃ n : ℕ, n + 1 = 2 := by
  /- Since the goal is existential, we should ask:
     "what object should I provide?"

     Here `n = 1` is the natural guess, because `1 + 1 = 2`. -/
  refine ⟨1, ?_⟩
  /- After choosing the witness, the remaining goal is:
     `1 + 1 = 2`

     `norm_num` proves straightforward numerical facts by normalization. -/
  norm_num

/-!
`inter_subset_left` is a first set-theoretic proof.

Syntax guide:

- `Set α`
  means a set of elements of type `α`
- `s ∩ t`
  means the intersection of `s` and `t`
- `⊆`
  means subset
- `s ∩ t ⊆ s`
  means every element of `s ∩ t` is also an element of `s`

Important meaning:

- a subset statement `A ⊆ B` is really shorthand for
  `∀ x, x ∈ A → x ∈ B`

So Lean will naturally let us prove it by introducing:

1. an arbitrary element `x`
2. a hypothesis that `x ∈ s ∩ t`
3. the goal `x ∈ s`
-/
theorem inter_subset_left {α : Type*} (s t : Set α) : s ∩ t ⊆ s := by
  /- `intro x hx`:
     - `x` is an arbitrary element
     - `hx` is the assumption that `x ∈ s ∩ t`

     The new goal is to show `x ∈ s`. -/
  intro x hx
  /- Membership in an intersection has two parts:
     - `hx.1 : x ∈ s`
     - `hx.2 : x ∈ t`

     Since the goal is `x ∈ s`, `hx.1` is exactly what we need. -/
  exact hx.1

/-!
`union_with_empty` is about equality of sets.

Syntax guide:

- `s ∪ (∅ : Set α)`
  means the union of `s` with the empty set
- `∪`
  means union
- `∅`
  means the empty set
- `=`
  between sets means the two sets have exactly the same elements
- `ext x`
  is extensionality: to prove two sets are equal, prove they contain the same
  arbitrary element `x`
- `simp`
  simplifies expressions using built-in and imported lemmas

Mathematical idea:

To prove two sets are equal, prove:

- `x ∈ left ↔ x ∈ right`

for an arbitrary `x`.
-/
theorem union_with_empty {α : Type*} (s : Set α) : s ∪ (∅ : Set α) = s := by
  /- `ext x` changes the set-equality goal into a membership goal for an
     arbitrary `x`.

     Conceptually, it turns
       `s ∪ ∅ = s`
     into
       `x ∈ s ∪ ∅ ↔ x ∈ s`. -/
  ext x
  /- `simp` now unfolds the meaning of union membership and empty-set
     membership, then simplifies:

     - `x ∈ s ∪ ∅` becomes `x ∈ s ∨ x ∈ ∅`
     - `x ∈ ∅` is false
     - so this reduces to `x ∈ s`
  -/
  simp

/-!
## Mini-lemmas, counterexamples, and toy models for quantifiers and sets

The same methodology applies here:

- unfold the notation (`∀`, `∃`, `⊆`, `∈`, `∩`, `∪`)
- test a proposed statement on a small model
- keep reusable lemmas near the first proof where they become natural
-/

/-!
Counterexample: it is false that every predicate holds for every natural number.

The false proposed statement is:

`∀ P : ℕ → Prop, ∀ n, P n`

Syntax abstraction:

- `ℕ → Prop` means "predicate on natural numbers"
- `(fun _ => False)` is the predicate that is false for every input
- `h (fun _ => False) 0` asks the alleged theorem to prove `False` at `0`

This shows how a counterexample can be a tiny model: choose the always-false
predicate.
-/
theorem counterexample_not_every_predicate_holds :
    ¬ (∀ P : ℕ → Prop, ∀ n, P n) := by
  intro h
  exact h (fun _ => False) 0

/-!
Toy model for sets: two subsets of `Bool`.

`Bool` has exactly two values:

- `true`
- `false`

So it is a very small universe for testing set ideas.

Syntax abstraction:

- `def BoolTrueSet : Set Bool := ...`
  defines a set of Boolean values
- `{b | b = true}`
  is set-builder notation: the set of all `b` such that `b = true`
-/
def BoolTrueSet : Set Bool := {b | b = true}

def BoolFalseSet : Set Bool := {b | b = false}

/-!
Toy lemma: `true` belongs to the set of Booleans equal to `true`.

After unfolding `BoolTrueSet`, the goal is just `true = true`, so `rfl`
solves it.

Syntax abstraction:

- `∈` means membership
- `rfl` proves equality when both sides reduce to the same expression
-/
theorem true_mem_BoolTrueSet : true ∈ BoolTrueSet := by
  rfl

/-!
Toy lemma: the "true" set and the "false" set are disjoint.

Mathematical idea:

No Boolean value is both `true` and `false`.

Lean idea:

- use `ext b` to prove set equality by arbitrary membership
- use `cases b` because a Boolean has only two possible values
- use `simp` to evaluate the two concrete cases
-/
theorem BoolTrueSet_inter_BoolFalseSet_empty : BoolTrueSet ∩ BoolFalseSet = ∅ := by
  ext b
  cases b <;> simp [BoolTrueSet, BoolFalseSet]

/-!
Toy application of an earlier lemma.

Instead of reproving that `BoolTrueSet ∩ BoolFalseSet ⊆ BoolTrueSet`, we reuse
`inter_subset_left`.

This is the "look back" phase: after proving a general lemma, test it on a toy
model to see what it gives.
-/
theorem BoolTrueFalse_inter_subset_left : BoolTrueSet ∩ BoolFalseSet ⊆ BoolTrueSet := by
  exact inter_subset_left BoolTrueSet BoolFalseSet

end QuantifiersAndSets

section Functions

/-!
`pointwise_extensionality` is the key warmup for function equality.

Syntax guide:

- `f g : α → β`
  means `f` and `g` are functions from `α` to `β`
- `∀ x, f x = g x`
  means the two functions agree on every input `x`
- `f = g`
  means the functions themselves are equal
- `funext`
  stands for function extensionality: to prove two functions are equal, prove
  they give equal outputs on an arbitrary input

Mathematical idea:

Functions are equal when they have the same value at every input.
-/
theorem pointwise_extensionality {α β : Type*} {f g : α → β} (h : ∀ x, f x = g x) :
    f = g := by
  /- `funext x` says:
     "to prove `f = g`, let `x` be arbitrary and prove `f x = g x`."

     After this line, the goal is no longer function equality directly;
     it becomes pointwise equality at the input `x`. -/
  funext x
  /- The hypothesis `h` already says `f x = g x` for every `x`.
     So `h x` exactly matches the current goal. -/
  exact h x

/-!
## Mini-lemmas, counterexamples, and toy models for functions

The key idea for functions is:

- to prove equality of functions, prove equality at every input
- to disprove equality of functions, find one input where the outputs differ
-/

/-!
Toy model: two different-looking functions that are extensionally equal.

The functions are:

- `fun n : ℕ => n + 1`
- `fun n : ℕ => 1 + n`

They are written differently, but they give the same output for every natural
number because addition is commutative in this special case.

Syntax abstraction:

- `fun n : ℕ => ...` is anonymous function notation
- `funext n` reduces function equality to equality at arbitrary input `n`
- `Nat.add_comm n 1` proves `n + 1 = 1 + n`
-/
theorem toy_same_nat_function :
    (fun n : ℕ => n + 1) = (fun n : ℕ => 1 + n) := by
  funext n
  exact Nat.add_comm n 1

/-!
Counterexample: two functions are not equal if they differ at one input.

The functions are:

- `fun n : ℕ => n + 1`
- `fun n : ℕ => n + 2`

They differ at `n = 0`.

Methodology:

- understand: the target is a negated equality
- devise_plan: assume equality, evaluate both functions at a simple input
- carry_out: use `congrFun h 0` to apply function equality to input `0`
- look_back: one counterexample input is enough to disprove function equality

Syntax abstraction:

- `¬ A` means `A → False`
- `congrFun h 0` says equal functions have equal values at input `0`
- `norm_num at h0` evaluates the impossible arithmetic equality
-/
theorem counterexample_nat_functions_not_equal :
    ¬ ((fun n : ℕ => n + 1) = (fun n : ℕ => n + 2)) := by
  intro h
  have h0 : 0 + 1 = 0 + 2 := by
    exact congrFun h 0
  norm_num at h0

end Functions

/-!
## Practice prompts

Try these after reading the examples above.

1. Prove `(P ∨ Q) → (Q ∨ P)`.
2. Prove `s ∩ t = t ∩ s` for sets.
3. Prove `Function.Injective f` from a suitable left inverse hypothesis.
4. Rewrite a short proof once with `intro`/`exact` and once with `simpa`.
-/

end FoM.Exam3
