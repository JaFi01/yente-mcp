import os

os.environ.setdefault("YENTE_BASE_URL", "http://yente-test:8000")

import pytest
import respx
import httpx

import yente_mcp.server as server_module
from yente_mcp.server import (
    health_check,
    get_status,
    list_datasets,
    get_dataset,
    search_entities,
    match_person,
    match_company,
    match_organization,
    match_vessel,
    match_crypto_wallet,
    match_bulk,
    get_entity,
    get_entity_adjacent,
    reconcile,
)

BASE = "http://yente-test:8000"


@pytest.fixture(autouse=True)
def reset_http_client():
    server_module._client = None
    yield
    server_module._client = None


@pytest.mark.asyncio
@respx.mock
async def test_health_check():
    respx.get(f"{BASE}/healthz").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    result = await health_check()
    assert result["status"] == "ok"


@pytest.mark.asyncio
@respx.mock
async def test_get_status():
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(200, json={"version": "4.0.0"}))
    result = await get_status()
    assert "version" in result


@pytest.mark.asyncio
@respx.mock
async def test_list_datasets():
    respx.get(f"{BASE}/datasets").mock(
        return_value=httpx.Response(200, json=[{"name": "default"}, {"name": "sanctions"}])
    )
    result = await list_datasets()
    assert len(result) == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_dataset():
    respx.get(f"{BASE}/datasets/sanctions").mock(
        return_value=httpx.Response(200, json={"name": "sanctions", "title": "Consolidated Sanctions"})
    )
    result = await get_dataset("sanctions")
    assert "name" in result


@pytest.mark.asyncio
@respx.mock
async def test_search_entities_basic():
    respx.get(f"{BASE}/search/default").mock(
        return_value=httpx.Response(200, json={"results": [], "total": 0})
    )
    result = await search_entities("test query")
    assert "results" in result


@pytest.mark.asyncio
@respx.mock
async def test_search_entities_with_schema():
    respx.get(f"{BASE}/search/sanctions").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"schema": "Person", "id": "NK-abc"}], "total": 1},
        )
    )
    result = await search_entities("Putin", dataset="sanctions", schema="Person")
    assert result["results"][0]["schema"] == "Person"


@pytest.mark.asyncio
@respx.mock
async def test_match_person_minimal():
    respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_person("John Doe")
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_person_full():
    respx.post(f"{BASE}/match/sanctions").mock(
        return_value=httpx.Response(
            200,
            json={
                "responses": {
                    "q": {
                        "results": [{"id": "NK-xyz", "score": 0.92, "schema": "Person"}]
                    }
                }
            },
        )
    )
    result = await match_person(
        "Vladimir Putin",
        dataset="sanctions",
        birth_date="1952-10-07",
        nationality="ru",
        aliases=["Владимир Путин"],
    )
    assert result["responses"]["q"]["results"][0]["score"] == 0.92


@pytest.mark.asyncio
@respx.mock
async def test_match_company():
    respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_company("Acme Corp")
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_organization():
    respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_organization("Red Cross")
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_organization_with_aliases():
    respx.post(f"{BASE}/match/sanctions").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_organization(
        "Hamas",
        dataset="sanctions",
        country="ps",
        aliases=["حماس", "Islamic Resistance Movement"],
    )
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_vessel():
    respx.post(f"{BASE}/match/sanctions").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_vessel("Ever Given", dataset="sanctions")
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_vessel_with_aliases():
    respx.post(f"{BASE}/match/sanctions").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_vessel(
        "Arctic Sea",
        dataset="sanctions",
        aliases=["Arktik More", "Polar Star"],
        imo_number="9403905",
    )
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_crypto_wallet():
    respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_crypto_wallet("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf")
    assert "responses" in result


@pytest.mark.asyncio
@respx.mock
async def test_match_crypto_wallet_custom_limit():
    route = respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q": {"results": []}}})
    )
    result = await match_crypto_wallet("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf", limit=10)
    assert "responses" in result
    import json
    body = json.loads(route.calls.last.request.content)
    assert body["limit"] == 10


