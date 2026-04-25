/-!
# Foundations of Mathematics

Lean workspace for formalizing material from the Foundations of Mathematics source set,
starting with `Book Of Proofs.pdf`.
-/

namespace FoM

/-- A tiny starter theorem so the project has a compiling Lean module. -/
theorem modus_ponens {P Q : Prop} (hP : P) (hPQ : P → Q) : Q :=
  hPQ hP

/-- Contrapositive, a common early proof technique. -/
theorem contrapositive {P Q : Prop} (h : P → Q) : ¬ Q → ¬ P := by
  intro hnQ hP
  exact hnQ (h hP)

end FoM
