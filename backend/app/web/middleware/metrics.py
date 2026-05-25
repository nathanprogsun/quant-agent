"""Metrics middleware for request timing and status tracking."""

import time
from http import HTTPStatus

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.app_logging import get_logger
from app.common.stats.metric import AppMetrics

logger = get_logger()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records request timing and status metrics."""

    def __init__(self, app: FastAPI, metrics: AppMetrics) -> None:
        super().__init__(app)
        self.metrics = metrics

    def _emit_metrics_and_log(
        self,
        request: Request,
        start_time: float,
        status_code: int,
        exception: Exception | None = None,
    ) -> None:
        try:
            process_time = (time.perf_counter() - start_time) * 1000
            method_tag = f"method:{request.method.lower()}"
            status_tag = f"status:{status_code}"
            tags = [method_tag, status_tag]
            path_tag = (
                f"path:{request.scope['root_path'].lower()}{request.scope['route'].path.lower()}"
                if "route" in request.scope
                else None
            )
            if path_tag:
                tags.append(path_tag)

            if status_code >= HTTPStatus.BAD_REQUEST:
                logger.warning(
                    "API request failed: {} {} {}",
                    request.method,
                    path_tag,
                    status_code,
                )

            self.metrics.timing("api_timing", process_time, tags=tags)
            self.metrics.increment("api_status", tags=tags)
        except Exception:
            logger.exception("Exception while emitting metrics")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            self._emit_metrics_and_log(
                request=request,
                start_time=start_time,
                status_code=response.status_code,
            )
            return response
        except Exception as e:
            self._emit_metrics_and_log(
                request=request,
                start_time=start_time,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                exception=e,
            )
            raise
