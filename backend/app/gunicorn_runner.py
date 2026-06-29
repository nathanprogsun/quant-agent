"""Gunicorn runner with custom UvicornWorker.

Enables running FastAPI application with gunicorn workers
using uvloop and httptools for high performance.
"""

from __future__ import annotations

from typing import Any

from gunicorn.app.base import BaseApplication
from gunicorn.util import import_app
from uvicorn.workers import UvicornWorker as BaseUvicornWorker

try:
    import uvloop
except ImportError:
    uvloop = None  # type: ignore[assignment]


class UvicornWorker(BaseUvicornWorker):
    """Uvicorn worker configuration for gunicorn.

    Uses uvloop as the event loop and httptools as the HTTP parser.
    """

class GunicornApplication(BaseApplication):
    """Custom gunicorn application with uvicorn workers.

    Usage:
        gunicorn -k app.gunicorn_runner.UvicornWorker \
            --bind 0.0.0.0:8000 \
            --workers 4 \
            --access-logfile - \
            app.web.__main__:get_app
    """

    def __init__(
        self,
        app: str,
        host: str,
        port: int,
        workers: int,
        **kwargs: Any,
    ) -> None:
        """Initialize gunicorn application.

        Args:
            app: Python path to app factory (e.g., 'myapp.web.__main__:get_app').
            host: Host to bind to.
            port: Port to bind to.
            workers: Number of worker processes.
            **kwargs: Additional gunicorn options.
        """
        self.options = {
            "bind": f"{host}:{port}",
            "workers": workers,
            "worker_class": "app.gunicorn_runner.UvicornWorker",
            **kwargs,
        }
        self.app = app
        super().__init__()

    def load_config(self) -> None:
        """Load gunicorn configuration.

        Sets configuration from options, ignoring unknown keys.
        """
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self) -> str:  # type: ignore[override]
        """Load and return the application factory.

        Returns:
            Python path string to the app factory.
        """
        return import_app(self.app)  # type: ignore[return-value]
