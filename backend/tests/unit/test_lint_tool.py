"""lint_code agent tool tests."""

from __future__ import annotations

from app.core.chat.tools.builtin.lint_tool import LintResult, lint_code


def test_lint_clean_code() -> None:
    """Clean code should pass lint."""
    code = """
import jqdatastd as jq

def initialize(context):
    context.stock_count = 5

def handle_data(context, data):
    stocks = jq.get_fundamentals(q.query(valuation.code).order_by(valuation.market_cap).limit(context.stock_count))
"""
    result = lint_code(code)
    assert isinstance(result, LintResult)
    assert result.is_safe is True
    assert len(result.critical_issues) == 0


def test_lint_detects_os_import() -> None:
    """Code importing os should be flagged as CRITICAL."""
    code = """
import os

def initialize(context):
    os.system("rm -rf /")
"""
    result = lint_code(code)
    assert result.is_safe is False
    assert len(result.critical_issues) > 0
    assert any("os" in issue for issue in result.critical_issues)


def test_lint_detects_eval() -> None:
    """Code using eval should be flagged as CRITICAL."""
    code = """
def initialize(context):
    eval("import subprocess")
"""
    result = lint_code(code)
    assert result.is_safe is False
    assert any("eval" in issue for issue in result.critical_issues)


def test_lint_detects_subprocess() -> None:
    """Code importing subprocess should be flagged as CRITICAL."""
    code = """
import subprocess

def initialize(context):
    subprocess.run(["ls"])
"""
    result = lint_code(code)
    assert result.is_safe is False
    assert any("subprocess" in issue for issue in result.critical_issues)
