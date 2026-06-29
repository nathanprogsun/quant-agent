"""Export the FastAPI OpenAPI schema to a file importable by Postman.

Usage::

    uv run python scripts/export_openapi.py --output openapi.json
    uv run python scripts/export_openapi.py --server http://localhost:8000

The output is a standard OpenAPI 3.x JSON document. Postman can import it
directly via *Import → File → OpenAPI 3.0*, or via *Import → Link* pointing
at a running server's ``/openapi.json`` endpoint.

A ``cookieAuth`` security scheme is added so Postman knows that authenticated
endpoints expect an ``access_token`` cookie (this project uses cookie-based
JWT, not Bearer headers). Override the cookie value inside Postman's
*Cookies* modal — it is intentionally not embedded in the spec.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.web.application import get_app

DEFAULT_SERVER = "http://localhost:8000"


def build_spec(server_url: str) -> dict[str, Any]:
    """Build a Postman-friendly OpenAPI 3.x spec from the FastAPI app."""
    app = get_app()
    spec = app.openapi()

    # Pin the server URL Postman should target. Without this, Postman leaves
    # the Base URL empty and every request is malformed.
    spec["servers"] = [{"url": server_url, "description": "Local dev server"}]

    # Project uses cookie-based JWT auth (see app.web.middleware.auth_middleware).
    # Declare a single security scheme Postman can recognize so authenticated
    # endpoints render with the auth indicator.
    spec.setdefault("components", {})
    spec["components"].setdefault("securitySchemes", {})
    spec["components"]["securitySchemes"]["cookieAuth"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "access_token",
        "description": (
            "JWT issued by /api/v1/auth/login, set as the access_token cookie. "
            "Configure the value in Postman's Cookies modal for the host above."
        ),
    }

    # The project enforces auth via middleware (AuthMiddleware), not via
    # FastAPI Security dependencies — so the generated spec doesn't tell
    # Postman which endpoints require auth. Decorate each operation: public
    # endpoints get an empty security array (overrides inheritance), the rest
    # inherit the default cookieAuth from the root spec.
    from app.web.middleware.auth_middleware import PUBLIC_PATHS

    for path, methods in spec.get("paths", {}).items():
        for http_method, op in methods.items():
            if http_method not in {"get", "post", "put", "patch", "delete"}:
                continue
            # Strip a trailing {param} when comparing to PUBLIC_PATHS, which
            # lists concrete paths (e.g. /api/v1/auth/login, not templates).
            is_public = path in PUBLIC_PATHS or any(
                path.startswith(p.rstrip("/") + "/") for p in PUBLIC_PATHS
            )
            if is_public:
                op["security"] = []

    # Default for the rest: cookie auth required. Operations that already
    # carry an explicit (non-empty) security keep it; everything else inherits.
    spec["security"] = [{"cookieAuth": []}]

    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OpenAPI spec for Postman")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=BACKEND_ROOT / "openapi.json",
        help="Where to write the JSON file (default: backend/openapi.json)",
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"Base URL embedded in the spec (default: {DEFAULT_SERVER})",
    )
    args = parser.parse_args()

    spec = build_spec(args.server)
    args.output.write_text(json.dumps(spec, indent=2, ensure_ascii=False))

    endpoint_count = sum(len(routes) for routes in spec.get("paths", {}).values())
    print(f"Wrote {args.output} ({endpoint_count} operations, server={args.server})")


if __name__ == "__main__":
    main()
