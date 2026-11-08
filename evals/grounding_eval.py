"""Grounded-extraction run on the recorded detail fixtures (calls the configured LLM).

    python -m evals.grounding_eval

Needs LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (environment or .env). Responses are cached
under ``.job-scout/llm_cache/`` (git-ignored), so a rerun with the same model and prompts
makes no API calls and reproduces the numbers.

The LLM is run on every fixture listing, including those the deterministic layer already
grounds, so the LLM layer is measured on its own. What is reported:

* first-attempt pass rate: answers whose quotes all validated on the first try;
* final status after at most 2 corrective retries (grounded / partial / abstained);
* how many non-null fields survived, and an independent re-check that each final quote is
  a verbatim substring of the listing;
* agreement (not accuracy: there are no human labels) between LLM and title-keyword
  seniority where both produced a value.

Writes ``evals/results/grounding.md``.
"""

import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from evals.fixture_offers import FIXTURES_DIR, fixture_offers
from job_scout.generation.grounded import (
    MAX_RETRIES,
    OpenAICompatibleClient,
    deterministic_seniority,
    extract_grounded,
    listing_text,
)
from job_scout.normalize.text import is_verbatim_quote

OUT = Path("evals/results/grounding.md")
CACHE_DIR = Path(".job-scout/llm_cache")


def _error_kind(error: str) -> str:
    if "not an exact substring" in error:
        return "quote not verbatim"
    if "quote is empty" in error:
        return "value without quote"
    if "is null; set both" in error:
        return "quote without value"
    if re.search(r"json|Invalid JSON|EOF", error, re.IGNORECASE):
        return "malformed JSON"
    if "Input should be" in error:
        return "value outside enum"
    return "other"


async def run() -> int:
    os.environ.setdefault("JOB_SCOUT_LLM_CACHE_DIR", str(CACHE_DIR))
    client = OpenAICompatibleClient.from_env()
    if client is None:
        print("LLM_BASE_URL / LLM_API_KEY / LLM_MODEL are not set", file=sys.stderr)
        return 2
    client.cache_dir = CACHE_DIR

    offers = fixture_offers(FIXTURES_DIR)
    statuses: Counter[str] = Counter()
    first_errors: Counter[str] = Counter()
    first_pass = 0
    fields_kept = Counter[str]()
    quotes_rechecked = 0
    quotes_ok = 0
    agree = disagree = 0
    rows: list[str] = []
    for origin, offer in offers:
        text = listing_text(offer)
        outcome = await extract_grounded(text, client)
        statuses[outcome.status] += 1
        if not outcome.attempts[0].errors:
            first_pass += 1
        for err in outcome.attempts[0].errors:
            first_errors[_error_kind(err)] += 1
        f = outcome.fields
        for name, value, quote in (
            ("seniority", f.seniority, f.seniority_quote),
            ("work_mode", f.work_mode, f.work_mode_quote),
        ):
            if value:
                fields_kept[name] += 1
                quotes_rechecked += 1
                quotes_ok += bool(quote and is_verbatim_quote(quote, text))
        det = deterministic_seniority(offer.title)
        if det is not None and f.seniority is not None:
            if det[0] == f.seniority:
                agree += 1
            else:
                disagree += 1
        rows.append(
            f"| {origin} | {outcome.status} | {len(outcome.attempts)} | "
            f"{f.seniority.value if f.seniority else '-'} | {json.dumps(f.seniority_quote, ensure_ascii=False) if f.seniority_quote else '-'} | "
            f"{','.join(m.value for m in f.work_mode) if f.work_mode else '-'} | "
            f"{json.dumps(f.work_mode_quote, ensure_ascii=False) if f.work_mode_quote else '-'} | "
            f"{det[0].value if det else '-'} |"
        )

    n = len(offers)
    lines = [
        "# Grounded extraction (fixtures)",
        "",
        f"- Date: {date.today().isoformat()}",
        "- Command: `python -m evals.grounding_eval`",
        f"- Model: `{client.model}` (OpenAI-compatible endpoint), temperature 0, max {MAX_RETRIES} retries",
        f"- Listings: {n} tier-1 detail fixtures (title + stored description, <= 4 000 chars). "
        "Polish and English, plus one Ukrainian description (pracuj/detail_4.html, recorded "
        "2026-11-08; Polish title).",
        "",
        f"- First-attempt pass (all quotes verbatim on try 1): **{first_pass}/{n}**",
        "- Final status: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())),
        f"- Fields kept: seniority {fields_kept['seniority']}/{n}, work_mode {fields_kept['work_mode']}/{n}",
        f"- Independent re-check of kept quotes: {quotes_ok}/{quotes_rechecked} verbatim",
        f"- Seniority agreement with the title-keyword rule (both non-null): {agree}/{agree + disagree}"
        " (agreement, not accuracy: no human labels)",
        "- First-attempt validation errors by kind: "
        + (", ".join(f"{k} {v}" for k, v in first_errors.most_common()) or "none"),
        "",
        "| Fixture | Status | Attempts | Seniority | Quote | Work mode | Quote | Title rule |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.as_posix())
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
