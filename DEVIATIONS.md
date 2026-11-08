# DEVIATIONS LOG (JS-MCP-001)

This log records any deviation from manual specifications as required by Section 0.2 and Section 2.5.

| ID | Section | Deviation | Reason | Approved By |
|---|---|---|---|---|
| DEV-001 | 3.1 | Dual HTTP/2 and HTTP/1.1 client transport with automatic fallback | Grupa Pracuj (`pracuj.pl`, `theprotocol.it`) uses Akamai bot management that returns HTTP 403 when negotiating HTTP/2 with Python httpx (fingerprinted h2 settings/frames), while responding HTTP 200 over HTTP/1.1. Added HTTP/1.1 transport routing for these hosts and auto-fallback on 403. | Operator (Automatic Section 0.2 rule) |

| DEV-002 | GRANDE PLAN Part I §2 | New planning/validation/grounding code lives in `src/job_scout/generation/`, not a top-level `src/generation/`; evals and skew monitors live in top-level `evals/`. | Keeps one installable package with one import root; `evals/` is tooling, not part of the server. | Owner (work plan §3, 2026-11-07) |
| DEV-003 | Work plan step 1 | `build_plan` emits `listing` and `validity` tasks only; no per-offer `detail` tasks. The validity task depends on all listing tasks and runs once on the filtered, deduplicated result. | Every adapter fetches detail pages inside `search()`; splitting that out needs an adapter API change across 13 boards. Running validity per board would multiply requests (up to `limit` per board instead of `limit` in total). | Agent, 2026-11-08 (pending owner review) |
| DEV-004 | Work plan step 2 | The optional B2B net estimate (`B2BAssumptions`) is not implemented, and the UoP calculator leaves out the art. 83 health cap. UoP gross ↔ net itself was implemented on 2026-11-08 from primary acts (consolidated texts Dz.U. 2026 poz. 199 and 592, Dz.U. 2025 poz. 1461; M.P. 2025 poz. 1206). | B2B net depends on the tax form and ZUS tier, which listings never state. The art. 83 cap needs the PIT rules in force on 2021-12-31, which have not been sourced, and it only binds at low wages. | Owner request, 2026-11-08 |
| DEV-005 | Work plan step 4 | Semantic skew centres EmbeddingGemma vectors on the baseline mean before taking cosines. | Raw vectors are anisotropic on this data (random fixture pairs average about 0.84 cosine); uncentred, 0/4 injected topics were flagged at any threshold tried. See `evals/skew/results/semantic_injection.md`. | Agent, 2026-11-08 |
