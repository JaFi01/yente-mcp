# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install all dependencies (including dev)
uv sync

# Run all tests (no live network required)
uv run pytest

# Run a single test
uv run pytest tests/test_tools.py::test_match_person_full

# Run the MCP server locally (requires yente running at YENTE_BASE_URL)
YENTE_BASE_URL=http://localhost:8000 uv run python -m yente_mcp

# Start full stack (elasticsearch + yente + mcp containers)
docker compose up

# Rebuild and restart only the mcp container
docker compose up --build mcp
```

## Architecture

All MCP logic lives in a single file: `src/yente_mcp/server.py`. There is no routing layer, middleware, or abstraction beyond two private HTTP helpers (`_get`, `_post`) that every tool calls directly.

**Request flow:**

```
MCP client → FastMCP (stateless_http, port 8080) → _get/_post helpers → yente HTTP API (port 8000) → ElasticSearch
```

**Key design constraints:**

- `YENTE_BASE_URL`, `YENTE_API_KEY`, and `YENTE_TIMEOUT` are read at **module import time** (top of `server.py`). Tests set `os.environ` before importing to override them. `YENTE_TIMEOUT` defaults to `60` seconds.
- `host="0.0.0.0"` and `port=8080` are passed to the `FastMCP(...)` constructor, not to `mcp.run()`. The installed `mcp` SDK (1.27+) ignores `host`/`port` on `run()`.
- A shared `httpx.AsyncClient` is lazily created on first use via `_get_client()` and reused for connection pooling. It is closed during FastMCP lifespan shutdown (`_lifespan`). Tests reset `server._client = None` via an `autouse` fixture so each test gets a fresh client that respx can intercept.
- `_get` and `_post` catch `httpx.HTTPStatusError` and `httpx.RequestError` and return structured `{"error": "...", "status": <code or None>}` dicts instead of raising.
- All match tools send `properties.name` as a list (`[name]`), then extend with aliases. `match_vessel` also supports `aliases`.
- `match_crypto_wallet` accepts a `limit` parameter (default 5).
- `get_entity` passes `nested` as `str(nested).lower()` — the yente API expects the string `"true"` or `"false"`, not a boolean.
- `get_entity_adjacent` appends `/{prop}` to the path only when `prop` is provided.

**Tests** mock at the `httpx` transport layer via `respx`. They import tool functions directly and `await` them — this works because `@mcp.tool()` returns the original coroutine unchanged.

**Docker Compose startup order:** elasticsearch (healthcheck) → yente (healthcheck, `start_period: 120s` for first-time index) → mcp. The mcp container will not start until yente passes its healthcheck.

**Manifest choice:** `docker-compose.yml` uses `civic.yml` (free, non-commercial datasets). Switch to `commercial.yml` for commercial OpenSanctions data (requires a paid delivery token).
