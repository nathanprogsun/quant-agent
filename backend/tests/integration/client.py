"""APITestClient - Simplified API client wrapper for integration tests."""
from __future__ import annotations

import json
from typing import Any, cast

from httpx import AsyncClient


class APITestError(Exception):
    """Raised when API call returns non-success status."""

    def __init__(self, status: int, data: dict[str, Any]):
        self.status = status
        self.data = data
        super().__init__(f"API Error {status}: {data}")

    def __repr__(self) -> str:
        return f"APITestError(status={self.status}, data={self.data})"


class APITestClient:
    """Wrapper for AsyncClient with simplified error handling.

    All methods raise APITestError on non-success responses.
    Use get_raw() when you need to check status code without raising.
    """

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """POST request, raises on error."""
        resp = await self._client.post(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return cast(dict[str, Any], resp.json())

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """GET request, raises on error."""
        resp = await self._client.get(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return cast(dict[str, Any], resp.json())

    async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PUT request, raises on error."""
        resp = await self._client.put(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return cast(dict[str, Any], resp.json())

    async def patch(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PATCH request, raises on error."""
        resp = await self._client.patch(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return cast(dict[str, Any], resp.json())

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """DELETE request, raises on error."""
        resp = await self._client.delete(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return cast(dict[str, Any], resp.json())

    async def get_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """GET request, returns (status_code, json) without raising on error.

        Use this when you need to check error status codes.
        """
        resp = await self._client.get(path, **kwargs)
        return resp.status_code, resp.json()

    async def post_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """POST request, returns (status_code, json) without raising on error.

        For streaming responses, the body may be empty or SSE data.
        Returns empty dict if JSON parsing fails.
        """
        resp = await self._client.post(path, **kwargs)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    async def patch_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """PATCH request, returns (status_code, json) without raising on error."""
        resp = await self._client.patch(path, **kwargs)
        return resp.status_code, resp.json()

    async def delete_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """DELETE request, returns (status_code, json) without raising on error.

        Returns empty dict if JSON parsing fails (e.g., empty response body).
        """
        resp = await self._client.delete(path, **kwargs)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    async def post_sse(
        self,
        path: str,
        **kwargs: Any,
    ) -> tuple[int, dict[str, str], list[tuple[str, Any]]]:
        """POST request that parses an SSE response body.

        Returns:
            status_code, response headers (lowercase keys), parsed (event, data) pairs.
        """
        async with self._client.stream("POST", path, **kwargs) as resp:
            status = resp.status_code
            headers = {key.lower(): value for key, value in resp.headers.items()}
            events: list[tuple[str, Any]] = []
            current_event: str | None = None
            data_lines: list[str] = []

            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
                    continue
                if line != "" or current_event is None:
                    continue

                data_str = "\n".join(data_lines) if data_lines else "null"
                if data_str == "null":
                    data: Any = None
                else:
                    data = json.loads(data_str)
                events.append((current_event, data))
                current_event = None
                data_lines = []

            if current_event is not None:
                data_str = "\n".join(data_lines) if data_lines else "null"
                data = None if data_str == "null" else json.loads(data_str)
                events.append((current_event, data))

            return status, headers, events
