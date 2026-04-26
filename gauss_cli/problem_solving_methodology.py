"""Project-native problem-solving methodology for Lean mathematical work."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gauss_cli.project import ProjectManifestError, ProjectNotFoundError, discover_gauss_project

SOURCE_BASIS = (
    {
        "author": "George Polya",
        "title": "How to Solve It",
        "local_path_hint": "Sources/ProblemSolving/How to Solve It*.pdf",
        "analysis": (
            "Four-phase control loop: understand the problem, devise a plan, "
            "carry out the plan, and look back. The OCR-visible source emphasizes "
            "unknown/data/condition, suitable notation, figures, related problems, "
            "auxiliary elements, checking each step, and reusing the result or method."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Solving Mathematical Problems",
        "local_path_hint": "Sources/ProblemSolving/Solving mathematical problems*.pdf",
        "analysis": (
            "Operational problem engineering: classify the task, understand data "
            "and objective separately, select efficient notation, write known facts, "
            "modify the problem through special cases/reformulations/generalizations, "
            "prove mini-results, and prefer concise understandable solutions."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "245A: Problem solving strategies",
        "url": "https://terrytao.wordpress.com/2010/10/21/245a-problem-solving-strategies/",
        "analysis": (
            "Analysis-oriented tactics: split equalities into inequalities or inclusions, "
            "use epsilon-room, approximate rough objects by simpler ones, discard exceptional "
            "sets when legitimate, abstract irrelevant structure, and prove properties from "
            "generators or preservation principles."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Ask yourself dumb questions - and answer them",
        "url": "https://terrytao.wordpress.com/career-advice/ask-yourself-dumb-questions-and-answer-them/",
        "analysis": (
            "Active questioning habit: test whether hypotheses are necessary, whether converses "
            "hold, what happens in classical or degenerate cases, and where a proof uses each assumption."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Learn and relearn your field",
        "url": "https://terrytao.wordpress.com/career-advice/learn-and-relearn-your-field/",
        "analysis": (
            "Tool and lemma mastery: seek alternate proofs, model examples, weaker versions, "
            "generalizations, analogues, and the boundary between problems a lemma can and cannot solve."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "On the importance of partial progress",
        "url": "https://terrytao.wordpress.com/career-advice/on-the-importance-of-partial-progress/",
        "analysis": (
            "Treat failed attempts as reusable partial progress by recording which subcases, "
            "regions, or obstructions the attempt handled and what remains unresolved."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Learn the limitations of your tools",
        "url": "https://terrytao.wordpress.com/career-advice/learn-the-limitations-of-your-tools/",
        "analysis": (
            "Audit each method by knowing model successes, counterexamples, substitutes, "
            "and warning signs that a tool is being used as a black box."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Be sceptical of your own work",
        "url": "https://terrytao.wordpress.com/career-advice/be-sceptical-of-your-own-work/",
        "analysis": (
            "Stress-test unexpectedly easy proofs by looking for overpowered methods, hidden "
            "division/sign errors, missing hypotheses, and arguments that also prove false stronger claims."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Amplification, arbitrage, and the tensor power trick",
        "url": "https://terrytao.wordpress.com/2007/09/05/amplification-arbitrage-and-the-tensor-power-trick/",
        "analysis": (
            "Research-level strengthening method: take many copies of a problem, exploit product "
            "or multiplicative structure, then descend back to one copy to remove losses or sharpen bounds."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "There's more to mathematics than rigour and proofs",
        "url": "https://terrytao.wordpress.com/career-advice/theres-more-to-mathematics-than-rigour-and-proofs/",
        "analysis": (
            "Balance intuition and formal proof: use heuristic models to generate candidate arguments, "
            "then let rigorous verification destroy bad intuition and preserve useful structure."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Continually aim just beyond your current range",
        "url": "https://terrytao.wordpress.com/career-advice/continually-aim-just-beyond-your-current-range/",
        "analysis": (
            "Training heuristic: choose tasks just outside the current toolbox, disable all but one "
            "difficulty when needed, and use restricted reproofs of known results to extend range."
        ),
    },
    {
        "author": "Terence Tao",
        "title": "Mathematical exploration and discovery at scale",
        "url": "https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/",
        "analysis": (
            "Computational exploration loop: experiment, detect patterns, form conjectures, verify, "
            "and separate machine-assisted search from proof and counterexample validation."
        ),
    },
)

POLYA_PHASES = (
    {
        "phase": "understand",
        "assistant_obligation": "Identify target, data, hypotheses, conditions, notation, and examples before editing.",
        "checks": (
            "unknown_or_target",
            "data_and_hypotheses",
            "condition_sanity",
            "notation",
            "example_or_diagram",
        ),
    },
    {
        "phase": "devise_plan",
        "assistant_obligation": "Connect data to target through related problems, definitions, auxiliary objects, or subgoals.",
        "checks": (
            "related_theorem_or_problem",
            "definition_unfolding",
            "special_or_simplified_case",
            "auxiliary_lemma",
            "hypothesis_usage",
        ),
    },
    {
        "phase": "carry_out",
        "assistant_obligation": "Write the Lean proof in small verified steps and keep the plan aligned with diagnostics.",
        "checks": ("local_goal_state", "lean_diagnostics", "file_or_target_check"),
    },
    {
        "phase": "look_back",
        "assistant_obligation": "Verify, simplify, extract reusable lemmas, and explain the proof pattern compactly.",
        "checks": (
            "strongest_verification",
            "alternate_or_shorter_route",
            "key_hypothesis",
            "reusable_lemma_candidate",
        ),
    },
)

TAO_MOVES = (
    "classify as show/evaluate, find, existence, concept study, or proof repair",
    "separate data from objective",
    "choose structure-sensitive notation",
    "write known facts before proof search",
    "try special or degenerate cases",
    "reformulate by definitions, contradiction, contrapositive, substitution, or equivalent goals",
    "compare with analogous problems",
    "generalize or simplify to expose the mechanism",
    "remove data, swap data with objective, or negate target as a stress test",
    "prove mini-results and normalize the situation",
    "split equalities into inequalities or mutual inclusions",
    "give yourself epsilon-room for limiting or approximate arguments",
    "approximate rough objects by simpler ones and justify the limiting step",
    "use a priori estimates before construction",
    "flip by complement, reflection, negation, or duality",
    "move to product spaces and reorganize sums, integrals, averages, or counts",
    "expand definitions when hypotheses and goal are only one or two layers apart",
    "choose parameters late and in a non-circular dependency order",
    "drop inessential constants when only qualitative behavior matters",
    "balance free parameters by testing scales",
    "pass to subsequences, limsup/liminf, or pigeonhole structure",
    "spend symmetries strategically through normalization or relabeling",
    "linearize nonlinear problems around a base object",
    "use amplification or tensor-power tricks when product structure can remove losses",
    "prove closure from generators when a class is built by operations",
    "treat failed attempts as partial progress by recording what they did solve",
    "audit tools through model examples, counterexamples, limits, and substitutes",
    "stress-test easy proofs by checking whether the method proves a false stronger result",
    "use computation or AI for exploration, but keep proof verification separate",
    "prefer short, understandable, reusable proofs after verification",
)

METHODOLOGY_MODES: dict[str, dict[str, Any]] = {
    "overview": {
        "title": "Unified Pólya/Tao workflow",
        "purpose": "Select a compact general strategy before doing Lean work.",
        "use_when": "The task is mathematical but no specific obstruction is visible yet.",
        "actions": (
            "classify the task as prove, compute, find, existence, concept study, or repair",
            "separate data, hypotheses, conditions, unknowns, and objective",
            "choose notation or representation that absorbs structure",
            "probe examples and boundary cases before editing",
            "reduce to subgoals or mini-lemmas",
            "verify in Lean and look back for a reusable pattern",
        ),
        "deliverable": "A short plan with the current phase, likely moves, and first Lean check.",
    },
    "toy_models": {
        "title": "Toy model generator",
        "purpose": "Create simpler models that preserve the real difficulty.",
        "use_when": "The theorem is too abstract, has many hypotheses, or the mechanism is unclear.",
        "actions": (
            "try the smallest nontrivial finite example",
            "try low-dimensional, one-variable, or one-generator cases",
            "try symmetric, normalized, or extremal cases",
            "remove one complication at a time while keeping at least one genuine difficulty",
            "mark which simplification became trivial and which preserved the obstruction",
        ),
        "deliverable": "A list of toy models, what each preserves, and which one should guide the proof.",
    },
    "counterexample_probe": {
        "title": "Counterexample and boundary probe",
        "purpose": "Try to falsify the statement to discover the proof mechanism.",
        "use_when": "A proof path is unclear, a hypothesis looks suspicious, or the goal may be false.",
        "actions": (
            "remove or weaken one hypothesis at a time",
            "test degenerate, boundary, and smallest nontrivial cases",
            "try the converse, stronger conclusion, and negated target",
            "construct a failed counterexample and record exactly where it fails",
            "turn the failure point into a candidate lemma or missing hypothesis",
        ),
        "deliverable": "A boundary table: variant, expected status, obstruction, and proof clue.",
    },
    "hypothesis_audit": {
        "title": "Hypothesis audit",
        "purpose": "Track how each assumption supports the proof.",
        "use_when": "The proof has unused assumptions, too many assumptions, or a statement needs explanation.",
        "actions": (
            "list every hypothesis and the exact Lean object it provides",
            "predict where each hypothesis should be used",
            "test whether the conclusion survives without each hypothesis",
            "check converses and weaker versions",
            "identify hypotheses that only support notation or typeclass search",
        ),
        "deliverable": "A hypothesis-use map plus any suspected redundant or essential assumptions.",
    },
    "parameter_plan": {
        "title": "Parameter and epsilon planner",
        "purpose": "Manage epsilon, delta, N, R, eta, constants, and free parameters without circular choices.",
        "use_when": "The proof involves limits, approximation, convergence, compactness, estimates, or optimization.",
        "actions": (
            "introduce slack before exact targets when legitimate",
            "split tolerances into named pieces",
            "derive all parameter constraints before choosing values",
            "choose parameters in dependency order from outermost to innermost",
            "drop inessential constants and balance competing error terms by scale",
        ),
        "deliverable": "A non-circular parameter order and the inequalities each choice must satisfy.",
    },
    "proof_strategy": {
        "title": "Proof strategy selector",
        "purpose": "Choose a proof route before editing Lean.",
        "use_when": "The theorem is ready to prove but the first tactic or lemma path is unclear.",
        "actions": (
            "compare direct proof, contradiction, contrapositive, induction, extensionality, and construction",
            "split equalities into two inequalities or set equalities into two inclusions",
            "expand definitions only when the goal is close to the hypotheses",
            "look for a priori estimates before construction",
            "try complement, duality, product-space reorganization, symmetry normalization, or linearization",
        ),
        "deliverable": "A ranked proof route with required lemmas, Lean tools to query, and first edit.",
    },
    "attempt_review": {
        "title": "Failed-attempt review",
        "purpose": "Convert failed work into partial progress rather than discarding it.",
        "use_when": "A Lean proof, informal proof, or automation run failed.",
        "actions": (
            "locate the first real failure, not just the first diagnostic",
            "record which subgoals, cases, or estimates the attempt solved",
            "identify whether the failure is representation, missing lemma, false statement, or tool limitation",
            "decide whether to repair, restart from a toy model, or change formulation",
            "preserve useful lemmas and delete accidental complexity",
        ),
        "deliverable": "A failure classification, salvaged facts, missing lemma candidates, and next attempt plan.",
    },
    "look_back": {
        "title": "Look-back and reusable-lemma extraction",
        "purpose": "Turn a finished proof into learning and reusable project structure.",
        "use_when": "A proof compiles or an explanation seems complete.",
        "actions": (
            "verify the strongest cheap check available",
            "try to shorten or simplify the argument without hiding the mechanism",
            "identify where each important hypothesis was used",
            "ask whether the method proves a useful generalization or weaker reusable lemma",
            "extract stable lemmas only when they remove real future complexity",
        ),
        "deliverable": "A concise proof explanation, reusable pattern, and lemma extraction decision.",
    },
}

MODE_ALIASES = {
    "": "overview",
    "default": "overview",
    "counterexample": "counterexample_probe",
    "counterexamples": "counterexample_probe",
    "boundary": "counterexample_probe",
    "hypotheses": "hypothesis_audit",
    "hypothesis": "hypothesis_audit",
    "epsilon": "parameter_plan",
    "parameters": "parameter_plan",
    "strategy": "proof_strategy",
    "proof": "proof_strategy",
    "review": "attempt_review",
    "failed_attempt": "attempt_review",
    "retrospective": "look_back",
}

TOPIC_DEFAULTS = {
    "logic": ("unfold connectives", "test converses", "use truth-functional examples"),
    "sets": ("use extensionality", "split equalities into mutual inclusions", "track element witnesses"),
    "functions": ("unfold injective/surjective", "track domains and codomains", "compose witnesses explicitly"),
    "relations": ("unfold reflexive/symmetric/transitive", "test counterexamples on small finite types"),
    "induction": ("identify the predicate", "check base case", "state the induction hypothesis precisely"),
    "cardinality": ("separate injection/surjection/bijection", "build explicit maps", "check inverse laws"),
    "number theory": ("try modular reductions", "test small residues", "look for divisibility obstructions"),
    "algebra": ("use structure-preserving maps", "test generators", "look for normal forms"),
    "linear algebra": ("choose a basis", "separate span from independence", "track kernels and images"),
    "geometry": ("draw a faithful diagram", "normalize by symmetry", "test degenerate configurations"),
    "combinatorics": ("try small finite cases", "look for extremal examples", "use pigeonhole or double counting"),
    "probability": ("condition on useful information", "test independence assumptions", "use expectation as averaging"),
    "calculus": ("normalize variables", "test limiting cases", "separate local from global behavior"),
    "analysis": ("use epsilon-room", "approximate by simple objects", "track exceptional sets"),
    "topology": ("unfold open/closed/compact", "use neighborhood tests", "try counterexamples"),
}


def normalize_methodology_mode(mode: str | None) -> str:
    """Return a supported methodology mode."""
    raw = str(mode or "overview").strip().lower().replace("-", "_").replace(" ", "_")
    canonical = MODE_ALIASES.get(raw, raw)
    if canonical not in METHODOLOGY_MODES:
        return "overview"
    return canonical


def _methodology_module_candidates(project_root: Path, lean_root: Path | None = None) -> tuple[Path, ...]:
    root = lean_root or project_root
    return (
        root / "OpenGaussLean4" / "ProblemSolvingMethodology.lean",
        root / "FoM" / "Methodology.lean",
        root / "Methodology.lean",
    )


def find_methodology_module(project_root: Path, lean_root: Path | None = None) -> Path | None:
    """Return the project methodology Lean module, if one is present."""
    for candidate in _methodology_module_candidates(project_root, lean_root):
        if candidate.is_file():
            return candidate
    return None


def project_has_methodology(project_root: Path, lean_root: Path | None = None) -> bool:
    """Return whether a project carries a problem-solving methodology Lean module."""
    return find_methodology_module(project_root, lean_root) is not None


def methodology_for_project(
    *,
    cwd: str | Path | None = None,
    topic: str | None = None,
    problem_kind: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Return structured methodology guidance for the active project."""
    active = Path(cwd or Path.cwd()).expanduser().resolve()
    try:
        project = discover_gauss_project(active)
        project_found = True
        project_root = project.root
        lean_root = project.lean_root
        project_payload = {
            "name": project.name,
            "root": str(project.root),
            "lean_root": str(project.lean_root),
        }
    except (ProjectNotFoundError, ProjectManifestError):
        project_found = False
        project_root = active
        lean_root = active
        project_payload = {"name": "", "root": str(active), "lean_root": str(active)}

    normalized_topic = str(topic or "").strip().lower()
    normalized_mode = normalize_methodology_mode(mode)
    topic_moves = TOPIC_DEFAULTS.get(normalized_topic, ())
    module_path = find_methodology_module(project_root, lean_root)
    enabled = module_path is not None

    return {
        "success": True,
        "project_found": project_found,
        "project": project_payload,
        "enabled": enabled,
        "methodology_module": str(module_path or ""),
        "methodology_module_exists": module_path is not None and module_path.is_file(),
        "source_basis": list(SOURCE_BASIS),
        "problem_kind": str(problem_kind or "unknown").strip().lower() or "unknown",
        "topic": normalized_topic,
        "topic_moves": list(topic_moves),
        "mode": normalized_mode,
        "available_modes": sorted(METHODOLOGY_MODES),
        "selected_mode": METHODOLOGY_MODES[normalized_mode],
        "polya_phases": list(POLYA_PHASES),
        "tao_moves": list(TAO_MOVES),
        "codex_required_behavior": [
            "Apply the methodology silently; do not make the user memorize the checklist.",
            "For Lean mathematical edits, consult this methodology before choosing proof tactics or lemmas.",
            "Prefer Lean context tools before editing: project status, proof context, goals, diagnostics, symbols.",
            "After editing, run the strongest cheap verification and summarize only the applied method and result.",
        ],
    }


