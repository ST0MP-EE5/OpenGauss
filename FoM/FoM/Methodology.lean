/-!
# Mathematical Problem-Solving Methodology

This module makes the Pólya/Tao problem-solving process available inside a Lean
project.  It is not specific to Foundations of Mathematics; FoM simply imports
the same broad workflow for its current learning path.
-/

namespace OpenGaussMethodology

/-- Broad shape of a mathematical task. -/
inductive ProblemKind where
  | showEvaluate
  | findObject
  | existence
  | conceptStudy
  | proofRepair
  | researchExploration
  | unknown
  deriving Repr, DecidableEq

/-- The four Pólya control phases. -/
inductive PolyaPhase where
  | understand
  | devisePlan
  | carryOut
  | lookBack
  deriving Repr, DecidableEq

/-- Tao-style tactical transformations used to make a problem workable. -/
inductive TaoMove where
  | classifyProblem
  | separateDataObjective
  | chooseNotation
  | writeKnownFacts
  | drawOrInstantiate
  | specialCase
  | degenerateCase
  | reformulate
  | analogousProblem
  | generalize
  | removeHypothesis
  | swapDataObjective
  | proveMiniResult
  | normalize
  | splitEquality
  | epsilonRoom
  | approximateBySimpleObjects
  | exceptionalSet
  | generatorClosure
  | counterexampleSearch
  | partialProgress
  | toolAudit
  | skepticalCheck
  | elegantCleanup
  deriving Repr, DecidableEq

/-- A named set of prompts that an assistant should silently apply. -/
structure PromptBlock where
  name : String
  prompts : List String
  deriving Repr

/-- Source-grounded Pólya prompts for the first pass over a mathematical problem. -/
def polyaUnderstand : PromptBlock :=
  { name := "understand"
    prompts :=
      [ "Identify the unknown or target statement.",
        "List the data, hypotheses, and conditions.",
        "Check whether the condition appears sufficient, redundant, or contradictory.",
        "Introduce suitable notation only after the principal objects are clear.",
        "Draw a figure, instantiate an example, or name concrete witnesses when helpful." ] }

/-- Source-grounded Pólya prompts for finding a plan. -/
def polyaPlan : PromptBlock :=
  { name := "devise_plan"
    prompts :=
      [ "Look for a related solved problem or theorem with the same or similar target.",
        "Restate the problem by unfolding definitions or changing the proof form.",
        "Try a special, degenerate, analogous, or more accessible related problem.",
        "Consider an auxiliary object or intermediate lemma if it connects data to target.",
        "Return to the original goal and check whether all relevant hypotheses are used." ] }

/-- Source-grounded Pólya prompts for executing a plan. -/
def polyaCarryOut : PromptBlock :=
  { name := "carry_out"
    prompts :=
      [ "Keep the current plan visible while writing the Lean proof.",
        "Check each proof step with Lean rather than relying on plausibility.",
        "If the plan changes, restate the new tactical goal before continuing." ] }

/-- Source-grounded Pólya prompts for looking back. -/
def polyaLookBack : PromptBlock :=
  { name := "look_back"
    prompts :=
      [ "Run the strongest available Lean check.",
        "Ask whether the result can be derived differently or more directly.",
        "Record which hypothesis, definition, or lemma did real work.",
        "Extract a reusable lemma when the same proof move is likely to recur." ] }

/-- Tao's operational problem-engineering loop. -/
def taoEngineering : PromptBlock :=
  { name := "tao_engineering"
    prompts :=
      [ "Classify the task as show/evaluate, find, existence, concept study, proof repair, or exploration.",
        "Separate understanding the data from understanding the objective.",
        "Choose notation that uses the structure and reduces avoidable asymmetry.",
        "Write down known facts in the selected notation before editing heavily.",
        "Modify the problem: special case, simplified version, consequence, reformulation, similar problem, or generalization.",
        "Use aggressive stress tests when stuck: remove data, negate the objective, swap data with target, or search for failed counterexamples.",
        "Create mini-results and normalizations that make the final proof shorter.",
        "Prefer a proof that is short, understandable, and reusable over brute-force proof search." ] }

/-- Tao blog-derived research and analysis habits. -/
def taoBlogHabits : PromptBlock :=
  { name := "tao_blog_habits"
    prompts :=
      [ "Split equalities into two inequalities or set equalities into two inclusions when useful.",
        "Give yourself epsilon-room or prove a slightly weaker quantitative statement first.",
        "Approximate rough objects by simpler ones while tracking the limiting justification.",
        "Ask dumb questions: remove hypotheses, test converses, strengthen conclusions, and locate where each hypothesis is used.",
        "Treat failed attempts as partial progress by identifying exactly which subcase or obstruction they handled.",
        "Audit tools by recording model examples, counterexamples, limits, and substitutes.",
        "Be skeptical when a hard problem suddenly becomes easy; isolate and recheck the decisive simplification.",
        "Prefer patient iteration over premature commitment to one large theory or one favorite method." ] }

/-- The default ordered methodology for Lean mathematical work. -/
def defaultWorkflow : List PromptBlock :=
  [ polyaUnderstand, polyaPlan, taoEngineering, taoBlogHabits, polyaCarryOut, polyaLookBack ]

/-- Moves that are broadly useful for introductory and intermediate mathematical topics. -/
def generalMoves : List TaoMove :=
  [ TaoMove.classifyProblem,
    TaoMove.separateDataObjective,
    TaoMove.chooseNotation,
    TaoMove.writeKnownFacts,
    TaoMove.drawOrInstantiate,
    TaoMove.reformulate,
    TaoMove.proveMiniResult,
    TaoMove.counterexampleSearch,
    TaoMove.partialProgress,
    TaoMove.toolAudit,
    TaoMove.skepticalCheck,
    TaoMove.elegantCleanup ]

/-- Minimal invariant Codex should maintain while assisting with Lean mathematics. -/
def codexInvariant : String :=
  "Before editing a Lean proof, silently run understand -> plan -> engineer -> check -> look_back."

end OpenGaussMethodology
