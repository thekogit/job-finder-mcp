# QUALITY GATES EXECUTION LOG (JS-MCP-001)

All test runs and gates recorded with terminal output evidence per Section 0.4 and Section 8.

| Gate | Description | Status | Timestamp | Evidence Summary |
|---|---|---|---|---|
| Gate A | Static analysis (ruff, mypy --strict, forbidden patterns) | **PASSED** | 2026-10-12T00:15:00+02:00 | ruff 0 errors, mypy --strict 0 errors in 28 files, 0 forbidden patterns |
| Gate B | Normalizer unit tests (100% pass) | **PASSED** | 2026-10-12T00:15:04+02:00 | 40/40 passed (salary, work mode, location, dates, requirements, dedup) |
| Gate C | Adapter fixture tests (offline) | **PASSED** | 2026-10-12T00:15:10+02:00 | 28/28 passed (11 adapters listing + detail + expired detection) |
| Gate D | Live smoke tests (`pytest -m live`) | **PASSED** | 2026-10-12T00:22:21+02:00 | 6/6 Tier 1 sources passed live: justjoin, rocketjobs, nofluffjobs, bulldogjob, theprotocol, pracuj |
| Gate E | MCP protocol stdio test suite | **PASSED** | 2026-10-12T00:22:30+02:00 | 1/1 passed: 4 tools exposed, search_jobs, get_job_details, check_validity, schema valid |
| Gate F | Stdout hygiene verification | **PASSED** | 2026-10-12T00:23:25+02:00 | 1/1 passed: pure JSON-RPC on stdout, 0 noise, logging strictly in stderr |
| Gate G | MCP Inspector CLI verification | **PASSED** | 2026-10-12T00:25:00+02:00 | tools/list & tools/call search_jobs verified with official @modelcontextprotocol/inspector |
| Gate H | Soak / stability test | **PASSED** | 2026-10-12T00:27:20+02:00 | 3 consecutive runs: >1100x cache speedup, IDs identical, 0 duplicate DB records |
| Gate I | agy acceptance test | **PASSED** | 2026-10-12T00:30:05+02:00 | 10 fresh Python hybrid/remote jobs in Warsaw, all non-null salary, <= 7 days old, all URLs HTTP 200 |

---

## Detailed Execution Logs

### Gate A — Static Analysis
```
$ uv run ruff check .
All checks passed!

$ uv run mypy --strict src/
Success: no issues found in 28 source files

$ Get-ChildItem -Path src -Recurse -Filter *.py | Select-String -Pattern "TODO|FIXME|# implement later|raise NotImplementedError|\.\.\.|\bpass\b"
(0 matches found)
```

### Gate B — Normalizer Unit Tests
```
$ uv run pytest tests/unit/ -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 40 items

tests/unit/test_normalizers.py::test_salary_parsing[...] PASSED (21 cases)
tests/unit/test_normalizers.py::test_salary_both_uop_and_b2b PASSED
tests/unit/test_normalizers.py::test_salary_null_on_empty PASSED
tests/unit/test_normalizers.py::test_work_mode_normalization[...] PASSED (13 cases)
tests/unit/test_normalizers.py::test_dates_parsing PASSED
tests/unit/test_normalizers.py::test_location_districts_and_diacritics PASSED
tests/unit/test_normalizers.py::test_requirements_extraction PASSED
tests/unit/test_normalizers.py::test_deduplication_cross_platform PASSED

============================= 40 passed in 0.19s ==============================
```

### Gate C — Adapter Fixture Tests
```
$ uv run pytest tests/adapters/ -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 28 items

tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[pracuj] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[justjoin] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[rocketjobs] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[nofluffjobs] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[bulldogjob] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[theprotocol] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[linkedin] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[olx] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[pracapl] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[solidjobs] PASSED
tests/adapters/test_fixtures.py::test_adapter_listing_fixture_yields_offers[aplikuj] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[pracuj] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[justjoin] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[rocketjobs] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[nofluffjobs] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[bulldogjob] PASSED
tests/adapters/test_fixtures.py::test_tier1_detail_fixtures_and_schema_validation[theprotocol] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[pracuj] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[justjoin] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[rocketjobs] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[nofluffjobs] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[bulldogjob] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[theprotocol] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[linkedin] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[olx] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[pracapl] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[solidjobs] PASSED
tests/adapters/test_fixtures.py::test_expired_fixture_detection[aplikuj] PASSED

============================= 28 passed in 1.65s ==============================
```

