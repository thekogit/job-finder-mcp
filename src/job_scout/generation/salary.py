"""Deterministic salary normalisation and the minimum-salary filter.

All arithmetic is plain Python. Nothing here calls an LLM, converts currencies or guesses
a contract type. A value is only placed on a comparison basis when the listing says enough
to put it there:

* ``monthly_gross_pln_equivalent``: UoP in PLN, stated as gross ("brutto"), or stated as
  net and converted back to gross with the sourced tax parameters (``uop.py``).
* ``uop_monthly_net_estimate``: the same UoP bands as take-home pay (net stated, or gross
  converted). An estimate under the assumptions listed in ``uop.py``.
* ``monthly_net_invoice_pln``: B2B, stated as net of VAT ("netto" / "+ VAT"), in PLN.

Anything else keeps its nominal monthly band and is reported, not silently compared.
"""

import logging
import math
from collections.abc import Callable
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from job_scout.generation.salary_constants import (
    HOURS_PER_MONTH,
    MONTHS_PER_YEAR,
    ROUND_TRIP_TOLERANCE,
    WORKING_DAYS_PER_MONTH,
)
from job_scout.generation.uop import uop_monthly_gross_from_net, uop_monthly_net
from job_scout.models import (
    JobOffer,
    SalaryContract,
    SalaryGrossNet,
    SalaryPeriod,
    SalaryRange,
)

logger = logging.getLogger(__name__)

SalaryBasis = Literal["nominal", "uop_gross", "b2b_net"]
SalaryFilterOutcome = Literal["kept", "no_salary", "non_pln", "basis_unavailable", "below_min"]

_MONTHS_PER_PERIOD: dict[SalaryPeriod, float] = {
    SalaryPeriod.HOUR: 1.0 / HOURS_PER_MONTH,
    SalaryPeriod.DAY: 1.0 / WORKING_DAYS_PER_MONTH,
    SalaryPeriod.MONTH: 1.0,
    SalaryPeriod.YEAR: float(MONTHS_PER_YEAR),
}


def to_monthly(value: float, period: SalaryPeriod) -> float:
    """Convert an amount quoted per ``period`` into the per-month amount."""
    return value / _MONTHS_PER_PERIOD[period]


def from_monthly(value: float, period: SalaryPeriod) -> float:
    """Convert a per-month amount into the amount per ``period``."""
    return value * _MONTHS_PER_PERIOD[period]


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=ROUND_TRIP_TOLERANCE)


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float | None = None
    max: float | None = None

    def mapped(self, fn: Callable[[float], float]) -> "Band":
        return Band(
            min=None if self.min is None else fn(self.min),
            max=None if self.max is None else fn(self.max),
        )

    def scaled(self, factor: float) -> "Band":
        return Band(
            min=None if self.min is None else self.min * factor,
            max=None if self.max is None else self.max * factor,
        )

    @property
    def upper(self) -> float | None:
        return self.max if self.max is not None else self.min


