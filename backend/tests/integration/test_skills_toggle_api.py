"""Integration tests for the skills toggle REST API (P1.5)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.app_context.app_context import AppContext
from app.skills.storage.local_skill_storage import LocalSkillStorage
from app.web.api.skills.service import SkillsService
from tests.integration.client import APITestClient


def _seed_skill(root: Path, name: str, body: str = "body") -> None:
    container = root / "public" / name
    container.mkdir(parents=True, exist_ok=True)
    (container / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: desc for {name}\n---\n{body}",
        encoding="utf-8",
    )


@pytest.fixture
async def skills_client(
    api_client: AsyncClient,
    test_app_context: AppContext,
    tmp_path: Path,
) -> AsyncClient:
    """Authed client with a SkillsService backed by a tmp skill root."""
    client = APITestClient(api_client)
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"skill-test-{uuid.uuid4().hex[:8]}@test.com",
            "password": "TestPassword123!",
            "full_name": "Skill Tester",
        },
    )

    root = tmp_path / "skills"
    _seed_skill(root, "deep-research", body="research body")
    _seed_skill(root, "code-review", body="review body")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(json.dumps({"skills": {}}), encoding="utf-8")

    app = api_client._transport.app  # type: ignore[attr-defined]
    app.state.skills_service = SkillsService(
        storage=LocalSkillStorage(root=root),
        config_path=config_path,
    )
    return api_client


@pytest.mark.integration
async def test_get_disclosure_returns_metadata(skills_client: AsyncClient) -> None:
    resp = await skills_client.get("/api/skills/disclosure")
    assert resp.status_code == 200
    payload = resp.json()
    names = {s["name"] for s in payload["skills"]}
    assert names == {"deep-research", "code-review"}
    # Metadata only — no body field
    assert "body" not in payload["skills"][0]
    # Unknown skills default enabled
    assert all(s["enabled"] is True for s in payload["skills"])


@pytest.mark.integration
async def test_put_toggle_disables_skill_and_persists(skills_client: AsyncClient) -> None:
    resp = await skills_client.put("/api/skills/deep-research", json={"enabled": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["name"] == "deep-research"

    # Subsequent GET reflects new state
    listing = (await skills_client.get("/api/skills/disclosure")).json()
    by_name = {s["name"]: s for s in listing["skills"]}
    assert by_name["deep-research"]["enabled"] is False
    assert by_name["code-review"]["enabled"] is True


@pytest.mark.integration
async def test_put_toggle_writes_extensions_config(skills_client: AsyncClient) -> None:
    await skills_client.put("/api/skills/code-review", json={"enabled": False})
    app = skills_client._transport.app  # type: ignore[attr-defined]
    service: SkillsService = app.state.skills_service
    on_disk = json.loads(service._config_path.read_text(encoding="utf-8"))
    assert on_disk["skills"]["code-review"]["enabled"] is False


@pytest.mark.integration
async def test_put_toggle_unknown_skill_returns_404(skills_client: AsyncClient) -> None:
    resp = await skills_client.put("/api/skills/nope", json={"enabled": False})
    assert resp.status_code == 404


@pytest.mark.integration
async def test_toggle_re_enables_skill(skills_client: AsyncClient) -> None:
    await skills_client.put("/api/skills/deep-research", json={"enabled": False})
    await skills_client.put("/api/skills/deep-research", json={"enabled": True})
    listing = (await skills_client.get("/api/skills/disclosure")).json()
    by_name = {s["name"]: s for s in listing["skills"]}
    assert by_name["deep-research"]["enabled"] is True
