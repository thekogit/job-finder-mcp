"""Salary reconciliation on the recorded fixtures.

    python -m evals.salary_reconciliation

For every salary band a board publishes as structured data in the fixtures (SolidJobs API
``salaryRange``; JSON-LD ``baseSalary`` on detail pages) this checks:

1. extracted: the adapter produced a valid ``SalaryRange`` for it (not dropped);
2. matches board: the band's min/max equal the board's own numbers;
3. consistent: ``NormalizedSalary`` validates (hourly x 168 = monthly, monthly x 12 = annual);
4. round trip: the monthly band converted back to the board's period equals the board's
   numbers within 0.01.

A band is *reconciled* when all four hold. Writes ``evals/results/salary_reconciliation.md``.
"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evals.fixture_offers import FIXTURES_DIR, fixture_offers, solidjobs_offers
from job_scout.extract.jsonld import extract_job_posting_jsonld
from job_scout.generation.salary import from_monthly, normalize_salary
from job_scout.generation.salary_constants import ROUND_TRIP_TOLERANCE
from job_scout.models import JobOffer, SalaryPeriod

OUT = Path("evals/results/salary_reconciliation.md")


@dataclass
class Row:
    origin: str
    board_min: float | None
    board_max: float | None
    period: str
    currency: str
    contract: str
    checks: dict[str, bool]
    note: str = ""

    @property
    def reconciled(self) -> bool:
        return all(self.checks.values())


def _period(text: str) -> SalaryPeriod:
    lower = text.lower()
    if "hour" in lower:
        return SalaryPeriod.HOUR
    if "day" in lower:
        return SalaryPeriod.DAY
    if "year" in lower:
        return SalaryPeriod.YEAR
    return SalaryPeriod.MONTH


def _check(origin: str, offer: JobOffer, board_min: Any, board_max: Any, period: SalaryPeriod, currency: str) -> Row:
    bmin = None if board_min is None else float(board_min)
    bmax = None if board_max is None else float(board_max)
    checks = {"extracted": False, "matches_board": False, "consistent": False, "round_trip": False}
    row = Row(origin, bmin, bmax, period.value, currency, "-", checks)
    if not offer.salary:
        row.note = "no band extracted"
        return row
    band = offer.salary[0]
    row.contract = band.contract.value
    checks["extracted"] = True
    checks["matches_board"] = (
        band.period == period
        and band.currency == currency
        and (None if band.min is None else float(band.min)) == bmin
        and (None if band.max is None else float(band.max)) == bmax
    )
    try:
        norm = normalize_salary(band)
    except ValidationError as err:
        row.note = str(err).splitlines()[0]
        return row
    checks["consistent"] = True
    back_min = None if norm.monthly.min is None else from_monthly(norm.monthly.min, period)
    back_max = None if norm.monthly.max is None else from_monthly(norm.monthly.max, period)
    checks["round_trip"] = all(
        (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= ROUND_TRIP_TOLERANCE)
        for a, b in ((back_min, bmin), (back_max, bmax))
    )
    return row


def collect() -> list[Row]:
    rows: list[Row] = []
    for raw, offer in solidjobs_offers(FIXTURES_DIR):
        sr = raw.get("salaryRange")
        if isinstance(sr, dict):
            rows.append(
                _check(
                    f"solidjobs/listing_1.json#{raw.get('id')}",
                    offer,
                    sr.get("lowerBound"),
                    sr.get("upperBound"),
                    _period(str(sr.get("salaryPeriod") or "month")),
                    str(sr.get("currency") or "PLN"),
                )
            )
    for origin, offer in fixture_offers(FIXTURES_DIR):
        html = (FIXTURES_DIR / origin).read_text(encoding="utf-8")
        jp = extract_job_posting_jsonld(html) or {}
        base = jp.get("baseSalary")
        if not isinstance(base, dict) or not isinstance(base.get("value"), dict):
            continue
        value = base["value"]
        rows.append(
            _check(
                origin,
                offer,
                value.get("minValue") or value.get("value"),
                value.get("maxValue") or value.get("value"),
                _period(str(value.get("unitText") or "month")),
                str(base.get("currency") or "PLN"),
            )
        )
    return rows


def main() -> int:
    rows = collect()
    reconciled = sum(r.reconciled for r in rows)
    per_check = Counter(name for r in rows for name, ok in r.checks.items() if ok)
    contracts = Counter(r.contract for r in rows)
    lines = [
        "# Salary reconciliation (fixtures)",
        "",
        f"- Date: {date.today().isoformat()}",
        "- Command: `python -m evals.salary_reconciliation`",
        f"- Bands with board-published structured numbers: {len(rows)}",
        f"- **Reconciled: {reconciled}/{len(rows)}**",
        "- Per check: " + ", ".join(f"{k} {per_check[k]}/{len(rows)}" for k in ("extracted", "matches_board", "consistent", "round_trip")),
        "- Contract types as extracted: " + ", ".join(f"{k} {v}" for k, v in sorted(contracts.items())),
        "",
        "Scope: this checks the arithmetic and the extraction against the board's own numbers.",
        "It does not check gross/net: no fixture band states it, so `uop_gross` and `b2b_net`",
        "comparison bases are unavailable for every band here (see README, salary filter).",
        "",
        "| Origin | Board min | Board max | Period | Cur | Contract | Reconciled | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.origin} | {r.board_min} | {r.board_max} | {r.period} | {r.currency} | {r.contract} | "
            f"{'yes' if r.reconciled else 'no: ' + ', '.join(k for k, v in r.checks.items() if not v)} | {r.note} |"
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"bands": len(rows), "reconciled": reconciled}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
