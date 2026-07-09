"""Unit tests for jqcli backtest result parsing helpers."""

from __future__ import annotations

from app.core.backtest.service import _parse_performance_series

_JAN_1_MS = 1704067200000
_JAN_31_MS = 1706659200000


def _sample_result_payload() -> dict:
    return {
        "id": "59453115",
        "data": {
            "state": "done",
            "userRecord": None,
            "result": {
                "count": 2,
                "overallReturn": {
                    "time": [_JAN_1_MS, _JAN_31_MS],
                    "value": [0.0, 5.2],
                },
                "benchmark": {
                    "time": [_JAN_1_MS, _JAN_31_MS],
                    "value": [0.0, 3.1],
                },
            },
        },
    }


def test_parse_performance_series_from_overall_return() -> None:
    points = _parse_performance_series(_sample_result_payload())
    assert len(points) == 2
    assert points[0].date == "2024-01-01"
    assert points[0].strategy == 0.0
    assert points[0].benchmark == 0.0
    assert points[1].strategy == 5.2
    assert points[1].benchmark == 3.1
    assert points[1].relative == 2.1
