# Reasoning Display Context (StrategyBot)

Persistent rules for how LLM chain-of-thought content travels from the model
through the agent runtime, persists across sessions, and surfaces to the user
in the chat UI. Applies to every chat thread in the backend's worker
(`app/core/chat/service/worker.py`) and every chat surface in the frontend
(`frontend/src/components/workspace/`).

## Language

**Reasoning chunk**:
A streaming token delta emitted by the LLM carrying chain-of-thought text, as
distinct from final reply text. Travels in one of `delta.reasoning_content`,
`delta.reasoning`, `additional_kwargs.reasoning_details`, a content block of
`type == "thinking"`, or inline `«THINK»` tags — the provider decides.
_Avoid_: "thinking text", "CoT" — both cause overloading with adjacent
concepts (the UI's "Thinking" label, "chain of thought" visualisation).

**Reasoning segment**:
The reasoning text belonging to a single AIMessage instance in the LangGraph
state. One segment per model turn — including tool-call turns and the final
no-tool-call turn.
_Avoid_: "round", "step" — both are overloaded ("tool round" in the prompt,
"step" in agent orchestration).

**Reasoning channel**:
The wire field that carries reasoning content across boundaries. In this
codebase: `AIMessageChunk.additional_kwargs["reasoning_content"]`, set by the
provider adapter and preserved end-to-end by `_serialize_chunk_data`.
_Avoid_: "sideband", "metadata" — both are implementation-shaped.

**AIMessage boundary**:
The boundary used to delimit one reasoning segment from the next. Coincident
exactly with the AIMessage instance in the LangGraph state.
_Avoid_: "tool-call round" — confusing with the user-facing "round" affordance.

**Normalized reasoning**:
The internal representation produced by the provider adapter, in which
whichever provider-side form reasoning arrived in has been promoted into a
single `additional_kwargs["reasoning_content"]` string before the chunk
leaves the chat model layer.

**Checkpointer persistence**:
The carrier for AIMessages — and therefore for reasoning — across reloads.
Reasoning inherits its persistence lifetime from the parent AIMessage.
_Avoid_: "message store", "ai_messages table" — neither exists in this
codebase (see ADR-0002).

**Segmented folding**:
The frontend layout where each reasoning segment lives in its own collapsible
row inside the message group's chain-of-thought, independent of sibling
segments.
_Avoid_: "single panel", "thinking log" — both names imply a different shape.
