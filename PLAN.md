# Implementation Plan: job-scout MCP Server (JS-MCP-001 Rev A)

## Execution Order
1. Section 3: Baseline setup, pyproject.toml, package layout, core models, SQLite store, HTTP client, schemas
2. Section 4 & 5: Source discovery & live reconnaissance (fixtures, robots.txt, endpoint detection)
3. Normalizers & Extractors: salary, work_mode, location, dates, text, requirements, jsonld, nextdata
4. Adapters: Base adapter, Tier 1 (pracuj, justjoin, rocketjobs, nofluffjobs, bulldogjob, theprotocol), Tier 2/3
5. Section 6 & 7: FastMCP server (4 tools: search_jobs, get_job_details, check_validity, list_sources)
6. Section 8: Quality Gates execution & logging to GATES.md
   - Gate A: Static analysis (`ruff check .`, `mypy --strict src/`, forbidden pattern scan)
   - Gate B: Normalizer unit tests (100% pass)
   - Gate C: Adapter fixture offline tests (100% pass)
   - Gate D: Live smoke tests (`pytest -m live`) & SOURCES_STATUS.md
   - Gate E: MCP protocol stdio test suite
   - Gate F: Stdout hygiene verification
   - Gate G: MCP Inspector verification
   - Gate H: Soak and stability test
7. Section 9: agy configuration integration, backup, validation, and acceptance test (Gate I)
8. Section 11: Final deliverables report

## Key Files
- `pyproject.toml`, `README.md`, `PLAN.md`, `DEVIATIONS.md`, `SOURCES_STATUS.md`, `GATES.md`
- `schema/job_offer.schema.json`, `schema/search_result.schema.json`
- `src/job_scout/server.py`, `models.py`, `registry.py`, `http.py`, `store.py`
- `src/job_scout/normalize/{salary,work_mode,location,dates,text,requirements}.py`
- `src/job_scout/extract/{jsonld,nextdata}.py`
- `src/job_scout/adapters/{base,pracuj,justjoin,rocketjobs,nofluffjobs,bulldogjob,theprotocol,...}.py`
- `tests/{conftest.py,unit/,adapters/,mcp/,live/,fixtures/}`
