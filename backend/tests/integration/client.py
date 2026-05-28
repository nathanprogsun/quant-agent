"""APITestClient - Simplified API client wrapper for integration tests."""
from __future__ import annotations

from typing import Any

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

    def __init__(self, client: AsyncClient):
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """POST request, raises on error."""
        resp = await self._client.post(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """GET request, raises on error."""
        resp = await self._client.get(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PUT request, raises on error."""
        resp = await self._client.put(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def patch(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PATCH request, raises on error."""
        resp = await self._client.patch(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """DELETE request, raises on error."""
        resp = await self._client.delete(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

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