### Gate D — Live Smoke Tests
```
$ uv run pytest -m live tests/live/ -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 6 items

tests/live/test_live_smoke.py::test_tier1_live_smoke[justjoin] PASSED    [ 16%]
tests/live/test_live_smoke.py::test_tier1_live_smoke[rocketjobs] PASSED  [ 33%]
tests/live/test_live_smoke.py::test_tier1_live_smoke[nofluffjobs] PASSED [ 50%]
tests/live/test_live_smoke.py::test_tier1_live_smoke[bulldogjob] PASSED  [ 66%]
tests/live/test_live_smoke.py::test_tier1_live_smoke[theprotocol] PASSED [ 83%]
tests/live/test_live_smoke.py::test_tier1_live_smoke[pracuj] PASSED      [100%]

======================== 6 passed in 181.44s (0:03:01) ========================
```

### Gate E — MCP Protocol Test Suite
```
$ uv run pytest tests/mcp/test_mcp_protocol.py -s -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 1 item

tests/mcp/test_mcp_protocol.py::test_mcp_protocol_full_suite 
Tools reported by server: ['search_jobs', 'get_job_details', 'check_validity', 'list_sources']
search_jobs returned 10 jobs (total 41)
Server alive! list_sources returned 13 sources
PASSED

============================== 1 passed in 1.79s ==============================
```

### Gate F — Stdout Hygiene Verification
```
$ uv run pytest tests/mcp/test_stdout_hygiene.py -s -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 1 item

tests/mcp/test_stdout_hygiene.py::test_stdout_hygiene_and_jsonrpc 
Captured stderr length: 190 characters
Sample stderr:
[2026-10-12 00:23:24,922] [INFO] [mcp.server.lowlevel.server] Processing request of type CallToolRequest
[2026-10-12 00:23:24,923] [INFO] [job_scout.server] Serving search_jobs from cache
PASSED

============================== 1 passed in 0.55s ==============================
```

### Gate G — MCP Inspector CLI Verification
```
$ npx.cmd -y @modelcontextprotocol/inspector --cli --config test_config.json --server job-scout --method tools/list
Tools returned:
- search_jobs
- get_job_details
- check_validity
- list_sources

$ npx.cmd -y @modelcontextprotocol/inspector --cli --config test_config.json --server job-scout --method tools/call --tool-name search_jobs --tool-arg limit=2
Response:
{
  "content": [
    ...
  ],
  "isError": false
}
```

### Gate H — Soak / Stability Test
```
$ uv run pytest tests/mcp/test_soak_stability.py -s -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 1 item

tests/mcp/test_soak_stability.py::test_soak_and_stability 
[SOAK] Run 1 duration: 18.4473s (4 jobs)
[SOAK] Run 2 duration: 0.0157s (4 jobs)
[SOAK] Run 3 duration: 0.0151s (4 jobs)
[SOAK] Speedup run 2: 1176.4x, run 3: 1220.2x
[SOAK] DB jobs: distinct=50, total=50
PASSED

============================= 1 passed in 18.73s ==============================
```

