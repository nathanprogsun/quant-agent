"""Metrics utilities for monitoring.

Provides simple metric collectors for timing, counting, and gauging.
In production, integrate with Datadog, Prometheus, etc.
"""

from __future__ import annotations

from typing import Any

__all__ = ["AppMetrics", "api_metric", "custom_metric", "init_dog_statsd"]


class AppMetrics:
    """Metrics collector for API monitoring."""

    def __init__(self) -> None:
        self._metrics: dict[str, list[tuple[float, list[str]]]] = {}

    def timing(self, metric_name: str, value: float, tags: list[str] | None = None) -> None:
        """Record a timing metric in milliseconds."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        self._metrics[metric_name].append((value, tags or []))

    def increment(self, metric_name: str, value: float = 1, tags: list[str] | None = None) -> None:
        """Increment a counter metric."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        self._metrics[metric_name].append((value, tags or []))

    def gauge(self, metric_name: str, value: float, tags: list[str] | None = None) -> None:
        """Record a gauge metric."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        self._metrics[metric_name].append((value, tags or []))

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics."""
        return dict(self._metrics)


# Global metrics instances
api_metric = AppMetrics()
custom_metric = AppMetrics()


def init_dog_statsd() -> None:
    """Initialize DogStatsD client if configured.

    Call this at startup if datadog_on is True in settings.
    """
