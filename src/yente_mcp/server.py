import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

YENTE_BASE_URL = os.getenv("YENTE_BASE_URL", "http://yente:8000")
YENTE_API_KEY = os.getenv("YENTE_API_KEY", "")

mcp = FastMCP(
    "yente-mcp",
    instructions=(
        "OpenSanctions screening server. Use match_* tools for KYC/AML compliance "
        "checks against sanctions, PEP and watchlist data. Use search_entities for "
        "exploratory lookups. Use get_entity for full profiles including sanctions "
        "details and relationships."
    ),
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=8080,
)


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if YENTE_API_KEY:
        h["Authorization"] = f"ApiKey {YENTE_API_KEY}"
    return h


async def _get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{YENTE_BASE_URL}{path}", params=params, headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{YENTE_BASE_URL}{path}", json=body, headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


# ── Group 1: Health & metadata ────────────────────────────────────────────────

@mcp.tool()
async def health_check() -> dict:
    """Check liveness of the yente API.

    Use this to verify that the yente service is up and reachable before
    running screening queries.
    """
    return await _get("/healthz")


@mcp.tool()
async def get_status() -> dict:
    """Return yente version information and index statistics.

    Use to confirm the running yente version and the state of the loaded
    datasets (entity counts, last update time).
    """
    return await _get("/")


@mcp.tool()
async def list_datasets() -> dict:
    """List all datasets available in this yente instance.

    Returns metadata for every loaded dataset including name, title, entity
    counts, and coverage dates. Use to discover which dataset scopes are
    available before calling search or match tools.
    """
    return await _get("/datasets")


@mcp.tool()
async def get_dataset(dataset: str) -> dict:
    """Return metadata for a single dataset.

    Args:
        dataset: Dataset name/scope (e.g. "default", "sanctions", "peps",
                 "us_ofac_sdn", "eu_fsf").
    """
    return await _get(f"/datasets/{dataset}")


# ── Group 2: Search ───────────────────────────────────────────────────────────

@mcp.tool()
async def search_entities(
    query: str,
    dataset: str = "default",
    schema: str | None = None,
    limit: int = 10,
    offset: int = 0,
    sort: str = "score:desc",
) -> dict:
    """Full-text search for entities in a dataset.

    Performs a Lucene query against the yente index. Suitable for
    exploratory lookups (e.g. "find all entities related to ACME Corp").

    NOT suitable for compliance screening — use match_* tools for KYC/AML
    checks, as they apply fuzzy name-matching algorithms and return scored
    results with a threshold.

    Args:
        query: Lucene query string (e.g. "Vladimir Putin" or "name:Gazprom").
        dataset: Dataset scope to search (default: "default" which includes all).
        schema: Entity type filter — Person, Company, Vessel, Organization, etc.
        limit: Maximum number of results (default: 10).
        offset: Pagination offset (default: 0).
        sort: Sort order, e.g. "score:desc", "name:asc" (default: "score:desc").
    """
    params: dict[str, Any] = {"q": query, "limit": limit, "offset": offset, "sort": sort}
    if schema is not None:
        params["schema"] = schema
    return await _get(f"/search/{dataset}", params=params)


# ── Group 3: Match (KYC/AML screening) ───────────────────────────────────────

@mcp.tool()
async def match_person(
    name: str,
    dataset: str = "default",
    birth_date: str | None = None,
    nationality: str | None = None,
    id_number: str | None = None,
    aliases: list[str] | None = None,
    threshold: float = 0.5,
    limit: int = 5,
) -> dict:
    """Screen a person against sanctions, PEP and watchlist data.

    Sends a fuzzy name-matching query to yente. Higher threshold reduces
    false positives but may miss partial name matches.

    Args:
        name: Primary full name of the person.
        dataset: Dataset scope (default: "default").
        birth_date: Date of birth in ISO format (YYYY-MM-DD).
        nationality: ISO 3166-1 alpha-2 country code for nationality.
        id_number: National ID or passport number.
        aliases: Additional names or spellings to include in matching.
        threshold: Minimum match score 0–1 (default: 0.5).
        limit: Maximum number of matches returned (default: 5).
    """
    properties: dict[str, Any] = {"name": [name]}
    if aliases:
        properties["name"].extend(aliases)
    if birth_date is not None:
        properties["birthDate"] = birth_date
    if nationality is not None:
        properties["nationality"] = nationality
    if id_number is not None:
        properties["idNumber"] = id_number
    body = {
        "queries": {"q": {"schema": "Person", "properties": properties}},
        "threshold": threshold,
        "limit": limit,
    }
    return await _post(f"/match/{dataset}", body)


@mcp.tool()
async def match_company(
    name: str,
    dataset: str = "default",
    country: str | None = None,
    registration_number: str | None = None,
    aliases: list[str] | None = None,
    threshold: float = 0.5,
    limit: int = 5,
) -> dict:
    """Screen a company against sanctions and watchlist data.

    Args:
        name: Primary registered name of the company.
        dataset: Dataset scope (default: "default").
        country: ISO 3166-1 alpha-2 country code for incorporation country.
        registration_number: Company registration or tax number.
        aliases: Additional names or trading names.
        threshold: Minimum match score 0–1 (default: 0.5).
        limit: Maximum number of matches returned (default: 5).
    """
    properties: dict[str, Any] = {"name": [name]}
    if aliases:
        properties["name"].extend(aliases)
    if country is not None:
        properties["country"] = country
    if registration_number is not None:
        properties["registrationNumber"] = registration_number
    body = {
        "queries": {"q": {"schema": "Company", "properties": properties}},
        "threshold": threshold,
        "limit": limit,
    }
    return await _post(f"/match/{dataset}", body)


