# job-scout MCP Server

High-performance, local Model Context Protocol (MCP) server that aggregates, normalizes, deduplicates, and verifies fresh job offers in Warsaw (and remote opportunities open to Poland-based candidates) across Polish and international job boards.

Built per specification **JS-MCP-001 Rev: A**.

---

## Supported Job Boards

| Source ID | Platform | Tier | Status | Notes |
|---|---|---|---|---|
| `pracuj` | Pracuj.pl | 1 | Enabled | Full normalization, dual HTTP/1.1 transport |
| `justjoin` | JustJoin.it | 1 | Enabled | Full normalization, Next.js / API hydration |
| `rocketjobs` | RocketJobs.pl | 1 | Enabled | Full normalization, Next.js / API hydration |
| `nofluffjobs` | NoFluffJobs.com | 1 | Enabled | Always publishes structured salary |
| `bulldogjob` | BulldogJob.pl | 1 | Enabled | IT job board, clean schema parsing |
| `theprotocol` | TheProtocol.it | 1 | Enabled | IT platform (Grupa Pracuj), dual HTTP/1.1 transport |
| `linkedin` | LinkedIn Jobs | 2 | Enabled | Public guest job search endpoint |
| `olx` | OLX.pl Praca | 2 | Enabled | Blue-collar and general jobs in Warsaw |
| `pracapl` | Praca.pl | 2 | Enabled | General job board |
| `solidjobs` | Solid.jobs | 2 | Enabled | High-precision tech jobs with transparent salaries |
| `aplikuj` | Aplikuj.pl | 2 | Enabled | General Polish job board |
| `glassdoor` | Glassdoor | 3 | Disabled | Heavy Cloudflare challenge (clean fallback) |
| `indeed` | Indeed PL | 3 | Disabled | Cloudflare challenge (clean fallback) |

---

## MCP Tools Reference

The server exposes 4 tools over standard stdio transport:

### 1. `search_jobs`
Searches fresh, verified job offers in Warsaw or remote open to Poland.
- **Arguments**:
  - `keywords` (string, optional): Search query (e.g. `"Python"`, `"DevOps"`).
  - `sources` (list of strings, optional): Subset of source IDs to query.
  - `max_age_days` (integer, 1-60, default `14`): Filter postings older than N days.
  - `work_modes` (list of strings, optional): `["onsite", "hybrid", "remote"]`.
  - `salary_min_pln_month` (integer, optional): Filter by monthly PLN gross salary equivalent.
  - `only_with_salary` (boolean, default `false`): Filter only postings with published compensation.
  - `include_metro` (boolean, default `false`): Include Warsaw suburbs (Piaseczno, Pruszków, etc.).
  - `verify_validity` (boolean, default `true`): Concurrently check HTTP 200 and expiration markers.
  - `limit` (integer, 1-200, default `50`): Max offers returned.
  - `offset` (integer, default `0`): Pagination offset.
- **Output**: `SearchResult` object containing normalized jobs and per-source status.

### 2. `get_job_details`
Retrieves full, rich details for a single job offer.
- **Arguments**:
  - `url` (string, required): Offer URL.
- **Output**: Complete `JobOffer` object with expanded description, requirements, tech stack, and salary.

### 3. `check_validity`
Batch verification of current online validity and expiry markers for up to 50 URLs.
- **Arguments**:
  - `urls` (list of strings, required): URLs to verify.
- **Output**: List of `ValidityResult` (`url`, `is_valid`, `reason`, `checked_at`).

### 4. `list_sources`
Lists all supported platforms, their tier, enablement status, robots.txt status, and health metrics.

---

## Installation & Running

### Requirements
- Python 3.12+
- `uv` packaging tool

### Run Directly
```bash
uv run job-scout
```

### Run Tests
```bash
# Static analysis
uv run ruff check .
uv run mypy --strict src/

# Unit & adapter tests
uv run pytest tests/unit/
uv run pytest tests/adapters/

# MCP protocol tests
uv run pytest tests/mcp/

# Live smoke tests
uv run pytest -m live tests/live/
```

---

## Antigravity (agy) Integration

In `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "job-scout": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\szpon\\CodeProjects\\side\\job-finder-mcp",
        "run",
        "job-scout"
      ],
      "env": {}
    }
  }
}
```

Verify connection:
```bash
agy mcp list
```

---

## Storage & Logging

- **Database**: SQLite database stored at `~/.job-scout/jobs.db` with WAL mode and automatic deduplication across platforms.
- **Logs**:
  - `stderr` for runtime logs (stdio protocol hygiene guarantees 0 logs on stdout).
  - File log at `~/.job-scout/server.log`.
