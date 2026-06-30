"""Unit tests for jqcli backtest result parsing helpers."""

from __future__ import annotations

from app.core.backtest.service import (
    _parse_holding_groups,
    _parse_holdings_from_logs,
    _parse_performance_series,
    _parse_trade_groups,
    _parse_trades_from_logs,
)

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


def test_parse_trade_groups_returns_empty_when_no_trades_key() -> None:
    assert _parse_trade_groups(_sample_result_payload()) == []


def test_parse_holding_groups_returns_empty_when_user_record_none() -> None:
    assert _parse_holding_groups(_sample_result_payload()) == []


def test_parse_trades_from_logs() -> None:
    logs = [
        "2024-01-02 09:30:00 - INFO - 订单已委托：StockOrder(id=1, security=605365.XSHG, amount=1900, action=open)",
        "2024-01-15 09:30:00 - INFO - 订单已委托：StockOrder(id=2, security=605365.XSHG, amount=1900, action=close)",
    ]
    groups = _parse_trades_from_logs(logs)
    assert len(groups) == 2
    assert groups[0].date == "2024-01-02"
    assert groups[0].trades[0].symbol == "605365.XSHG"
    assert groups[0].trades[0].side == "买入"
    assert groups[1].trades[0].side == "卖出"


def test_parse_holdings_from_logs() -> None:
    logs = [
        "2024-01-02 15:00:00 - INFO - 605365.XSHG: 1900 股, 价值 29754.00",
        "2024-01-02 15:00:00 - INFO - 600519.XSHG: 100 股, 价值 150000.00",
    ]
    groups = _parse_holdings_from_logs(logs)
    assert len(groups) == 1
    assert groups[0].date == "2024-01-02"
    assert len(groups[0].holdings) == 2
    assert groups[0].summary.total_market_value == 179754.0