def problem_probe_for_project(
    *,
    statement: str | None = None,
    cwd: str | Path | None = None,
    topic: str | None = None,
    problem_kind: str | None = None,
    mode: str | None = None,
    attempt: str | None = None,
) -> dict[str, Any]:
    """Return an actionable probe plan for a mathematical statement or failed attempt."""
    payload = methodology_for_project(cwd=cwd, topic=topic, problem_kind=problem_kind, mode=mode)
    selected_mode = payload["selected_mode"]
    active_statement = str(statement or "").strip()
    active_attempt = str(attempt or "").strip()
    normalized_mode = payload["mode"]

    return {
        "success": True,
        "operation": "problem_probe",
        "enabled": payload["enabled"],
        "project_found": payload["project_found"],
        "project": payload["project"],
        "methodology_module": payload["methodology_module"],
        "statement": active_statement,
        "attempt_supplied": bool(active_attempt),
        "topic": payload["topic"],
        "problem_kind": payload["problem_kind"],
        "mode": normalized_mode,
        "mode_guidance": selected_mode,
        "topic_moves": payload["topic_moves"],
        "probe_plan": [
            "Parse the statement into data, hypotheses, objective, and hidden conditions.",
            *selected_mode["actions"],
            "Use Lean context tools to test the plan before editing source files.",
            "After any edit, verify with check/build/sorry report and revise the probe result.",
        ],
        "lean_tool_sequence": [
            "gauss_lean_project_status",
            "gauss_lean_proof_context or gauss_lean_lsp_goals when a file location is known",
            "gauss_lean_lsp_symbols or gauss_search_files for relevant lemmas",
            "gauss_lean_check_file or gauss_lean_lake_build after edits",
        ],
        "deliverable": selected_mode["deliverable"],
        "codex_required_behavior": [
            "Use this probe to choose the next mathematical move; do not present it as a rigid checklist.",
            "If the statement is missing, ask for the theorem/goal or inspect the active Lean context.",
            "If an attempt is supplied, classify the first structural failure before proposing edits.",
            "Keep verification separate from exploration; Lean or Comparator remains the authority.",
        ],
    }


def compact_methodology_prompt(cwd: str | Path | None = None) -> str:
    """Return concise prompt text suitable for Codex/system instructions."""
    payload = methodology_for_project(cwd=cwd)
    if not payload["enabled"]:
        return ""
    phase_names = " -> ".join(phase["phase"] for phase in payload["polya_phases"])
    return (
        "Problem-solving methodology module detected. For Lean mathematical work, silently apply "
        f"{phase_names}. Use Tao-style problem engineering: classify the task, "
        "separate data from objective, choose notation, try special/reformulated/generalized "
        "versions, make mini-lemmas, preserve partial progress, audit tools, verify in Lean, "
        "then look back for reusable patterns. "
        "Call `gauss_problem_solving_methodology` when the topic, proof strategy, or next move is unclear, "
        "and `gauss_problem_probe` for toy models, counterexample probes, hypothesis audits, parameter plans, "
        "proof strategy selection, failed-attempt review, or look-back extraction."
    )
