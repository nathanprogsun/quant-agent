"""Build-time assertions for make_lead_agent / build_middlewares.

Covers the gap left by test_sync_io_offload.test_make_lead_agent_async_*
which mocks make_lead_agent entirely: here we drive the real assembly
function and assert the hardened middleware set is wired into the
production chain (not just constructed in isolation).
"""

from __future__ import annotations

from app.core.chat.agent.features import RuntimeFeatures
from app.core.chat.agent.middleware_chain import build_middlewares
from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware
from app.core.chat.middlewares.input_sanitization_middleware import (
    InputSanitizationMiddleware,
)
from app.core.chat.middlewares.llm_error_handling_middleware import (
    LLMErrorHandlingMiddleware,
)
from app.core.chat.middlewares.safety_finish_reason_middleware import (
    SafetyFinishReasonMiddleware,
)
from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware
from app.core.chat.middlewares.system_message_coalescing_middleware import (
    SystemMessageCoalescingMiddleware,
)
from app.core.chat.middlewares.token_budget_middleware import TokenBudgetMiddleware


def test_build_middlewares_wires_hardened_set() -> None:
    """The hardened middleware set must be present in the assembled chain."""
    chain = build_middlewares({}, features=RuntimeFeatures())
    types_present = {type(mw) for mw in chain}
    expected = [
        LLMErrorHandlingMiddleware,
        InputSanitizationMiddleware,
        SystemMessageCoalescingMiddleware,
        SafetyFinishReasonMiddleware,
        TokenBudgetMiddleware,
        ClarificationMiddleware,
    ]
    missing = [c.__name__ for c in expected if c not in types_present]
    assert not missing, f"middleware(s) missing from chain: {missing}"


def test_input_sanitization_runs_before_message_mutators() -> None:
    """InputSanitization must precede message-mutating middlewares so
    injection defense sees the original user content first."""
    chain = build_middlewares({}, features=RuntimeFeatures())
    idx_in = next(i for i, m in enumerate(chain) if isinstance(m, InputSanitizationMiddleware))
    idx_summ = next(i for i, m in enumerate(chain) if isinstance(m, SummarizationMiddleware))
    idx_coal = next(
        i for i, m in enumerate(chain) if isinstance(m, SystemMessageCoalescingMiddleware)
    )
    assert idx_in < idx_summ
    assert idx_in < idx_coal


def test_clarification_is_last() -> None:
    """ClarificationMiddleware is the terminal middleware."""
    chain = build_middlewares({}, features=RuntimeFeatures())
    assert isinstance(chain[-1], ClarificationMiddleware)