@pytest.mark.asyncio
@respx.mock
async def test_match_bulk():
    respx.post(f"{BASE}/match/default").mock(
        return_value=httpx.Response(
            200,
            json={
                "responses": {
                    "person1": {"results": []},
                    "company1": {"results": []},
                }
            },
        )
    )
    result = await match_bulk(
        queries={
            "person1": {"schema": "Person", "properties": {"name": ["Jane Doe"]}},
            "company1": {"schema": "Company", "properties": {"name": ["Evil Corp"]}},
        }
    )
    assert "person1" in result["responses"]
    assert "company1" in result["responses"]


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_nested():
    respx.get(f"{BASE}/entities/NK-abc").mock(
        return_value=httpx.Response(200, json={"id": "NK-abc", "schema": "Person", "properties": {}})
    )
    result = await get_entity("NK-abc")
    assert result["id"] == "NK-abc"
    assert respx.calls.last.request.url.params["nested"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_flat():
    respx.get(f"{BASE}/entities/NK-abc").mock(
        return_value=httpx.Response(200, json={"id": "NK-abc", "schema": "Person", "properties": {}})
    )
    result = await get_entity("NK-abc", nested=False)
    assert result["schema"] == "Person"
    assert respx.calls.last.request.url.params["nested"] == "false"


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_adjacent_all():
    respx.get(f"{BASE}/entities/NK-abc/adjacent").mock(
        return_value=httpx.Response(
            200,
            json={"sanctions": [{"id": "NK-sanction-1"}], "count": 1},
        )
    )
    result = await get_entity_adjacent("NK-abc")
    assert "sanctions" in result


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_adjacent_prop():
    respx.get(f"{BASE}/entities/NK-abc/adjacent/sanctions").mock(
        return_value=httpx.Response(200, json={"results": [], "count": 0})
    )
    result = await get_entity_adjacent("NK-abc", prop="sanctions")
    assert "count" in result


@pytest.mark.asyncio
@respx.mock
async def test_reconcile():
    respx.post(f"{BASE}/reconcile/default").mock(
        return_value=httpx.Response(
            200,
            json={"q0": {"result": []}},
        )
    )
    result = await reconcile({"q0": {"query": "Vladimir Putin", "type": "Person", "limit": 3}})
    assert "q0" in result


# ── Error path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_get_returns_structured_error_on_404():
    respx.get(f"{BASE}/entities/NK-missing").mock(
        return_value=httpx.Response(404, json={"detail": "Entity not found"})
    )
    result = await get_entity("NK-missing")
    assert result["status"] == 404
    assert "error" in result


@pytest.mark.asyncio
@respx.mock
async def test_get_returns_structured_error_on_500():
    respx.get(f"{BASE}/healthz").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )
    result = await health_check()
    assert result["status"] == 500
    assert "error" in result


@pytest.mark.asyncio
@respx.mock
async def test_post_returns_structured_error_on_404():
    respx.post(f"{BASE}/match/unknown-dataset").mock(
        return_value=httpx.Response(404, json={"detail": "Dataset not found"})
    )
    result = await match_person("John Doe", dataset="unknown-dataset")
    assert result["status"] == 404
    assert "error" in result


@pytest.mark.asyncio
@respx.mock
async def test_get_returns_structured_error_on_timeout():
    respx.get(f"{BASE}/healthz").mock(side_effect=httpx.TimeoutException("request timed out"))
    result = await health_check()
    assert result["status"] is None
    assert "error" in result


@pytest.mark.asyncio
@respx.mock
async def test_get_returns_structured_error_on_network_failure():
    respx.get(f"{BASE}/healthz").mock(side_effect=httpx.ConnectError("connection refused"))
    result = await health_check()
    assert result["status"] is None
    assert "error" in result


@pytest.mark.asyncio
@respx.mock
async def test_post_returns_structured_error_on_network_failure():
    respx.post(f"{BASE}/match/default").mock(side_effect=httpx.ConnectError("connection refused"))
    result = await match_person("John Doe")
    assert result["status"] is None
    assert "error" in result
