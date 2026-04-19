"""AXLE-backed Lean proof-service tools."""

from __future__ import annotations

import json
from typing import Any

from gauss_cli.config import load_config
from gauss_cli.lean_service import (
    AxleProofService,
    LeanProofServiceError,
    axle_sdk_available,
    resolve_axle_environment,
)
from tools.registry import registry


def check_axle_requirements() -> bool:
    """Return whether AXLE-backed tools can be loaded."""
    return axle_sdk_available()


def _build_axle_service() -> AxleProofService:
    return AxleProofService()


def _success_payload(operation: str, **payload: Any) -> str:
    return json.dumps(
        {
            "success": True,
            "provider": "axle",
            "operation": operation,
            **payload,
        },
        ensure_ascii=False,
    )


def _error_payload(operation: str, exc: LeanProofServiceError, **payload: Any) -> str:
    return json.dumps(
        {
            "success": False,
            "provider": "axle",
            "operation": operation,
            "error": str(exc),
            "error_type": exc.code,
            **payload,
        },
        ensure_ascii=False,
    )


async def axle_environments_tool(timeout_seconds: float | None = None) -> str:
    service = _build_axle_service()
    try:
        environments = await service.list_environments(timeout_seconds=timeout_seconds)
    except LeanProofServiceError as exc:
        return _error_payload("environments", exc)
    return _success_payload(
        "environments",
        environments=environments,
        count=len(environments),
    )


