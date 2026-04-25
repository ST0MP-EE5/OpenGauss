"""OpenGauss-native Lean LSP-style tools."""

from __future__ import annotations

import json
from typing import Any

from gauss_cli.lean_service import (
    LeanProofServiceError,
    local_lean_lsp_definition,
    local_lean_lsp_diagnostics,
    local_lean_lsp_goals,
    local_lean_lsp_hover,
    local_lean_lsp_references,
    local_lean_lsp_symbols,
    local_lean_proof_context,
)
from tools.registry import registry


def _json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error_payload(operation: str, exc: Exception) -> str:
    error_type = exc.code if isinstance(exc, LeanProofServiceError) else type(exc).__name__
    return _json_payload(
        {
            "success": False,
            "provider": "local",
            "operation": operation,
            "error": str(exc),
            "error_type": error_type,
        }
    )


def _diagnostics_tool(*, path: str, cwd: str | None = None, timeout_seconds: int = 30 * 60) -> str:
    try:
        payload = local_lean_lsp_diagnostics(
            path=path,
            cwd=cwd,
            timeout_seconds=int(timeout_seconds or 30 * 60),
        )
    except Exception as exc:
        return _error_payload("lean_lsp_diagnostics", exc)
    return _json_payload({"operation": "lean_lsp_diagnostics", **payload})


def _goals_tool(*, path: str, line: int, column: int, cwd: str | None = None) -> str:
    try:
        payload = local_lean_lsp_goals(path=path, line=int(line), column=int(column), cwd=cwd)
    except Exception as exc:
        return _error_payload("lean_lsp_goals", exc)
    return _json_payload({"success": True, "operation": "lean_lsp_goals", **payload})


def _hover_tool(*, path: str, line: int, column: int, cwd: str | None = None) -> str:
    try:
        payload = local_lean_lsp_hover(path=path, line=int(line), column=int(column), cwd=cwd)
    except Exception as exc:
        return _error_payload("lean_lsp_hover", exc)
    return _json_payload({"success": True, "operation": "lean_lsp_hover", **payload})


def _definition_tool(*, path: str, line: int, column: int, cwd: str | None = None) -> str:
    try:
        payload = local_lean_lsp_definition(path=path, line=int(line), column=int(column), cwd=cwd)
    except Exception as exc:
        return _error_payload("lean_lsp_definition", exc)
    return _json_payload({"success": True, "operation": "lean_lsp_definition", **payload})


def _references_tool(*, path: str, line: int, column: int, cwd: str | None = None, limit: int = 100) -> str:
    try:
        payload = local_lean_lsp_references(
            path=path,
            line=int(line),
            column=int(column),
            cwd=cwd,
            limit=int(limit or 100),
        )
    except Exception as exc:
        return _error_payload("lean_lsp_references", exc)
    return _json_payload({"success": True, "operation": "lean_lsp_references", **payload})


def _symbols_tool(*, query: str, cwd: str | None = None, path: str | None = None, limit: int = 50) -> str:
    try:
        payload = local_lean_lsp_symbols(
            query=query,
            cwd=cwd,
            path=path,
            limit=int(limit or 50),
        )
    except Exception as exc:
        return _error_payload("lean_lsp_symbols", exc)
    return _json_payload({"success": True, "operation": "lean_lsp_symbols", **payload})


def _proof_context_tool(
    *,
    path: str,
    cwd: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> str:
    try:
        payload = local_lean_proof_context(path=path, cwd=cwd, line=line, column=column)
    except Exception as exc:
        return _error_payload("lean_proof_context", exc)
    return _json_payload({"success": True, "operation": "lean_proof_context", **payload})


_PATH_PROPERTY = {
    "type": "string",
    "description": "Lean file path relative to the active project Lean root, or an absolute project file path.",
}
_CWD_PROPERTY = {
    "type": "string",
    "description": "Optional working directory used to discover the nearest OpenGauss project.",
}
_LINE_PROPERTY = {"type": "integer", "description": "1-based line number."}
_COLUMN_PROPERTY = {"type": "integer", "description": "1-based column number."}

LEAN_LSP_DIAGNOSTICS_SCHEMA = {
    "name": "lean_lsp_diagnostics",
    "description": "Return Lean diagnostics for a file using native OpenGauss local project services, not MCP.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROPERTY,
            "cwd": _CWD_PROPERTY,
            "timeout_seconds": {"type": "integer", "description": "Check timeout in seconds. Defaults to 1800."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}

LEAN_LSP_GOALS_SCHEMA = {
    "name": "lean_lsp_goals",
    "description": "Return local proof-state context near a Lean cursor position without calling lean-lsp-mcp.",
    "parameters": {
        "type": "object",
        "properties": {"path": _PATH_PROPERTY, "line": _LINE_PROPERTY, "column": _COLUMN_PROPERTY, "cwd": _CWD_PROPERTY},
        "required": ["path", "line", "column"],
        "additionalProperties": False,
    },
}

LEAN_LSP_HOVER_SCHEMA = {
    "name": "lean_lsp_hover",
    "description": "Return hover/type-like symbol information at a Lean cursor position from the native declaration index.",
    "parameters": {
        "type": "object",
        "properties": {"path": _PATH_PROPERTY, "line": _LINE_PROPERTY, "column": _COLUMN_PROPERTY, "cwd": _CWD_PROPERTY},
        "required": ["path", "line", "column"],
        "additionalProperties": False,
    },
}

LEAN_LSP_DEFINITION_SCHEMA = {
    "name": "lean_lsp_definition",
    "description": "Find likely definition sites for the symbol at a Lean cursor position.",
    "parameters": {
        "type": "object",
        "properties": {"path": _PATH_PROPERTY, "line": _LINE_PROPERTY, "column": _COLUMN_PROPERTY, "cwd": _CWD_PROPERTY},
        "required": ["path", "line", "column"],
        "additionalProperties": False,
    },
}

LEAN_LSP_REFERENCES_SCHEMA = {
    "name": "lean_lsp_references",
    "description": "Find project references for the symbol at a Lean cursor position using the native reference index.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROPERTY,
            "line": _LINE_PROPERTY,
            "column": _COLUMN_PROPERTY,
            "cwd": _CWD_PROPERTY,
            "limit": {"type": "integer", "description": "Maximum references to return. Defaults to 100."},
        },
        "required": ["path", "line", "column"],
        "additionalProperties": False,
    },
}

