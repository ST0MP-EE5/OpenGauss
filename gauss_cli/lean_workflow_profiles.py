"""Native Lean workflow profiles used by OpenGauss slash commands."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeanWorkflowProfile:
    name: str
    summary: str
    guidance: tuple[str, ...]


_PROFILES: dict[str, LeanWorkflowProfile] = {
    "prove": LeanWorkflowProfile(
        name="proof search",
        summary="Prove an existing Lean statement with local context, AXLE, and Comparator where applicable.",
        guidance=(
            "Inspect the target with lean_proof_context or lean_lsp_goals before editing proof terms.",
            "Use lean_lsp_symbols and lean_lsp_definition to discover local lemmas before adding new ones.",
            "Prefer small reusable lemmas only when they reduce real proof complexity.",
            "Finish by running lean_check_file or lean_lake_build; use lean_comparator_check when a Challenge/Solution pair is present.",
        ),
    ),
    "autoprove": LeanWorkflowProfile(
        name="autonomous proof search",
        summary="Run a bounded autonomous prove-repair-verify loop for an existing Lean target.",
        guidance=(
            "Start with project status, target diagnostics, and current sorry locations.",
            "Alternate proof attempts with lean_lsp_diagnostics and lean_check_file feedback.",
            "Use AXLE repair or simplification tools when a local proof attempt gets stuck.",
            "Select the best complete attempt by Lean verification, then Comparator if the task has benchmark-style files.",
        ),
    ),
    "formalize": LeanWorkflowProfile(
        name="theorem formalization",
        summary="Translate an informal or benchmark statement into maintainable Lean code.",
        guidance=(
            "Identify imports and nearby declaration patterns with lean_lsp_symbols before drafting definitions.",
            "Keep theorem names and public statements stable when the user or benchmark provides them.",
            "Use lemma factoring for reusable mathematical steps; keep one-off scaffolding local.",
            "Verify the resulting module with lean_check_file or lean_lake_build and report any remaining sorries.",
        ),
    ),
    "autoformalize": LeanWorkflowProfile(
        name="autonomous formalization campaign",
        summary="Run the native OpenGauss loop: import discovery, theorem formalization, proof search, repair, audit, cleanup.",
        guidance=(
            "Treat Challenge.lean as immutable when present and write the completed proof in Solution.lean.",
            "Use native LSP context for diagnostics, symbols, definitions, and cursor-local proof context.",
            "Use AXLE for proof checking, repair, declaration extraction, and normalization when helpful.",
            "Run lean_comparator_check as the final audit for benchmark-style Challenge/Solution work.",
            "Preserve artifacts and give a concise final status with the strongest verification result.",
        ),
    ),
    "draft": LeanWorkflowProfile(
        name="proof draft",
        summary="Draft a maintainable Lean proof plan and partial implementation.",
        guidance=(
            "Ground the plan in current diagnostics, imports, and nearby declarations.",
            "Leave explicit checkpoints if the proof cannot be completed in one pass.",
        ),
    ),
    "review": LeanWorkflowProfile(
        name="proof review",
        summary="Review Lean changes for correctness, maintainability, and proof-audit readiness.",
        guidance=(
            "Prioritize semantic bugs, unsound assumptions, remaining sorries, and missing Comparator checks.",
            "Use lean_lsp_diagnostics, lean_sorry_report, and lean_comparator_check where applicable.",
        ),
    ),
    "checkpoint": LeanWorkflowProfile(
        name="checkpoint",
        summary="Record the current Lean proof state and next actionable steps.",
        guidance=(
            "Summarize diagnostics, sorries, recently edited files, and the next proof step.",
            "Do not start a new external workflow or launcher.",
        ),
    ),
    "refactor": LeanWorkflowProfile(
        name="Lean refactor",
        summary="Refactor Lean code while preserving theorem statements and proof behavior.",
        guidance=(
            "Use symbol and reference-style searches before renaming or moving declarations.",
            "Verify with lean_check_file or lean_lake_build after each meaningful refactor.",
        ),
    ),
    "golf": LeanWorkflowProfile(
        name="proof cleanup",
        summary="Simplify a completed Lean proof while preserving auditability.",
        guidance=(
            "Prefer readability over cleverness unless the user explicitly asks for shortest proof.",
            "Run diagnostics and sorries after cleanup; use Comparator when auditing a challenge solution.",
        ),
    ),
}


def get_workflow_profile(workflow_kind: str) -> LeanWorkflowProfile:
    return _PROFILES.get(workflow_kind, _PROFILES["prove"])
