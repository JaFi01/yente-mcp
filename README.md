# yente-mcp

MCP server wrapping the [yente](https://github.com/opensanctions/yente) self-hosted OpenSanctions API — sanctions, PEP and watchlist screening for KYC/AML workflows.

---

## Architecture

```
MCP client (Claude Desktop / AI agent)
        |
        | Streamable HTTP  :8080
        v
  ┌─────────────┐
  │  yente-mcp  │  (this project)
  └──────┬──────┘
         | HTTP  :8000
         v
  ┌─────────────┐
  │    yente    │  OpenSanctions API
  └──────┬──────┘
         | :9200
         v
  ┌───────────────┐     ┌───────────────────────┐
  │ ElasticSearch │ <── │ OpenSanctions bulk    │
  │    (index)    │     │ data (delivery token) │
  └───────────────┘     └───────────────────────┘
```

All data stays on your own infrastructure — no customer data leaves the deployment.

---

## Tools

| Tool | Description |
|------|-------------|
| `health_check` | Liveness check for the yente API |
| `get_status` | yente version and index statistics |
| `list_datasets` | All available dataset scopes |
| `get_dataset` | Metadata for a single dataset |
| `search_entities` | Full-text exploratory entity search (not for compliance) |
| `match_person` | KYC/AML screening for a person |
| `match_company` | KYC/AML screening for a company |
| `match_vessel` | Screening for a vessel by name / IMO / MMSI |
| `match_crypto_wallet` | Screening for a cryptocurrency wallet address |
| `match_bulk` | Batch screening — multiple entities in one call |
| `get_entity` | Full entity profile by OpenSanctions canonical ID |
| `get_entity_adjacent` | Related entities (sanctions, ownership, family) |
| `reconcile` | OpenRefine reconciliation protocol for data enrichment |

---

## Quick start

**Prerequisites:** Docker, Docker Compose v2, and an OpenSanctions delivery token.

**1. Get a token**

Sign up at https://www.opensanctions.org/api/ for a free trial delivery token.

**2. Configure `.env`**

```bash
cp .env.example .env
# Edit .env and set OPENSANCTIONS_DELIVERY_TOKEN=<your_token>
```

**3. Start all services**

```bash
docker compose up
```

The MCP server will be available at `http://localhost:8080/mcp` once yente finishes indexing (first start takes a few minutes).

---

## Connect to Claude Desktop

Add the following to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "yente-mcp": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

---

## Dataset scopes

| Scope | Contents |
|-------|----------|
| `default` | All datasets combined (broadest coverage) |
| `sanctions` | Global consolidated sanctions list |
| `peps` | Politically Exposed Persons |
| `us_ofac_sdn` | US OFAC Specially Designated Nationals |
| `eu_fsf` | EU Financial Sanctions Files |

---

## Matching vs. search

| | `search_entities` | `match_*` tools |
|---|---|---|
| **Purpose** | Exploratory lookup | KYC/AML compliance screening |
| **Algorithm** | Lucene full-text | Fuzzy name-matching with scoring |
| **Returns** | Ranked list | Scored candidates with threshold |
| **Use when** | Research, enrichment | Customer / transaction screening |

Use `match_*` tools for any compliance decision. `search_entities` does not apply the transliteration and fuzzy matching required for reliable sanctions screening.

---

## Reducing false positives

- Provide `birth_date` for persons — most sanctioned individuals share common names.
- Provide `nationality` or `country` to narrow geographic scope.
- Pass `registration_number` for companies when available.
- Add `aliases` (transliterations, maiden names, former names).
- Increase `threshold` toward `0.7–0.8` for stricter matching.
- Use a narrower `dataset` scope (e.g. `us_ofac_sdn`) when you only need a specific list.

---

## Development

```bash
# Install dependencies (including dev)
uv sync

# Run tests (no live network required)
uv run pytest

# Run the MCP server locally (requires a running yente at YENTE_BASE_URL)
YENTE_BASE_URL=http://localhost:8000 uv run python -m yente_mcp
```

---

## Environment variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENSANCTIONS_DELIVERY_TOKEN` | — | **Yes** | Token for OpenSanctions bulk data delivery |
| `YENTE_BASE_URL` | `http://yente:8000` | No | URL of the yente API |
| `YENTE_API_KEY` | `""` | No | API key if yente is auth-protected |

---

## License

Code: [Apache-2.0](LICENSE)

OpenSanctions data: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free for non-commercial use. Commercial users need a data licence from [OpenSanctions](https://www.opensanctions.org/licensing/).
