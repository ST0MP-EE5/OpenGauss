/-!
# Mathematical Problem-Solving Methodology

Project-native Pólya/Tao workflow objects for OpenGauss Lean work.
-/

namespace OpenGaussLean4
namespace ProblemSolvingMethodology

inductive ProblemKind where
  | showEvaluate
  | findObject
  | existence
  | conceptStudy
  | proofRepair
  | researchExploration
  | unknown
  deriving Repr, DecidableEq

inductive PolyaPhase where
  | understand
  | devisePlan
  | carryOut
  | lookBack
  deriving Repr, DecidableEq

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

structure PromptBlock where
  name : String
  prompts : List String
  deriving Repr

def polyaUnderstand : PromptBlock :=
  { name := "understand"
    prompts :=
      [ "Identify the unknown or target statement.",
        "List the data, hypotheses, and conditions.",
        "Check whether the condition appears sufficient, redundant, or contradictory.",
        "Introduce suitable notation only after the principal objects are clear.",
        "Draw a figure, instantiate an example, or name concrete witnesses when helpful." ] }

def polyaPlan : PromptBlock :=
  { name := "devise_plan"
    prompts :=
      [ "Look for a related solved problem or theorem with the same or similar target.",
        "Restate the problem by unfolding definitions or changing the proof form.",
        "Try a special, degenerate, analogous, or more accessible related problem.",
        "Consider an auxiliary object or intermediate lemma if it connects data to target.",
        "Return to the original goal and check whether all relevant hypotheses are used." ] }

def polyaCarryOut : PromptBlock :=
  { name := "carry_out"
    prompts :=
      [ "Keep the current plan visible while writing the Lean proof.",
        "Check each proof step with Lean rather than relying on plausibility.",
        "If the plan changes, restate the new tactical goal before continuing." ] }

def polyaLookBack : PromptBlock :=
  { name := "look_back"
    prompts :=
      [ "Run the strongest available Lean check.",
        "Ask whether the result can be derived differently or more directly.",
        "Record which hypothesis, definition, or lemma did real work.",
        "Extract a reusable lemma when the same proof move is likely to recur." ] }

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

def defaultWorkflow : List PromptBlock :=
  [ polyaUnderstand, polyaPlan, taoEngineering, taoBlogHabits, polyaCarryOut, polyaLookBack ]

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

def codexInvariant : String :=
  "Before editing a Lean proof, silently run understand -> plan -> engineer -> check -> look_back."

end ProblemSolvingMethodology
end OpenGaussLean4