LEAN_LSP_SYMBOLS_SCHEMA = {
    "name": "lean_lsp_symbols",
    "description": "Search Lean declarations in the active project or one file.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Symbol, namespace, or signature text to search for."},
            "cwd": _CWD_PROPERTY,
            "path": _PATH_PROPERTY,
            "limit": {"type": "integer", "description": "Maximum symbols to return. Defaults to 50."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

LEAN_PROOF_CONTEXT_SCHEMA = {
    "name": "lean_proof_context",
    "description": "Return combined imports, declarations, diagnostics, sorries, and optional cursor context for a Lean file.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": _PATH_PROPERTY,
            "cwd": _CWD_PROPERTY,
            "line": _LINE_PROPERTY,
            "column": _COLUMN_PROPERTY,
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


registry.register(
    name="lean_lsp_diagnostics",
    toolset="lean-lsp",
    schema=LEAN_LSP_DIAGNOSTICS_SCHEMA,
    handler=lambda args, **kw: _diagnostics_tool(
        path=args.get("path", ""),
        cwd=args.get("cwd"),
        timeout_seconds=args.get("timeout_seconds") or 30 * 60,
    ),
)
registry.register(
    name="lean_lsp_goals",
    toolset="lean-lsp",
    schema=LEAN_LSP_GOALS_SCHEMA,
    handler=lambda args, **kw: _goals_tool(
        path=args.get("path", ""),
        line=args.get("line") or 1,
        column=args.get("column") or 1,
        cwd=args.get("cwd"),
    ),
)
registry.register(
    name="lean_lsp_hover",
    toolset="lean-lsp",
    schema=LEAN_LSP_HOVER_SCHEMA,
    handler=lambda args, **kw: _hover_tool(
        path=args.get("path", ""),
        line=args.get("line") or 1,
        column=args.get("column") or 1,
        cwd=args.get("cwd"),
    ),
)
registry.register(
    name="lean_lsp_definition",
    toolset="lean-lsp",
    schema=LEAN_LSP_DEFINITION_SCHEMA,
    handler=lambda args, **kw: _definition_tool(
        path=args.get("path", ""),
        line=args.get("line") or 1,
        column=args.get("column") or 1,
        cwd=args.get("cwd"),
    ),
)
registry.register(
    name="lean_lsp_references",
    toolset="lean-lsp",
    schema=LEAN_LSP_REFERENCES_SCHEMA,
    handler=lambda args, **kw: _references_tool(
        path=args.get("path", ""),
        line=args.get("line") or 1,
        column=args.get("column") or 1,
        cwd=args.get("cwd"),
        limit=args.get("limit") or 100,
    ),
)
registry.register(
    name="lean_lsp_symbols",
    toolset="lean-lsp",
    schema=LEAN_LSP_SYMBOLS_SCHEMA,
    handler=lambda args, **kw: _symbols_tool(
        query=args.get("query", ""),
        cwd=args.get("cwd"),
        path=args.get("path"),
        limit=args.get("limit") or 50,
    ),
)
registry.register(
    name="lean_proof_context",
    toolset="lean-lsp",
    schema=LEAN_PROOF_CONTEXT_SCHEMA,
    handler=lambda args, **kw: _proof_context_tool(
        path=args.get("path", ""),
        cwd=args.get("cwd"),
        line=args.get("line"),
        column=args.get("column"),
    ),
)
