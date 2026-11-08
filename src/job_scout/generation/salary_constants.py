"""Constants for salary conversion: period conventions and statutory tax parameters.

Every statutory value below was read in the primary act on 2026-11-08 (official PDFs from
the Sejm ELI API, api.sejm.gov.pl / eli.gov.pl). Values are keyed by tax year because a
2027 PIT change is in the Sejm; add a year only once its acts are published.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# Period factors. These are a calculation convention, not a statutory value: the
# Polish working-time norm changes month by month with the number of working days, so a
# real month can have more or fewer hours than this. Board "per hour" B2B rates are
# usually quoted against the same 8 h x 21 days convention, which is why it is used here
# (and why the original filter used 168 h and 21 days).
HOURS_PER_DAY: Final = 8
WORKING_DAYS_PER_MONTH: Final = 21
HOURS_PER_MONTH: Final = HOURS_PER_DAY * WORKING_DAYS_PER_MONTH  # 168
MONTHS_PER_YEAR: Final = 12

# Tolerance for the round-trip invariant (hour -> month -> year -> month), in currency units.
ROUND_TRIP_TOLERANCE: Final = 0.01

USUS_2026 = "https://api.sejm.gov.pl/eli/acts/DU/2026/199/text.pdf"  # social insurance act, t.j. Dz.U. 2026 poz. 199
CAP_2026 = "https://api.sejm.gov.pl/eli/acts/MP/2025/1206/text.pdf"  # M.P. 2025 poz. 1206
HEALTH_2025 = "https://api.sejm.gov.pl/eli/acts/DU/2025/1461/text.pdf"  # health-care act, t.j. Dz.U. 2025 poz. 1461
PIT_2026 = "https://api.sejm.gov.pl/eli/acts/DU/2026/592/text.pdf"  # PIT act, t.j. Dz.U. 2026 poz. 592


@dataclass(frozen=True)
class UopTaxParams:
    """Employee-side parameters for one tax year (umowa o pracę, single employer)."""

    year: int
    pension_rate: Decimal
    disability_rate: Decimal
    sickness_rate: Decimal
    pension_disability_annual_cap: Decimal
    health_rate: Decimal
    kup_annual: Decimal
    kup_annual_commuter: Decimal
    pit_threshold: Decimal
    pit_low_rate: Decimal
    pit_high_rate: Decimal
    pit_tax_reducing_amount: Decimal
    sources: dict[str, str]
    checked: str


TAX_PARAMS: Final[dict[int, UopTaxParams]] = {
    2026: UopTaxParams(
        year=2026,
        pension_rate=Decimal("0.0976"),
        disability_rate=Decimal("0.015"),
        sickness_rate=Decimal("0.0245"),
        pension_disability_annual_cap=Decimal("282600"),
        health_rate=Decimal("0.09"),
        kup_annual=Decimal("3000"),
        kup_annual_commuter=Decimal("3600"),
        pit_threshold=Decimal("120000"),
        pit_low_rate=Decimal("0.12"),
        pit_high_rate=Decimal("0.32"),
        pit_tax_reducing_amount=Decimal("3600"),
        sources={
            "pension_rate": f"u.s.u.s. art. 22 ust. 1 pkt 1 (19.52%) split equally by art. 16 ust. 1 ({USUS_2026})",
            "disability_rate": f"u.s.u.s. art. 16 ust. 1b: insured 1.5%, payer 6.5% ({USUS_2026})",
            "sickness_rate": f"u.s.u.s. art. 22 ust. 1 pkt 3, financed wholly by the insured per art. 16 ust. 2 ({USUS_2026})",
            "pension_disability_annual_cap": f"M.P. 2025 poz. 1206 under u.s.u.s. art. 19 ust. 1 and 10 ({CAP_2026})",
            "health_rate": f"health act art. 79 ust. 1; base per art. 81 ust. 1, 5 (no 30x cap), 6 (minus employee social contributions) ({HEALTH_2025})",
            "kup_annual": f"PIT act art. 22 ust. 2 pkt 1: 250 zł/month, max 3000 zł/year ({PIT_2026})",
            "kup_annual_commuter": f"PIT act art. 22 ust. 2 pkt 3: 300 zł/month, max 3600 zł/year ({PIT_2026})",
            "pit_scale": f"PIT act art. 27 ust. 1: to 120 000 zł 12% minus 3600 zł; above, 10 800 zł + 32% of the excess ({PIT_2026})",
            "deductions": f"PIT act art. 26 ust. 1 pkt 2 lit. b deducts employee social contributions; art. 27b (health deduction) repealed ({PIT_2026})",
        },
        checked="2026-11-08",
    ),
}
DEFAULT_TAX_YEAR: Final = 2026
