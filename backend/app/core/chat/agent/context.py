"""Runtime context schema for create_agent — mirrors deer-flow pattern.

``Context`` is passed as the ``context`` parameter to ``agent.astream()``
and becomes ``runtime.context`` inside every middleware hook and graph node.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    """Per-run immutable context propagated to all middleware hooks.

    Attributes:
        user_id: Authenticated user UUID string (required).
                 Never None — auth layer guarantees authentication.
    """

    user_id: str
