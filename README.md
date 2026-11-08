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
  - `salary_min_pln_month` (integer, optional): Minimum monthly salary in PLN. **Behaviour change (2026-11-08):** offers without a salary, and offers whose salary is only in another currency, are now *excluded* and counted in `salary_filter` (previously they passed silently, and 5 000 EUR passed as 5 000 PLN).
  - `salary_basis` (`"nominal"` | `"uop_gross"` | `"b2b_net"`, default `"nominal"`): What the minimum is compared with. `nominal` uses the period-converted PLN amount whatever the contract, so B2B net and UoP gross share one axis. `uop_gross` keeps only UoP bands stated as gross; `b2b_net` keeps only B2B bands stated as net of VAT.
  - `only_with_salary` (boolean, default `false`): Filter only postings with published compensation.
  - `include_metro` (boolean, default `false`): Include Warsaw suburbs (Piaseczno, Pruszków, etc.).
  - `verify_validity` (boolean, default `true`): Concurrently check HTTP 200 and expiration markers.
  - `limit` (integer, 1-200, default `50`): Max offers returned.
  - `offset` (integer, default `0`): Pagination offset.
  - `return_plan` (boolean, default `false`): Include the typed search plan that was executed.
- **Output**: `SearchResult` with normalized jobs, one status row per planned source (a board that failed is reported as `error`, not dropped), `salary_filter` (what the salary minimum excluded and why) and, on request, `plan`.

### 2. `get_job_details`
Retrieves full, rich details for a single job offer.
- **Arguments**:
  - `url` (string, required): Offer URL.
- **Output**: Complete `JobOffer` object with expanded description, requirements, tech stack, and salary. `seniority` and `work_mode` carry a verbatim quote from the listing (`seniority_evidence`, `work_mode_evidence`) or stay empty; see *Grounded extraction* below.

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

# Offline tests (unit, adapters, MCP hygiene, evals/skew)
uv run pytest -m "not live"