class NormalizedSalary(BaseModel):
    """One salary band expressed per hour, month and year, plus its comparison bases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SalaryRange
    hourly: Band
    monthly: Band
    annual: Band
    monthly_gross_pln_equivalent: Band | None = None
    uop_monthly_net_estimate: Band | None = None
    monthly_net_invoice_pln: Band | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        problems: list[str] = []

        # hourly, monthly and annual must describe the same band
        for label, derived in (
            ("hourly x hours/month", self.hourly.scaled(HOURS_PER_MONTH)),
            ("annual / 12", self.annual.scaled(1.0 / MONTHS_PER_YEAR)),
        ):
            if not (_close(derived.min, self.monthly.min) and _close(derived.max, self.monthly.max)):
                problems.append(f"{label} = {derived} does not match monthly {self.monthly}")

        # the band in the listing's own period must survive the round trip
        src = self.source
        back = self.monthly.scaled(_MONTHS_PER_PERIOD[src.period])
        src_min = None if src.min is None else float(src.min)
        src_max = None if src.max is None else float(src.max)
        if not (_close(back.min, src_min) and _close(back.max, src_max)):
            problems.append(f"monthly band converted back to {src.period} = {back} != source")

        is_pln = src.currency == "PLN"
        uop_stated = is_pln and src.contract == SalaryContract.UOP and src.gross_net in (
            SalaryGrossNet.GROSS,
            SalaryGrossNet.NET,
        )
        b2b_net = is_pln and src.contract == SalaryContract.B2B and src.gross_net == SalaryGrossNet.NET
        gross_eq, net_est = self.monthly_gross_pln_equivalent, self.uop_monthly_net_estimate
        if (gross_eq is not None) != uop_stated or (net_est is not None) != uop_stated:
            problems.append(
                "monthly_gross_pln_equivalent and uop_monthly_net_estimate are defined only for "
                "UoP PLN bands stated as gross or net"
            )
        elif gross_eq is not None and net_est is not None:
            stated = gross_eq if src.gross_net == SalaryGrossNet.GROSS else net_est
            if stated != self.monthly:
                problems.append(f"the stated UoP band must equal the monthly band ({src.gross_net})")
            back = gross_eq.mapped(uop_monthly_net)
            if not (_close(back.min, net_est.min) and _close(back.max, net_est.max)):
                problems.append(f"net of the gross equivalent {back} != net estimate {net_est}")
        if (self.monthly_net_invoice_pln is not None) != b2b_net:
            problems.append("monthly_net_invoice_pln is only defined for B2B net PLN bands")
        elif self.monthly_net_invoice_pln is not None and self.monthly_net_invoice_pln != self.monthly:
            problems.append("monthly_net_invoice_pln must equal the monthly band")

        if problems:
            raise ValueError("; ".join(problems))
        return self


def normalize_salary(salary: SalaryRange) -> NormalizedSalary:
    source_band = Band(
        min=None if salary.min is None else float(salary.min),
        max=None if salary.max is None else float(salary.max),
    )
    monthly = source_band.scaled(1.0 / _MONTHS_PER_PERIOD[salary.period])
    is_pln = salary.currency == "PLN"
    gross_equiv: Band | None = None
    net_estimate: Band | None = None
    if is_pln and salary.contract == SalaryContract.UOP:
        if salary.gross_net == SalaryGrossNet.GROSS:
            gross_equiv, net_estimate = monthly, monthly.mapped(uop_monthly_net)
        elif salary.gross_net == SalaryGrossNet.NET:
            gross_equiv, net_estimate = monthly.mapped(uop_monthly_gross_from_net), monthly
    net_invoice = (
        monthly
        if is_pln
        and salary.contract == SalaryContract.B2B
        and salary.gross_net == SalaryGrossNet.NET
        else None
    )
    return NormalizedSalary(
        source=salary,
        hourly=monthly.scaled(1.0 / HOURS_PER_MONTH),
        monthly=monthly,
        annual=monthly.scaled(MONTHS_PER_YEAR),
        monthly_gross_pln_equivalent=gross_equiv,
        uop_monthly_net_estimate=net_estimate,
        monthly_net_invoice_pln=net_invoice,
    )


def try_salary_range(**fields: Any) -> SalaryRange | None:
    """Build a SalaryRange, or return None (and log why) when the band is invalid."""
    try:
        return SalaryRange(**fields)
    except ValidationError as err:
        logger.debug("Dropping invalid salary band %r: %s", fields.get("raw"), err)
        return None


def _basis_band(norm: NormalizedSalary, basis: SalaryBasis) -> Band | None:
    if basis == "uop_gross":
        return norm.monthly_gross_pln_equivalent
    if basis == "b2b_net":
        return norm.monthly_net_invoice_pln
    return norm.monthly


def evaluate_salary_min(
    offer: JobOffer, min_pln_month: float, basis: SalaryBasis = "nominal"
) -> SalaryFilterOutcome:
    """Decide whether an offer passes ``salary_min_pln_month`` on the given basis.

    * no salary at all -> excluded (``no_salary``);
    * no PLN band -> excluded (``non_pln``): there is no FX table, so no conversion;
    * no PLN band on the requested basis -> excluded (``basis_unavailable``);
    * otherwise kept when the upper end of any band reaches the minimum.

    ``nominal`` compares the period-converted PLN amount whatever the contract type, so it
    puts B2B net and UoP gross on one axis: callers who need a like-for-like comparison
    pass ``uop_gross`` or ``b2b_net``.
    """
    if not offer.salary:
        return "no_salary"
    pln = [s for s in offer.salary if s.currency == "PLN"]
    if not pln:
        return "non_pln"
    bands = [b for b in (_basis_band(normalize_salary(s), basis) for s in pln) if b is not None]
    if not bands:
        return "basis_unavailable"
    for band in bands:
        upper = band.upper
        if upper is not None and upper >= min_pln_month:
            return "kept"
    return "below_min"
