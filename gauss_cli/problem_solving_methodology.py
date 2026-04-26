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
    "prove closure from generators when a class is built by operations",
    "treat failed attempts as partial progress by recording what they did solve",
    "audit tools through model examples, counterexamples, limits, and substitutes",
    "stress-test easy proofs by checking whether the method proves a false stronger result",
    "prefer short, understandable, reusable proofs after verification",
)

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
    "calculus": ("normalize variables", "test limiting cases", "separate local from global behavior"),
    "analysis": ("use epsilon-room", "approximate by simple objects", "track exceptional sets"),
    "topology": ("unfold open/closed/compact", "use neighborhood tests", "try counterexamples"),
}


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
        "polya_phases": list(POLYA_PHASES),
        "tao_moves": list(TAO_MOVES),
        "codex_required_behavior": [
            "Apply the methodology silently; do not make the user memorize the checklist.",
            "For Lean mathematical edits, consult this methodology before choosing proof tactics or lemmas.",
            "Prefer Lean context tools before editing: project status, proof context, goals, diagnostics, symbols.",
            "After editing, run the strongest cheap verification and summarize only the applied method and result.",
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
        "Call `gauss_problem_solving_methodology` when the topic, proof strategy, or next move is unclear."
    )