async def axle_check_tool(
    *,
    content: str,
    environment: str | None = None,
    mathlib_options: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.check(
            content=content,
            environment=resolved_environment,
            mathlib_options=mathlib_options,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("check", exc, environment=environment or "")
    return _success_payload("check", environment=resolved_environment, result=result)


async def axle_verify_proof_tool(
    *,
    formal_statement: str,
    content: str,
    environment: str | None = None,
    permitted_sorries: list[str] | None = None,
    mathlib_options: bool | None = None,
    use_def_eq: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.verify_proof(
            formal_statement=formal_statement,
            content=content,
            environment=resolved_environment,
            permitted_sorries=permitted_sorries,
            mathlib_options=mathlib_options,
            use_def_eq=use_def_eq,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("verify_proof", exc, environment=environment or "")
    return _success_payload("verify_proof", environment=resolved_environment, result=result)


async def axle_extract_decls_tool(
    *,
    content: str,
    environment: str | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.extract_decls(
            content=content,
            environment=resolved_environment,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("extract_decls", exc, environment=environment or "")
    return _success_payload("extract_decls", environment=resolved_environment, result=result)


async def axle_repair_proofs_tool(
    *,
    content: str,
    environment: str | None = None,
    names: list[str] | None = None,
    indices: list[int] | None = None,
    repairs: list[str] | None = None,
    terminal_tactics: list[str] | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.repair_proofs(
            content=content,
            environment=resolved_environment,
            names=names,
            indices=indices,
            repairs=repairs,
            terminal_tactics=terminal_tactics,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("repair_proofs", exc, environment=environment or "")
    return _success_payload("repair_proofs", environment=resolved_environment, result=result)


async def axle_simplify_theorems_tool(
    *,
    content: str,
    environment: str | None = None,
    names: list[str] | None = None,
    indices: list[int] | None = None,
    simplifications: list[str] | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.simplify_theorems(
            content=content,
            environment=resolved_environment,
            names=names,
            indices=indices,
            simplifications=simplifications,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("simplify_theorems", exc, environment=environment or "")
    return _success_payload("simplify_theorems", environment=resolved_environment, result=result)


async def axle_normalize_tool(
    *,
    content: str,
    environment: str | None = None,
    normalizations: list[str] | None = None,
    failsafe: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.normalize(
            content=content,
            environment=resolved_environment,
            normalizations=normalizations,
            failsafe=failsafe,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("normalize", exc, environment=environment or "")
    return _success_payload("normalize", environment=resolved_environment, result=result)


async def axle_rename_tool(
    *,
    content: str,
    declarations: dict[str, str],
    environment: str | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> str:
    service = _build_axle_service()
    config = load_config()
    try:
        resolved_environment = resolve_axle_environment(
            config,
            explicit_environment=environment,
        )
        result = await service.rename(
            content=content,
            declarations=declarations,
            environment=resolved_environment,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _error_payload("rename", exc, environment=environment or "")
    return _success_payload("rename", environment=resolved_environment, result=result)


AXLE_ENVIRONMENTS_SCHEMA = {
    "name": "axle_environments",
    "description": "List AXLE Lean environments that can be used with the AXLE-backed proof-service tools.",
    "parameters": {
        "type": "object",
        "properties": {
            "timeout_seconds": {
                "type": "number",
                "description": "Optional timeout for the AXLE environments request.",
            }
        },
        "required": [],
    },
}

AXLE_CHECK_SCHEMA = {
    "name": "axle_check",
    "description": "Check Lean code with AXLE. Environment resolution order is project override, then gauss.lean_service.environment, then this tool argument.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to check."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "mathlib_options": {"type": "boolean", "description": "Whether to enable Mathlib options."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content"],
    },
}

AXLE_VERIFY_PROOF_SCHEMA = {
    "name": "axle_verify_proof",
    "description": "Verify a Lean proof with AXLE against a formal statement.",
    "parameters": {
        "type": "object",
        "properties": {
            "formal_statement": {"type": "string", "description": "The formal statement to verify."},
            "content": {"type": "string", "description": "Lean proof content."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "permitted_sorries": {"type": "array", "items": {"type": "string"}, "description": "Allowed sorry declaration names."},
            "mathlib_options": {"type": "boolean", "description": "Whether to enable Mathlib options."},
            "use_def_eq": {"type": "boolean", "description": "Whether to use definitional equality."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["formal_statement", "content"],
    },
}

AXLE_EXTRACT_DECLS_SCHEMA = {
    "name": "axle_extract_decls",
    "description": "Extract Lean declarations and dependency metadata with AXLE.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to analyze."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content"],
    },
}

AXLE_REPAIR_PROOFS_SCHEMA = {
    "name": "axle_repair_proofs",
    "description": "Repair Lean proofs with AXLE using optional target names, indices, and tactics.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to repair."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "names": {"type": "array", "items": {"type": "string"}, "description": "Target declaration names."},
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "Target declaration indices."},
            "repairs": {"type": "array", "items": {"type": "string"}, "description": "Repair strategies to apply."},
            "terminal_tactics": {"type": "array", "items": {"type": "string"}, "description": "Terminal tactics to try."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content"],
    },
}

AXLE_SIMPLIFY_THEOREMS_SCHEMA = {
    "name": "axle_simplify_theorems",
    "description": "Simplify Lean theorem proofs with AXLE.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to simplify."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "names": {"type": "array", "items": {"type": "string"}, "description": "Target declaration names."},
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "Target declaration indices."},
            "simplifications": {"type": "array", "items": {"type": "string"}, "description": "Simplification passes to apply."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content"],
    },
}

AXLE_NORMALIZE_SCHEMA = {
    "name": "axle_normalize",
    "description": "Normalize Lean code formatting and structure with AXLE.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to normalize."},
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "normalizations": {"type": "array", "items": {"type": "string"}, "description": "Normalization passes to apply."},
            "failsafe": {"type": "boolean", "description": "Whether to use AXLE's failsafe normalization mode."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content"],
    },
}

AXLE_RENAME_SCHEMA = {
    "name": "axle_rename",
    "description": "Rename Lean declarations with AXLE using a declaration-name mapping.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lean code to rewrite."},
            "declarations": {
                "type": "object",
                "description": "Mapping from old declaration names to new declaration names.",
                "additionalProperties": {"type": "string"},
            },
            "environment": {"type": "string", "description": "Optional AXLE environment name."},
            "ignore_imports": {"type": "boolean", "description": "Whether to ignore imports in the input content."},
            "timeout_seconds": {"type": "number", "description": "Optional request timeout."},
        },
        "required": ["content", "declarations"],
    },
}


registry.register(
    name="axle_environments",
    toolset="axle",
    schema=AXLE_ENVIRONMENTS_SCHEMA,
    handler=lambda args, **kw: axle_environments_tool(timeout_seconds=args.get("timeout_seconds")),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_check",
    toolset="axle",
    schema=AXLE_CHECK_SCHEMA,
    handler=lambda args, **kw: axle_check_tool(
        content=args.get("content", ""),
        environment=args.get("environment"),
        mathlib_options=args.get("mathlib_options"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_verify_proof",
    toolset="axle",
    schema=AXLE_VERIFY_PROOF_SCHEMA,
    handler=lambda args, **kw: axle_verify_proof_tool(
        formal_statement=args.get("formal_statement", ""),
        content=args.get("content", ""),
        environment=args.get("environment"),
        permitted_sorries=args.get("permitted_sorries"),
        mathlib_options=args.get("mathlib_options"),
        use_def_eq=args.get("use_def_eq"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_extract_decls",
    toolset="axle",
    schema=AXLE_EXTRACT_DECLS_SCHEMA,
    handler=lambda args, **kw: axle_extract_decls_tool(
        content=args.get("content", ""),
        environment=args.get("environment"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_repair_proofs",
    toolset="axle",
    schema=AXLE_REPAIR_PROOFS_SCHEMA,
    handler=lambda args, **kw: axle_repair_proofs_tool(
        content=args.get("content", ""),
        environment=args.get("environment"),
        names=args.get("names"),
        indices=args.get("indices"),
        repairs=args.get("repairs"),
        terminal_tactics=args.get("terminal_tactics"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_simplify_theorems",
    toolset="axle",
    schema=AXLE_SIMPLIFY_THEOREMS_SCHEMA,
    handler=lambda args, **kw: axle_simplify_theorems_tool(
        content=args.get("content", ""),
        environment=args.get("environment"),
        names=args.get("names"),
        indices=args.get("indices"),
        simplifications=args.get("simplifications"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_normalize",
    toolset="axle",
    schema=AXLE_NORMALIZE_SCHEMA,
    handler=lambda args, **kw: axle_normalize_tool(
        content=args.get("content", ""),
        environment=args.get("environment"),
        normalizations=args.get("normalizations"),
        failsafe=args.get("failsafe"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
registry.register(
    name="axle_rename",
    toolset="axle",
    schema=AXLE_RENAME_SCHEMA,
    handler=lambda args, **kw: axle_rename_tool(
        content=args.get("content", ""),
        declarations=args.get("declarations", {}),
        environment=args.get("environment"),
        ignore_imports=args.get("ignore_imports"),
        timeout_seconds=args.get("timeout_seconds"),
    ),
    check_fn=check_axle_requirements,
    is_async=True,
    emoji="🧠",
)
