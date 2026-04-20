#!/usr/bin/env python3
"""Lazy re-exports for the ``tools`` package.

Historically this package eagerly imported nearly every tool module at import
time. That meant a simple ``from tools.registry import registry`` also loaded
and registered unrelated optional surfaces before the CLI had selected its
actual tool surface.

Keep the public ``from tools import ...`` API, but only import a tool module
when that specific attribute is requested.
"""

from __future__ import annotations

from importlib import import_module


_MODULE_EXPORTS = {
    "tools.web_tools": (
        "web_search_tool",
        "web_extract_tool",
        "web_crawl_tool",
        "check_firecrawl_api_key",
    ),
    "tools.terminal_tool": (
        "terminal_tool",
        "check_terminal_requirements",
        "cleanup_vm",
        "cleanup_all_environments",
        "get_active_environments_info",
        "register_task_env_overrides",
        "clear_task_env_overrides",
        "TERMINAL_TOOL_DESCRIPTION",
    ),
    "tools.vision_tools": (
        "vision_analyze_tool",
        "check_vision_requirements",
    ),
    "tools.mixture_of_agents_tool": (
        "mixture_of_agents_tool",
        "check_moa_requirements",
    ),
    "tools.image_generation_tool": (
        "image_generate_tool",
        "check_image_generation_requirements",
    ),
    "tools.skills_tool": (
        "skills_list",
        "skill_view",
        "check_skills_requirements",
        "SKILLS_TOOL_DESCRIPTION",
    ),
    "tools.browser_tool": (
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_scroll",
        "browser_back",
        "browser_press",
        "browser_close",
        "browser_get_images",
        "browser_vision",
        "cleanup_browser",
        "cleanup_all_browsers",
        "get_active_browser_sessions",
        "check_browser_requirements",
        "BROWSER_TOOL_SCHEMAS",
    ),
    "tools.file_tools": (
        "read_file_tool",
        "write_file_tool",
        "patch_tool",
        "search_tool",
        "get_file_tools",
        "clear_file_ops_cache",
    ),
    "tools.todo_tool": (
        "todo_tool",
        "check_todo_requirements",
        "TODO_SCHEMA",
        "TodoStore",
    ),
    "tools.clarify_tool": (
        "clarify_tool",
        "check_clarify_requirements",
        "CLARIFY_SCHEMA",
    ),
    "tools.code_execution_tool": (
        "execute_code",
        "check_sandbox_requirements",
        "EXECUTE_CODE_SCHEMA",
    ),
    "tools.delegate_tool": (
        "delegate_task",
        "check_delegate_requirements",
        "DELEGATE_TASK_SCHEMA",
    ),
}

_EXPORTS = {
    name: (module_name, name)
    for module_name, names in _MODULE_EXPORTS.items()
    for name in names
}


def __getattr__(name: str):
    if name == "check_file_requirements":
        return check_file_requirements

    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'tools' has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


def check_file_requirements():
    """File tools only require the terminal backend to be available."""
    from .terminal_tool import check_terminal_requirements

    return check_terminal_requirements()


__all__ = sorted(list(_EXPORTS) + ["check_file_requirements"])
