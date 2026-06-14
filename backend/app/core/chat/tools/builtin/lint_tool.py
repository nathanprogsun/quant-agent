"""Code lint agent tool — AST-based safety checks."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

CRITICAL_IMPORTS = {"os", "subprocess", "shutil"}
HIGH_IMPORTS = {"socket", "http", "urllib", "requests", "httpx"}
MEDIUM_IMPORTS = {"pickle", "shelve", "ctypes"}
CRITICAL_CALLS = {"eval", "exec", "__import__"}
HIGH_ATTR_CALLS = {"importlib.import_module", "importlib.util.find_spec"}


@dataclass(frozen=True)
class LintResult:
    is_safe: bool
    critical_issues: list[str] = field(default_factory=list)
    high_issues: list[str] = field(default_factory=list)
    medium_issues: list[str] = field(default_factory=list)


def lint_result_to_dict(result: LintResult) -> dict[str, Any]:
    """Convert LintResult to a JSON-serializable dict for tool responses."""
    return {
        "is_safe": result.is_safe,
        "critical_issues": list(result.critical_issues),
        "high_issues": list(result.high_issues),
        "medium_issues": list(result.medium_issues),
    }


def lint_code(code: str) -> LintResult:
    """Check generated code for safety violations using AST parsing."""
    critical: list[str] = []
    high: list[str] = []
    medium: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        critical.append(f"语法错误: {e}")
        return LintResult(is_safe=False, critical_issues=critical)

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module in CRITICAL_IMPORTS:
                    critical.append(f"禁止导入 {module} 模块")
                elif module in HIGH_IMPORTS:
                    high.append(f"不建议导入 {module} 模块")
                elif module in MEDIUM_IMPORTS:
                    medium.append(f"注意: 导入 {module} 模块存在安全风险")

        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module in CRITICAL_IMPORTS:
                critical.append(f"禁止从 {module} 模块导入")
            elif module in HIGH_IMPORTS:
                high.append(f"不建议从 {module} 模块导入")

        # Check dangerous calls: eval, exec, __import__
        elif isinstance(node, ast.Call):
            func_name = ""
            func_qualname = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
                if isinstance(node.func.value, ast.Name):
                    func_qualname = f"{node.func.value.id}.{func_name}"

            if func_name in CRITICAL_CALLS:
                critical.append(f"禁止使用 {func_name}()")
            elif func_qualname in HIGH_ATTR_CALLS:
                critical.append(f"禁止使用 {func_qualname}()")
            elif func_name == "getattr" and node.args:
                # Flag getattr with string literals that could bypass import restrictions
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    attr_name = str(node.args[1].value)
                    if attr_name in ("__import__", "__subclasses__", "__builtins__"):
                        critical.append(f"禁止通过 getattr 访问 {attr_name}")
            elif func_name == "open" and len(node.args) > 1:
                mode_arg = node.args[1]
                if isinstance(mode_arg, ast.Constant) and "w" in str(mode_arg.value):
                    high.append("不建议写文件")

    return LintResult(
        is_safe=len(critical) == 0,
        critical_issues=critical,
        high_issues=high,
        medium_issues=medium,
    )


@tool
def lint_code_tool(code: str) -> dict[str, Any]:
    """Check generated Python strategy code for safety violations."""
    return lint_result_to_dict(lint_code(code))