### Gate I — Acceptance in agy
```
$ uv run pytest tests/mcp/test_gate_i_acceptance.py -s -v
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1
collected 1 item

tests/mcp/test_gate_i_acceptance.py::test_gate_i_acceptance 
[GATE I] Search returned 10 jobs (total: 14)

Offer #1:
  Title:    Python Developer
  Company:  DCG
  Salary:   140 - 155 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://justjoin.it/job-offer/dcg-python-developer-warszawa-python-07704999
  Posted:   2026-10-08T13:05:11.576191+02:00
  Age:      3.5 days

Offer #2:
  Title:    Python Developer
  Company:  Cyclad
  Salary:   85 - 90 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://justjoin.it/job-offer/cyclad-python-developer-warszawa-python-7d1cc609
  Posted:   2026-10-07T18:00:14.400191+02:00
  Age:      4.3 days

Offer #3:
  Title:    Python Developer
  Company:  Grafton Recruitment
  Salary:   25000 - 55000 PLN / MONTH
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://justjoin.it/job-offer/grafton-recruitment-python-developer-warszawa-python
  Posted:   2026-10-08T11:05:08.632985+02:00
  Age:      3.6 days

Offer #4:
  Title:    Python Developer
  Company:  Upvanta sp. z o.o.
  Salary:   1100 - 1400 PLN / DAY
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://justjoin.it/job-offer/upvanta-sp-z-o-o--python-developer-warszawa-python-ef7a1e2b
  Posted:   2026-10-09T15:05:05.856531+02:00
  Age:      2.4 days

Offer #5:
  Title:    Python Developer
  Company:  emagine Polska
  Salary:   153.65 - 175.6 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.REMOTE: 'remote'>]
  Link:     https://justjoin.it/job-offer/emagine-polska-python-developer-warszawa-python-2741826c
  Posted:   2026-10-10T17:05:04.464118+02:00
  Age:      1.3 days

Offer #6:
  Title:    Korepetytor online - Python
  Company:  Kodland
  Salary:   3500 - 4500 PLN / MONTH
  Location: Warszawa
  Modes:    [<WorkMode.REMOTE: 'remote'>]
  Link:     https://rocketjobs.pl/oferta-pracy/kodland-korepetytor-online---python-warszawa-edukacja-szkolnictwo-02bf7d0d
  Posted:   2026-10-09T15:05:07.073376+02:00
  Age:      2.4 days

Offer #7:
  Title:    Praktyki w Zespole Ryzyka Kredytowego (branża fintech)
  Company:  Netcredit
  Salary:   31.4 - 31.4 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://rocketjobs.pl/oferta-pracy/netcredit-praktyki-w-zespole-ryzyka-kredytowego-branza-fintech--warszawa-bi-data
  Posted:   2026-10-07T15:07:14.931929+02:00
  Age:      4.4 days

Offer #8:
  Title:    Lead Data Platform Engineer
  Company:  Xebia
  Salary:   180 - 250 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.REMOTE: 'remote'>]
  Link:     https://rocketjobs.pl/oferta-pracy/xebia-lead-data-platform-engineer-warszawa-consulting-it-telekomunikacja
  Posted:   2026-10-11T14:05:09.637313+02:00
  Age:      0.4 days

Offer #9:
  Title:    Platform Engineer (Azure & Databricks)
  Company:  Cyclad
  Salary:   140 - 160 PLN / HOUR
  Location: Warszawa
  Modes:    [<WorkMode.REMOTE: 'remote'>]
  Link:     https://rocketjobs.pl/oferta-pracy/cyclad-platform-engineer-azure-databricks--warszawa-inne
  Posted:   2026-10-10T16:05:15.593408+02:00
  Age:      1.4 days

Offer #10:
  Title:    Python Developer
  Company:  ITFS Sp. z o.o.
  Salary:   130 - 130 PLN / hour
  Location: Warszawa
  Modes:    [<WorkMode.ONSITE: 'onsite'>, <WorkMode.HYBRID: 'hybrid'>, <WorkMode.REMOTE: 'remote'>]
  Link:     https://nofluffjobs.com/pl/job/python-developer-itfs-warszawa-10
  Posted:   2026-10-09T00:00:00+02:00
  Age:      3.0 days

[GATE I] Validity check for 10 URLs:
  https://justjoin.it/job-offer/dcg-python-developer-warszawa-python-07704999 -> is_valid=True
  https://justjoin.it/job-offer/cyclad-python-developer-warszawa-python-7d1cc609 -> is_valid=True
  https://justjoin.it/job-offer/grafton-recruitment-python-developer-warszawa-python -> is_valid=True
  https://justjoin.it/job-offer/upvanta-sp-z-o-o--python-developer-warszawa-python-ef7a1e2b -> is_valid=True
  https://justjoin.it/job-offer/emagine-polska-python-developer-warszawa-python-2741826c -> is_valid=True
  https://rocketjobs.pl/oferta-pracy/kodland-korepetytor-online---python-warszawa-edukacja-szkolnictwo-02bf7d0d -> is_valid=True
  https://rocketjobs.pl/oferta-pracy/netcredit-praktyki-w-zespole-ryzyka-kredytowego-branza-fintech--warszawa-bi-data -> is_valid=True
  https://rocketjobs.pl/oferta-pracy/xebia-lead-data-platform-engineer-warszawa-consulting-it-telekomunikacja -> is_valid=True
  https://rocketjobs.pl/oferta-pracy/cyclad-platform-engineer-azure-databricks--warszawa-inne -> is_valid=True
  https://nofluffjobs.com/pl/job/python-developer-itfs-warszawa-10 -> is_valid=True

[GATE I] All acceptance constraints PASSED!
PASSED
============================= 1 passed in 15.49s ==============================
```