# Live smoke tests (hit the real boards)
uv run pytest -m live tests/live/
```

### Configuration
Copy `.env.example` to `.env`. `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` enable LLM grounding in `get_job_details` (any OpenAI-compatible endpoint; this project uses Ollama Cloud). Without them the server runs deterministic extraction only.

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

---

## Search planning

`search_jobs` first builds a `SearchPlan` (`src/job_scout/generation/search_plan.py`): frozen Pydantic models for the query, one `listing` task per board with its date window, and a `validity` task that depends on every listing task. The plan validator rejects duplicate task ids, unknown dependencies and cycles. `build_plan` is pure, so the same query and clock give the same plan. `execute_plan` runs the plan in topological layers (one `asyncio.gather` per layer). Filtering, persistence and deduplication run between the listing layer and the validity layer, so the validity check still covers at most `limit` URLs. Adapters fetch detail pages inside their listing call, so there are no separate `detail` tasks yet (DEVIATIONS.md, DEV-003).

## Salary validation

`SalaryRange` rejects bands with `min > max`, non-positive amounts, an unsupported ISO 4217 code or an empty `raw`. A board band that fails is dropped and logged instead of crashing the parse. `NormalizedSalary` (`src/job_scout/generation/salary.py`) holds each band per hour, month and year, and its `@model_validator` re-checks that they agree: hourly × 168 = monthly, monthly × 12 = annual, and the listing's own period survives the round trip within 0.01. The 8 h × 21 days factor is a calculation convention, documented in `salary_constants.py`, not a statutory value.

Comparison bases are only filled when the listing says enough: `monthly_gross_pln_equivalent` for UoP gross PLN, `monthly_net_invoice_pln` for B2B net PLN. There is no FX conversion and no guess at the B2B tax form. UoP gross-to-net is **not implemented**: the 2026 ZUS/PIT parameters it needs have not yet been confirmed against primary sources (DEVIATIONS.md, DEV-004).

## Grounded extraction

`seniority` and `work_mode` are filled in two layers (`src/job_scout/generation/grounded.py`):

1. Deterministic: a seniority keyword in the title (PL/UA/EN, e.g. `Senior`, `Młodszy`, `Старший`) is its own quote. Titles that name two levels ("Mid/Senior") are left empty.
2. LLM, only for fields still empty, and only in `get_job_details` when `LLM_*` is configured. The model must return each value with a quote. A `@model_validator` checks that the quote is a substring of the listing after whitespace/NBSP normalisation only (no case folding, no translation). A failed check is sent back to the model verbatim; after at most 2 retries, any field still without a valid quote is `null` (`seniority_confidence: "not_found"`). A structured value from the board is never overridden. Responses are cached on disk, keyed by model and prompt.

Limitation: the validator proves that a quote *exists* in the listing, not that it *supports* the value. In the run below, "na Lotnisku Chopina" ("at Chopin Airport") was the quote for `onsite`. Judging support needs the step-5 judge and human labels, which do not exist yet.

## Skew monitoring

`evals/skew/` (entry point `python -m evals.skew.run`):

- **Structural**: fingerprints the key paths and JSON types of every JSON-LD `JobPosting`, `__NEXT_DATA__` and JSON API payload (lists collapse to `[]`; id-like and Apollo-cache keys collapse to `<id>`), and counts offer links on HTML listings. Each run is diffed against the committed baselines in `evals/skew/baselines/` and alerts on `missing_path`, `renamed_key`, `casing_change`, `container_change` (list ↔ dict), `type_change` and `link_drop`.
- **Semantic**: embeds requirement strings, clusters them deterministically, and flags clusters with no near neighbour in the baseline as emerging skills. The embedder is EmbeddingGemma 2 (`unsloth/embeddinggemma-2-GGUF`, file `embeddinggemma-2-Q8_0.gguf`, SHA256 `6f1bd4ac…aed8bc`) served locally by llama.cpp. A word TF-IDF embedder is kept as the comparison baseline. Vectors are cached on disk. The weights are not part of this repository; see the [GGUF card](https://huggingface.co/unsloth/embeddinggemma-2-GGUF) and the [base model card](https://huggingface.co/google/embeddinggemma-2) for the licence, which links the Gemma terms and the Gemma Prohibited Use Policy.

```bash
# offline (CI): fixtures, TF-IDF
uv run python -m evals.skew.run --fixtures
# with EmbeddingGemma (tested with llama.cpp build b12192, CPU)
llama-server -m models/embeddinggemma-2-Q8_0.gguf --embeddings --host 127.0.0.1 --port 8091
uv run python -m evals.skew.run --fixtures --embedder gemma
# weekly LIVE run against the boards
uv run python -m evals.skew.run --weekly --embedder gemma
```

## Results

Every number below comes from a command run in this repository on 2026-11-08; the full outputs are linked.

| What | Result | Command | Output |
|---|---|---|---|
| Salary reconciliation: board-published bands (SolidJobs API, JSON-LD) extracted, equal to the board's numbers, internally consistent and round-tripping | **33/33** | `python -m evals.salary_reconciliation` | [salary_reconciliation.md](evals/results/salary_reconciliation.md) |
| Grounded extraction with `beam:cloud` on 19 detail fixtures (PL/EN, plus one Ukrainian description): passed on first attempt / grounded within 2 retries / abstained | **17/19** / 19/19 / 0 | `python -m evals.grounding_eval` | [grounding.md](evals/results/grounding.md) |
| Kept quotes re-checked as verbatim substrings | 22/22 | (same) | (same) |
| Structural skew: synthetic mutations (renamed key, list → dict, casing) detected; alerts on unmutated fixtures | **36/36**; 0 | `python -m evals.skew.run --fixtures --embedder gemma` | [example-fixtures.md](reports/skew/example-fixtures.md) |
| Semantic skew: injected synthetic topics (mixed EN/PL/UA) flagged, best row per setup: EmbeddingGemma centred / raw / TF-IDF | 4/4 / 0/4 / 2/4 | `python -m evals.skew.experiment` | [semantic_injection.md](evals/skew/results/semantic_injection.md) |

Read with care:

- Salary: no fixture states gross or net, so the UoP-gross and B2B-net bases were never exercised on real data.
- Ukrainian: one listing so far (`tests/fixtures/pracuj/detail_4.html`). Its stored description is a company introduction that states neither seniority nor work mode, and the model returned null for both. That is a correct abstention, but it is not yet evidence that Ukrainian quotes are extracted well.
- Grounding: these are pass rates against the substring rule, not accuracy. There are no human labels; the 9/9 seniority agreement with the title rule is agreement, not correctness.
- Semantic skew: the thresholds were picked from the same sweep (in-sample) and the topics are synthetic. EmbeddingGemma needs its vectors centred on the baseline mean: raw cosines are anisotropic (random fixture pairs average about 0.84), and uncentred it flagged nothing.
- First live run (`python -m evals.skew.run --weekly --embedder gemma --limit 3`, 2026-11-08, 11 enabled boards, about 2 minutes). Structural: JSON-LD `employmentType` changed from a string to a list on justjoin and rocketjobs, which the adapters turn into a malformed `contract_types` entry (a real bug the monitor surfaced, not yet fixed). Some optional-looking fields are gone on bulldogjob, theprotocol and solidjobs; no adapter reads them. `link_drop` alerts on linkedin and olx are unconfirmed: that run fingerprinted non-2xx responses too, which has since been fixed. Semantic: 3 clusters flagged as new against the fixture baseline (SAP CO cost planning, MLOps/MLflow, and "LinkedIn" page chrome, now filtered as noise).
- Eval judge (κ, precision, recall): *pending*; needs human labels.
