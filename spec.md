# yente-mcp — Technical Specification for Claude Code

## Overview

Build a production-ready MCP (Model Context Protocol) server called **yente-mcp** that wraps the [yente](https://github.com/opensanctions/yente) self-hosted OpenSanctions API and exposes it as MCP tools over **Streamable HTTP** transport.

The project is a standalone Python package delivered as a Docker container. It runs alongside a yente container via Docker Compose. All data stays on the user's own infrastructure — no customer data leaves the deployment.

---

## Repository layout

Create the following file structure from scratch:

```
yente-mcp/
├── src/
│   └── yente_mcp/
│       ├── __init__.py          # empty
│       ├── __main__.py          # entry point: runs mcp with streamable-http on 0.0.0.0:8080
│       └── server.py            # all MCP tools (see Tools section)
├── tests/
│   └── test_tools.py            # pytest tests using respx to mock httpx
├── docker-compose.yml           # elasticsearch + yente + mcp containers
├── Dockerfile                   # builds the mcp container
├── pyproject.toml               # uv-compatible, hatchling build backend
├── .env.example                 # documents all env vars
├── .gitignore
├── LICENSE                      # MIT
└── README.md
```

---

## Technology stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| MCP framework | `mcp[cli]>=1.8.0` (official Anthropic SDK, `FastMCP`) |
| HTTP client | `httpx>=0.27.0` (async) |
| MCP transport | **Streamable HTTP** — `stateless_http=True`, `json_response=True` |
| Container | Docker + Docker Compose v2 |
| Search backend | ElasticSearch 8.19.13 (managed by yente, pinned to match yente's own docker-compose) |
| Package manager | `uv` (used in Dockerfile and dev workflow) |
| Build backend | `hatchling` |
| Test framework | `pytest` + `pytest-asyncio` + `respx` |

---

## `pyproject.toml`

```toml
[project]
name = "yente-mcp"
version = "0.1.0"
description = "MCP server for OpenSanctions / yente – sanctions, PEP and watchlist screening"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.8.0",
    "httpx>=0.27.0",
]

[project.scripts]
yente-mcp = "yente_mcp.server:mcp.run"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/yente_mcp"]

[tool.uv]
dev-dependencies = [
    "pytest>=8.4",          # 8.4+ required by pytest-asyncio 1.x
    "pytest-asyncio>=1.0",  # current major version (1.4.0 as of June 2026)
    "respx>=0.22",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Environment variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `YENTE_BASE_URL` | `http://yente:8000` | No | URL of the yente API (set by docker-compose) |
| `YENTE_API_KEY` | `""` | No | API key if yente is auth-protected |
| `OPENSANCTIONS_DELIVERY_TOKEN` | — | **Yes** | Token for OpenSanctions bulk data delivery. Get at https://www.opensanctions.org/api/ |

Read all env vars at module level in `server.py`:

```python
YENTE_BASE_URL = os.getenv("YENTE_BASE_URL", "http://yente:8000")
YENTE_API_KEY  = os.getenv("YENTE_API_KEY", "")
```

---

## `server.py` — implementation requirements

### FastMCP instance

```python
from mcp.server.fastmcp import FastMCP

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
)
```

### HTTP helpers

Two private async helpers using `httpx.AsyncClient`:

```python
async def _get(path: str, params: dict | None = None) -> Any
async def _post(path: str, body: dict) -> Any
```

Both must:
- Prepend `YENTE_BASE_URL` to `path`
- Set headers: `Accept: application/json`, `Content-Type: application/json`
- If `YENTE_API_KEY` is set, add `Authorization: ApiKey {key}`
- Call `resp.raise_for_status()` before returning `resp.json()`
- Use `timeout=30` for GET, `timeout=60` for POST

### Tools — complete list

Implement all 13 tools below as `async def` decorated with `@mcp.tool()`.
Every tool must have a full docstring explaining purpose, when to use it,
and all parameters. Return type is always `dict`.

#### Group 1: Health & metadata

| Tool | Method | yente endpoint | Notes |
|------|--------|---------------|-------|
| `health_check()` | GET | `/healthz` | Liveness check |
| `get_status()` | GET | `/` | Version + index stats |
| `list_datasets()` | GET | `/datasets` | All available datasets |
| `get_dataset(dataset: str)` | GET | `/datasets/{dataset}` | Metadata for one dataset |

#### Group 2: Search (full-text, exploratory)

**`search_entities`** — GET `/search/{dataset}`

Parameters:
- `query: str` — Lucene query string
- `dataset: str = "default"` — scope
- `schema: str | None = None` — entity type filter (Person, Company, Vessel…)
- `limit: int = 10`
- `offset: int = 0`
- `sort: str = "score:desc"`

Build params dict from all non-None values; pass to `_get`.

Docstring must note: *not suitable for compliance screening — use match_* for that*.

#### Group 3: Match (KYC/AML screening)

All match tools POST to `/match/{dataset}` with body:
```json
{
  "queries": {
    "q": { "schema": "...", "properties": { ... } }
  },
  "threshold": 0.5,
  "limit": 5
}
```

**`match_person`**

Parameters:
- `name: str`
- `dataset: str = "default"`
- `birth_date: str | None = None` → `properties.birthDate`
- `nationality: str | None = None` → `properties.nationality`
- `id_number: str | None = None` → `properties.idNumber`
- `aliases: list[str] | None = None` → appended to `properties.name`
- `threshold: float = 0.5`
- `limit: int = 5`

Schema: `"Person"`

**`match_company`**

Parameters:
- `name: str`
- `dataset: str = "default"`
- `country: str | None = None` → `properties.country`
- `registration_number: str | None = None` → `properties.registrationNumber`
- `aliases: list[str] | None = None` → appended to `properties.name`
- `threshold: float = 0.5`
- `limit: int = 5`

Schema: `"Company"`

**`match_vessel`**

Parameters:
- `name: str`
- `dataset: str = "default"`
- `flag: str | None = None` → `properties.flag`
- `imo_number: str | None = None` → `properties.imoNumber`
- `mmsi: str | None = None` → `properties.mmsi`
- `threshold: float = 0.5`
- `limit: int = 5`

Schema: `"Vessel"`

**`match_crypto_wallet`**

Parameters:
- `address: str` → `properties.publicKey`
- `currency: str | None = None` → `properties.currency`
- `dataset: str = "default"`
- `threshold: float = 0.5`

Schema: `"CryptoWallet"`, hardcoded `limit: 5`

**`match_bulk`** — batch screening, multiple entities in one call

Parameters:
- `queries: dict[str, dict]` — map of query_id → FtM entity object  
  (`{"schema": "...", "properties": {...}}`)
- `dataset: str = "default"`
- `threshold: float = 0.5`
- `limit: int = 5`

Body: `{"queries": queries, "threshold": threshold, "limit": limit}`

#### Group 4: Entities

**`get_entity`**

Parameters:
- `entity_id: str` — OpenSanctions canonical ID, e.g. `NK-aU5ybkbRFJucf8YMwsJvDw`
- `nested: bool = True`

GET `/entities/{entity_id}?nested=true|false`

Pass nested as lowercase string: `str(nested).lower()`

Docstring must explain: use after a match/search hit to get full profile including sanctions, ownership, family relationships.

**`get_entity_adjacent`**

Parameters:
- `entity_id: str`
- `prop: str | None = None` — e.g. `"sanctions"`, `"ownershipOwner"`, `"familyMember"`
- `limit: int = 20`
- `offset: int = 0`

Path: `/entities/{entity_id}/adjacent` — if `prop` provided, append `/{prop}`

#### Group 5: Reconciliation

**`reconcile`**

Parameters:
- `queries: dict[str, dict]` — OpenRefine reconciliation queries
- `dataset: str = "default"`

POST `/reconcile/{dataset}` with `{"queries": queries}`

---

## `__main__.py`

```python
from yente_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

---

## `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv pip install --system --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "yente_mcp"]
```

---

## `docker-compose.yml`

Three services in dependency order:

### `elasticsearch`
- Image: `docker.elastic.co/elasticsearch/elasticsearch:8.19.13`
  _(pinned to exact version from yente's official docker-compose.yml)_
- Environment:
  - `node.name=index`
  - `cluster.name=opensanctions-index`
  - `discovery.type=single-node`
  - `bootstrap.memory_lock=true`
  - `xpack.security.enabled=false`
  - `ES_JAVA_OPTS=-Xms4g -Xmx4g`
- ulimits: `memlock: soft: -1, hard: -1`
- Named volume: `es_data:/usr/share/elasticsearch/data`
- Healthcheck: `curl --fail http://localhost:9200/_cluster/health || exit 1`
- No explicit `restart` (use deploy.restart_policy instead, matching yente's style)

### `yente`
- Image: `ghcr.io/opensanctions/yente:5.4.0`
  _(pinned — `latest` is bad practice in compose; update manually when upgrading)_
- `depends_on: elasticsearch: condition: service_healthy`
- Environment:
  - `YENTE_INDEX_TYPE: "elasticsearch"` ← **required since yente 5.x**
  - `YENTE_INDEX_URL: http://elasticsearch:9200`
  - `YENTE_MANIFEST: /app/manifests/commercial.yml` (or `civic.yml` for non-commercial)
  - `OPENSANCTIONS_DELIVERY_TOKEN: ${OPENSANCTIONS_DELIVERY_TOKEN}`
- Port: `8000:8000`
- Healthcheck: `curl -f http://localhost:8000/healthz`
  — interval 30s, timeout 10s, retries 3, **start_period 120s** (first index takes minutes)
- `restart: unless-stopped`

### `mcp`
- `build: context: . dockerfile: Dockerfile`
- `depends_on: yente: condition: service_healthy`
- Environment:
  - `YENTE_BASE_URL: http://yente:8000`
  - `YENTE_API_KEY: ${YENTE_API_KEY:-}`
- Port: `8080:8080`
- `restart: unless-stopped`

Named volume declaration: `volumes: es_data:`

---

## `tests/test_tools.py`

### Setup

Set `YENTE_BASE_URL` env var **before** importing from `server.py`:

```python
import os
os.environ.setdefault("YENTE_BASE_URL", "http://yente-test:8000")
```

Import all 13 tool functions directly from `yente_mcp.server`.

Define `BASE = "http://yente-test:8000"` for use in all mock URLs.

### Test requirements

Write one `@pytest.mark.asyncio` test per scenario. Decorate each test with `@respx.mock`. Mock the exact HTTP method + URL that the tool calls. Assert on the return value.

Minimum test coverage:

| Test | Mocks | Asserts |
|------|-------|---------|
| `test_health_check` | GET `/healthz` → `{"status": "ok"}` | `result["status"] == "ok"` |
| `test_get_status` | GET `/` → `{"version": "4.0.0"}` | version field present |
| `test_list_datasets` | GET `/datasets` → list of 2 | length == 2 |
| `test_get_dataset` | GET `/datasets/sanctions` | name field |
| `test_search_entities_basic` | GET `/search/default` | `"results" in result` |
| `test_search_entities_with_schema` | GET `/search/sanctions` with schema | schema in first result |
| `test_match_person_minimal` | POST `/match/default` | `"responses" in result` |
| `test_match_person_full` | POST `/match/sanctions` with score 0.92 | score == 0.92 |
| `test_match_company` | POST `/match/default` | responses present |
| `test_match_vessel` | POST `/match/sanctions` | responses present |
| `test_match_crypto_wallet` | POST `/match/default` | responses present |
| `test_match_bulk` | POST `/match/default` | both query IDs in responses |
| `test_get_entity_nested` | GET `/entities/NK-abc` | id == "NK-abc" |
| `test_get_entity_flat` | GET `/entities/NK-abc` | schema == "Person" |
| `test_get_entity_adjacent_all` | GET `/entities/NK-abc/adjacent` | "sanctions" key present |
| `test_get_entity_adjacent_prop` | GET `/entities/NK-abc/adjacent/sanctions` | "count" key present |
| `test_reconcile` | POST `/reconcile/default` | "q0" key in result |

All 17 tests must pass with `pytest`.

---

## `.env.example`

```dotenv
# Required – get free trial at https://www.opensanctions.org/api/
OPENSANCTIONS_DELIVERY_TOKEN=your_token_here

# Optional – only needed if yente is configured with YENTE_API_KEY
YENTE_API_KEY=

# Set automatically by docker-compose – do not change for containerised use
# YENTE_BASE_URL=http://yente:8000
```

---

## `.gitignore`

```
.env
__pycache__/
*.py[cod]
.venv/
dist/
*.egg-info/
.pytest_cache/
```

---

## `README.md` — required sections

1. **Title + one-line description**
2. **Architecture diagram** (ASCII, showing: MCP client → yente-mcp:8080 → yente:8000 → ElasticSearch + data)
3. **Tool table** — all 13 tools with one-line description
4. **Quick start** — 3 steps: prerequisites, configure `.env`, `docker compose up`
5. **Connect to Claude Desktop** — JSON snippet for `claude_desktop_config.json`
6. **Dataset scopes table** — default / sanctions / peps / us_ofac_sdn / eu_fsf
7. **Matching vs. search** — when to use which
8. **Reducing false positives** — bullet list of techniques
9. **Development** — `uv sync`, `pytest`, local run command
10. **Environment variables table**
11. **License note** — MIT code, CC BY-NC 4.0 data

---

## Acceptance criteria

Claude Code must produce a repo where:

1. `pytest` exits 0 with all 17 tests passing — no live network required
2. `docker compose up` starts all three services (assuming a valid `OPENSANCTIONS_DELIVERY_TOKEN` in `.env`)
3. The MCP server is reachable at `http://localhost:8080/mcp` after startup
4. All 13 tools are discoverable via MCP `tools/list`
5. The `mcp` container does not start until `yente` is healthy (`depends_on` with condition)
6. No secrets are committed — `.env` is in `.gitignore`, only `.env.example` is tracked

---

## Important constraints

- **Do not use SSE transport** — it is deprecated. Use `streamable-http` exclusively.
- **Do not use `asyncio.run()` directly** — let FastMCP handle the event loop via `mcp.run()`.
- **Do not hardcode any tokens or API keys** — all secrets via environment variables.
- **All tool functions must be `async def`** — yente calls are always awaited via `httpx.AsyncClient`.
- **One `httpx.AsyncClient` per request** — use `async with httpx.AsyncClient(...) as client:` inside each helper, do not share a client across requests (stateless design).
- **`raise_for_status()` before `resp.json()`** — let HTTP errors propagate as exceptions to the MCP caller.
- Tests use `respx` to mock at the `httpx` transport layer — no monkeypatching of the helper functions themselves.