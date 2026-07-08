"""Chat model adapters and reasoning normalisation.

The actual custom chat-model subclass lives in ``patched_chat.py`` (slice 1+);
``reasoning_normalizer.py`` exposes the pure-function side of the pipeline.
See ADR-0001 (wire protocol) and ADR-0003 (MiniMax / DeepSeek provider scope).
"""
