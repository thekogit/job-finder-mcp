"""UoP (umowa o pracę) gross <-> net, employee side, from the statutory parameters.

Model: one employer, the same gross every month for the whole year, and the tax settled
annually (what the employee keeps after the yearly PIT return), divided by 12. A real
payslip moves during the year: advances are paid monthly, and the 32% bracket and the
contribution cap only start once the yearly totals cross them.

Not modelled (each is listed in ``UopNetBreakdown.assumptions``): PPK, the under-26 and
other PIT reliefs, 50% author's costs, joint filing, the art. 83 health-contribution
cap (it reduces health to a 2021-rules PIT advance and only binds at low wages), and
rounding to full złoty under the Tax Ordinance (differences below 1 zł).
"""

from dataclasses import dataclass
from decimal import Decimal

from job_scout.generation.salary_constants import DEFAULT_TAX_YEAR, TAX_PARAMS, UopTaxParams

ASSUMPTIONS: tuple[str, ...] = (
    "single employer, equal monthly gross for 12 months",
    "annual PIT settlement (individual filing), net averaged over 12 months",
    "standard employee costs (art. 22 ust. 2 pkt 1) unless commuter=True",
    "no PPK, no under-26 or other reliefs, no author's costs",
    "art. 83 health cap (low wages) not applied",
    "no rounding to full złoty",
)


@dataclass(frozen=True)
class UopNetBreakdown:
    year: int
    annual_gross: Decimal
    pension: Decimal
    disability: Decimal
    sickness: Decimal
    health: Decimal
    kup: Decimal
    tax_base: Decimal
    pit: Decimal
    annual_net: Decimal
    assumptions: tuple[str, ...] = ASSUMPTIONS

    @property
    def social(self) -> Decimal:
        return self.pension + self.disability + self.sickness

    @property
    def monthly_net(self) -> Decimal:
        return self.annual_net / 12


def _params(year: int) -> UopTaxParams:
    try:
        return TAX_PARAMS[year]
    except KeyError:
        raise KeyError(f"no sourced UoP tax parameters for {year}") from None


def _pit(tax_base: Decimal, p: UopTaxParams) -> Decimal:
    if tax_base <= p.pit_threshold:
        return max(Decimal(0), tax_base * p.pit_low_rate - p.pit_tax_reducing_amount)
    first_bracket = p.pit_threshold * p.pit_low_rate - p.pit_tax_reducing_amount
    return first_bracket + (tax_base - p.pit_threshold) * p.pit_high_rate


def uop_annual(
    monthly_gross: float | Decimal, year: int = DEFAULT_TAX_YEAR, commuter: bool = False
) -> UopNetBreakdown:
    p = _params(year)
    gross = Decimal(str(monthly_gross)) * 12
    capped = min(gross, p.pension_disability_annual_cap)
    pension = capped * p.pension_rate
    disability = capped * p.disability_rate
    sickness = gross * p.sickness_rate  # the 30x cap covers pension and disability only
    social = pension + disability + sickness
    health = (gross - social) * p.health_rate  # no cap on the health base (art. 81 ust. 5)
    kup = min(gross, p.kup_annual_commuter if commuter else p.kup_annual)
    tax_base = max(Decimal(0), gross - social - kup)
    pit = _pit(tax_base, p)
    return UopNetBreakdown(
        year=year,
        annual_gross=gross,
        pension=pension,
        disability=disability,
        sickness=sickness,
        health=health,
        kup=kup,
        tax_base=tax_base,
        pit=pit,
        annual_net=gross - social - health - pit,
    )


def uop_monthly_net(monthly_gross: float, year: int = DEFAULT_TAX_YEAR, commuter: bool = False) -> float:
    return float(uop_annual(monthly_gross, year, commuter).monthly_net)


def uop_monthly_gross_from_net(
    monthly_net: float, year: int = DEFAULT_TAX_YEAR, commuter: bool = False
) -> float:
    """Invert uop_monthly_net by bisection (net is strictly increasing in gross)."""
    low, high = 0.0, max(1.0, monthly_net) * 3
    while uop_monthly_net(high, year, commuter) < monthly_net:
        high *= 2
    for _ in range(80):
        mid = (low + high) / 2
        if uop_monthly_net(mid, year, commuter) < monthly_net:
            low = mid
        else:
            high = mid
    return (low + high) / 2
