"""Extract entities from strategy Python source (stdlib ast)."""

from __future__ import annotations

import ast
import re
import warnings
from functools import lru_cache
from typing import Any

from app.core.jq_kb.utils import json_safe_value

JQ_API_PATTERN = re.compile(
    r"\b(get_\w+|set_\w+|order_\w+|create_\w+|run_\w+|attribute_history|history)\s*\("
)


@lru_cache(maxsize=512)
def _parse_strategy_code(code: str) -> ast.Module | None:
    """Parse strategy source; suppress SyntaxWarning from third-party code."""
    if not code:
        return None
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            return ast.parse(code)
    except SyntaxError:
        return None


def extract_entities(code: str) -> dict[str, Any]:
    tree = _parse_strategy_code(code)
    functions = _extract_functions(tree)
    classes = _extract_classes(tree)
    imports = _extract_imports(tree)
    key_params = _extract_key_params(tree)
    factors_called = sorted(set(JQ_API_PATTERN.findall(code)))
    return {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "key_params": key_params,
        "factors_called": factors_called,
    }


def extract_function_code(code: str, func_name: str) -> str:
    tree = _parse_strategy_code(code)
    if tree is None:
        return ""
    lines = code.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            start = node.lineno - 1
            end = node.end_lineno or (start + 1)
            return "\n".join(lines[start:end])
    return ""


def _extract_functions(tree: ast.Module | None) -> list[str]:
    if tree is None:
        return []
    return list(dict.fromkeys(n.name for n in tree.body if isinstance(n, ast.FunctionDef)))


def _extract_classes(tree: ast.Module | None) -> list[str]:
    if tree is None:
        return []
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def _extract_imports(tree: ast.Module | None) -> list[str]:
    if tree is None:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)
    return imports


def _extract_key_params(tree: ast.Module | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if tree is None:
        return params
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "g"
            ):
                try:
                    params[target.attr] = json_safe_value(ast.literal_eval(node.value))
                except (ValueError, SyntaxError):
                    try:
                        params[target.attr] = ast.unparse(node.value)
                    except AttributeError:
                        params[target.attr] = "..."
    return params