@mcp.tool()
async def match_vessel(
    name: str,
    dataset: str = "default",
    flag: str | None = None,
    imo_number: str | None = None,
    mmsi: str | None = None,
    threshold: float = 0.5,
    limit: int = 5,
) -> dict:
    """Screen a vessel against sanctions data.

    Args:
        name: Vessel name.
        dataset: Dataset scope (default: "default").
        flag: Flag state as ISO 3166-1 alpha-2 country code.
        imo_number: IMO vessel identification number.
        mmsi: Maritime Mobile Service Identity number.
        threshold: Minimum match score 0–1 (default: 0.5).
        limit: Maximum number of matches returned (default: 5).
    """
    properties: dict[str, Any] = {"name": [name]}
    if flag is not None:
        properties["flag"] = flag
    if imo_number is not None:
        properties["imoNumber"] = imo_number
    if mmsi is not None:
        properties["mmsi"] = mmsi
    body = {
        "queries": {"q": {"schema": "Vessel", "properties": properties}},
        "threshold": threshold,
        "limit": limit,
    }
    return await _post(f"/match/{dataset}", body)


@mcp.tool()
async def match_crypto_wallet(
    address: str,
    currency: str | None = None,
    dataset: str = "default",
    threshold: float = 0.5,
) -> dict:
    """Screen a cryptocurrency wallet address against sanctions data.

    Args:
        address: Public blockchain address / public key.
        currency: Cryptocurrency ticker symbol (e.g. "BTC", "ETH").
        dataset: Dataset scope (default: "default").
        threshold: Minimum match score 0–1 (default: 0.5).
    """
    properties: dict[str, Any] = {"publicKey": address}
    if currency is not None:
        properties["currency"] = currency
    body = {
        "queries": {"q": {"schema": "CryptoWallet", "properties": properties}},
        "threshold": threshold,
        "limit": 5,
    }
    return await _post(f"/match/{dataset}", body)


@mcp.tool()
async def match_bulk(
    queries: dict[str, dict],
    dataset: str = "default",
    threshold: float = 0.5,
    limit: int = 5,
) -> dict:
    """Batch screening — screen multiple entities in a single API call.

    Each query is a FollowTheMoney entity object with a schema and properties.
    Results are keyed by the same query IDs.

    Args:
        queries: Map of query_id → FtM entity, e.g.:
                 {"p1": {"schema": "Person", "properties": {"name": ["John Doe"]}},
                  "c1": {"schema": "Company", "properties": {"name": ["Acme Ltd"]}}}
        dataset: Dataset scope (default: "default").
        threshold: Minimum match score 0–1 (default: 0.5).
        limit: Maximum matches per query (default: 5).
    """
    body = {"queries": queries, "threshold": threshold, "limit": limit}
    return await _post(f"/match/{dataset}", body)


# ── Group 4: Entities ─────────────────────────────────────────────────────────

@mcp.tool()
async def get_entity(entity_id: str, nested: bool = True) -> dict:
    """Retrieve a full entity profile by OpenSanctions canonical ID.

    Use this after a match or search hit to get the complete profile including
    all sanctions programs, ownership relationships, family member links,
    addresses, and source dataset references.

    Args:
        entity_id: OpenSanctions canonical ID, e.g. "NK-aU5ybkbRFJucf8YMwsJvDw".
        nested: If True (default), embed related entities inline. If False,
                return only IDs for related entities (faster, smaller response).
    """
    params = {"nested": str(nested).lower()}
    return await _get(f"/entities/{entity_id}", params=params)


@mcp.tool()
async def get_entity_adjacent(
    entity_id: str,
    prop: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List entities adjacent (related) to a given entity.

    Use to explore the network around a sanctioned entity — e.g. retrieve all
    sanctions records, ownership stakes, or family members.

    Args:
        entity_id: OpenSanctions canonical ID.
        prop: Relationship property to filter by (e.g. "sanctions",
              "ownershipOwner", "familyMember"). If omitted, returns all
              adjacent entities grouped by property.
        limit: Maximum results (default: 20).
        offset: Pagination offset (default: 0).
    """
    path = f"/entities/{entity_id}/adjacent"
    if prop is not None:
        path = f"{path}/{prop}"
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    return await _get(path, params=params)


# ── Group 5: Reconciliation ───────────────────────────────────────────────────

@mcp.tool()
async def reconcile(
    queries: dict[str, dict],
    dataset: str = "default",
) -> dict:
    """Reconcile entity names using the OpenRefine reconciliation protocol.

    Sends a batch of name queries and returns ranked candidate matches using
    the standard OpenRefine API format. Useful for data enrichment workflows
    and entity deduplication.

    Args:
        queries: OpenRefine reconciliation query objects keyed by query ID, e.g.:
                 {"q0": {"query": "Vladimir Putin", "type": "Person", "limit": 3}}
        dataset: Dataset scope (default: "default").
    """
    body = {"queries": queries}
    return await _post(f"/reconcile/{dataset}", body)
