"""TTFT + chunk-arrival pattern for chat SSE.

Measures:
  - t_request_start
  - first_event (metadata)
  - first_messages_chunk (any AIMessage chunk)
  - first_values_chunk
  - per-chunk inter-arrival times (to distinguish 'streaming works' from
    'all chunks arrive as one big blob')

The user's reported symptom is ~100s before any data — to repro we use
a query likely to trigger long reasoning (LLM providers that split
reasoning vs answer typically take 30-120s for thought + answer on such
queries).
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from app.settings import get_settings
from tests.integration.client import APITestClient

TTFT_BUDGET_SECONDS = 30.0
MAX_STREAM_SECONDS = 240.0

# Reasoning-triggering query. Designed so the model needs to "think"
# non-trivially before answering; budget = 4 steps * 4 primes ~ 16 primes
# to identify, plus a sum.
REASONING_QUERY = (
    "List the prime numbers between 1 and 30 one per line, "
    "then write a single line with the sum of those primes. "
    "Show your reasoning step by step."
)


def _should_run() -> bool:
    return os.environ.get("RUN_TTFT_REPRO") == "1"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _should_run(),
    reason="Diagnostic only — export RUN_TTFT_REPRO=1 to enable",
)
async def test_ttft_full_repro(authed_api_client: APITestClient) -> None:
    """Send a reasoning-triggering query and log every event's arrival time.

    Pass criterion: at least one event must arrive within TTFT_BUDGET_SECONDS.
    Diagnostic prints include [diag-ttft] tagged lines.
    """
    if not hasattr(authed_api_client, "_client"):
        pytest.skip("Test client does not expose underlying httpx client")

    settings = get_settings()
    created = await authed_api_client.post(
        "/api/v1/threads",
        json={"model_name": settings.model},
    )
    thread_id = created["id"]

    body = {
        "input": {
            "messages": [
                {"role": "user", "content": REASONING_QUERY},
            ],
        },
        "context": {"model_name": settings.model},
    }

    inner = authed_api_client._client  # type: ignore[attr-defined]

    t_request_start = time.perf_counter()
    first_metadata_time: float | None = None
    first_messages_time: float | None = None
    first_values_time: float | None = None
    chunk_count = 0
    last_event_time: float | None = None
    inter_arrival: list[float] = []
    seen_event_names: list[str] = []
    finished = False

    print(f"[diag-ttft] QUERY: {REASONING_QUERY[:80]!r}")
    print(f"[diag-ttft] model={settings.model} base_url={settings.openai_base_url}")
    print("[diag-ttft] sending request, t=0")

    try:
        async with inner.stream(
            "POST",
            f"/api/v1/threads/{thread_id}/runs/stream",
            json=body,
            timeout=MAX_STREAM_SECONDS,
        ) as resp:
            assert resp.status_code == 200, f"POST failed: {resp.status_code}"
            print(f"[diag-ttft] response status {resp.status_code}")

            current_event: str | None = None
            data_acc: list[str] = []
            async for raw_line in resp.aiter_lines():
                now = time.perf_counter()
                if last_event_time is not None:
                    inter_arrival.append(now - last_event_time)
                last_event_time = now

                stripped = raw_line.rstrip("\n")
                if stripped.startswith("event:"):
                    current_event = stripped[len("event:") :].strip()
                elif stripped.startswith("data:"):
                    data_acc.append(stripped[len("data:") :].strip())
                elif stripped == "" and current_event is not None:
                    data_str = "\n".join(data_acc) if data_acc else "null"
                    try:
                        _ = None if data_str == "null" else json.loads(data_str)
                    except json.JSONDecodeError:
                        _ = data_str

                    if first_metadata_time is None and current_event == "metadata":
                        first_metadata_time = now
                        print(f"[diag-ttft] first_metadata at {now - t_request_start:.3f}s")
                    if first_messages_time is None and current_event == "messages":
                        first_messages_time = now
                        print(f"[diag-ttft] first_messages at {now - t_request_start:.3f}s")
                    if first_values_time is None and current_event == "values":
                        first_values_time = now
                        print(f"[diag-ttft] first_values at {now - t_request_start:.3f}s")

                    seen_event_names.append(current_event)
                    chunk_count += 1
                    current_event = None
                    data_acc = []
                    if current_event is None:
                        # break once we have seen enough data
                        if chunk_count == 1:
                            print(f"[diag-ttft] first event wall-time {now - t_request_start:.3f}s")
                        if current_event == "__end__":
                            finished = True
                            break
            # Exit early after first non-metadata chunk arrival recorded
            # but keep listening for the full picture; bail when end seen.

            # If we never saw __end__, wait a bit more for any tail events.
            for _ in range(50):
                if finished:
                    break
                await asyncio.sleep(0.1)
    except Exception as exc:
        print(f"[diag-ttft] EXC {type(exc).__name__}: {exc}")

    total = (last_event_time or time.perf_counter()) - t_request_start
    print(f"[diag-ttft] DONE total={total:.3f}s chunks={chunk_count}")
    print(
        f"[diag-ttft] ttft(metadata)="
        f"{(first_metadata_time - t_request_start) if first_metadata_time else 'NA'}s"
    )
    print(
        f"[diag-ttft] ttft(messages)="
        f"{(first_messages_time - t_request_start) if first_messages_time else 'NA'}s"
    )
    print(
        f"[diag-ttft] ttft(values)="
        f"{(first_values_time - t_request_start) if first_values_time else 'NA'}s"
    )
    if inter_arrival:
        print(
            f"[diag-ttft] inter_arrival stats: "
            f"min={min(inter_arrival):.3f}s median="
            f"{sorted(inter_arrival)[len(inter_arrival) // 2]:.3f}s "
            f"max={max(inter_arrival):.3f}s"
        )
    print(f"[diag-ttft] event_names_seen={seen_event_names[:30]}")

    # Soft assert: we should at least see *some* event — failure of this
    # assert means infra is broken, not necessarily the bug.
    assert first_metadata_time is not None, "No metadata event seen"
    ttft = first_metadata_time - t_request_start
    assert ttft < TTFT_BUDGET_SECONDS, (
        f"TTFT(messages)={(first_messages_time - t_request_start) if first_messages_time else 'NA'}s "
        f"TTFT(values)={(first_values_time - t_request_start) if first_values_time else 'NA'}s "
        f"— 100s-first-data bug reproduced"
    )
