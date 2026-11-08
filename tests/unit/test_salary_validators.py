import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from job_scout.generation.salary import (
    NormalizedSalary,
    evaluate_salary_min,
    from_monthly,
    normalize_salary,
    to_monthly,
)
from job_scout.generation.salary_constants import HOURS_PER_MONTH, ROUND_TRIP_TOLERANCE
from job_scout.models import (
    JobOffer,
    SalaryContract,
    SalaryGrossNet,
    SalaryPeriod,
    SalaryRange,
)
from job_scout.normalize.salary import parse_salary

amounts = st.floats(min_value=1.0, max_value=5_000_000.0, allow_nan=False, allow_infinity=False)


@given(hourly=amounts)
def test_hour_month_year_month_round_trip(hourly: float) -> None:
    monthly = to_monthly(hourly, SalaryPeriod.HOUR)
    yearly = from_monthly(monthly, SalaryPeriod.YEAR)
    back = to_monthly(yearly, SalaryPeriod.YEAR)
    assert abs(back - monthly) <= ROUND_TRIP_TOLERANCE
    assert abs(from_monthly(back, SalaryPeriod.HOUR) - hourly) <= ROUND_TRIP_TOLERANCE


@given(
    low=amounts,
    spread=st.floats(min_value=0.0, max_value=100_000.0),
    period=st.sampled_from(list(SalaryPeriod)),
    contract=st.sampled_from(list(SalaryContract)),
    gross_net=st.sampled_from(list(SalaryGrossNet)),
)
def test_normalized_salary_is_always_internally_consistent(
    low: float,
    spread: float,
    period: SalaryPeriod,
    contract: SalaryContract,
    gross_net: SalaryGrossNet,
) -> None:
    band = SalaryRange(
        min=low, max=low + spread, period=period, contract=contract, gross_net=gross_net, raw="x"
    )
    norm = normalize_salary(band)  # the model validator re-checks every relation
    assert norm.monthly.min is not None and norm.hourly.min is not None
    assert abs(norm.hourly.min * HOURS_PER_MONTH - norm.monthly.min) <= ROUND_TRIP_TOLERANCE


def test_known_conversions() -> None:
    hourly = normalize_salary(SalaryRange(min=150, max=180, period=SalaryPeriod.HOUR, raw="150-180 zł/h"))
    assert hourly.monthly.min == pytest.approx(25_200)
    assert hourly.monthly.max == pytest.approx(30_240)
    yearly = normalize_salary(SalaryRange(min=240_000, max=300_000, period=SalaryPeriod.YEAR, raw="r"))
    assert yearly.monthly.min == pytest.approx(20_000)
    daily = normalize_salary(SalaryRange(min=1_000, period=SalaryPeriod.DAY, raw="1000/dzień"))
    assert daily.monthly.min == pytest.approx(21_000)


def test_inconsistent_normalized_salary_is_rejected() -> None:
    good = normalize_salary(SalaryRange(min=10_000, max=12_000, raw="10-12k"))
    tampered = good.model_dump()
    tampered["annual"] = {"min": 1.0, "max": 2.0}
    with pytest.raises(ValidationError, match="does not match monthly"):
        NormalizedSalary.model_validate(tampered)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"min": 20_000, "max": 10_000}, "greater than max"),
        ({"min": -5, "max": 10}, "must be positive"),
        ({"min": 0}, "must be positive"),
        ({}, "at least one of min/max"),
        ({"min": 10, "currency": "ZL"}, "ISO 4217"),
        ({"min": 10, "raw": "   "}, "raw must be non-empty"),
    ],
)
def test_salary_range_validator(fields: dict[str, object], message: str) -> None:
    payload: dict[str, object] = {"raw": "raw text", **fields}
    with pytest.raises(ValidationError, match=message):
        SalaryRange.model_validate(payload)


def test_parser_drops_invalid_band_instead_of_raising() -> None:
    assert parse_salary("20 000 - 10 000 zł") is None


def test_comparison_bases() -> None:
    uop = normalize_salary(parse_salary("12 000 - 15 000 zł brutto UoP")[0])  # type: ignore[index]
    assert uop.monthly_gross_pln_equivalent is not None
    assert uop.monthly_net_invoice_pln is None
    b2b = normalize_salary(parse_salary("20 000 - 25 000 zł netto + VAT (B2B)")[0])  # type: ignore[index]
    assert b2b.monthly_net_invoice_pln is not None
    assert b2b.monthly_gross_pln_equivalent is None
    eur = normalize_salary(SalaryRange(min=5_000, currency="EUR", contract=SalaryContract.UOP, gross_net=SalaryGrossNet.GROSS, raw="5000 EUR"))
    assert eur.monthly_gross_pln_equivalent is None


def _offer(salary: list[SalaryRange] | None) -> JobOffer:
    return JobOffer(
        id="1",
        link="https://example.com/1",
        source="test",
        title="Dev",
        description="d",
        salary=salary,
        first_seen_at="2026-11-08T00:00:00+01:00",
        last_checked_at="2026-11-08T00:00:00+01:00",
    )


def test_salary_min_filter_outcomes() -> None:
    # (c) offers without salary are now excluded
    assert evaluate_salary_min(_offer(None), 10_000) == "no_salary"
    # (a) 5 000 EUR no longer passes as 5 000 PLN
    eur = SalaryRange(min=5_000, max=6_000, currency="EUR", raw="5000-6000 EUR")
    assert evaluate_salary_min(_offer([eur]), 5_000) == "non_pln"
    # (d) hourly rates use the documented 168 h convention
    hourly = SalaryRange(min=100, max=120, period=SalaryPeriod.HOUR, raw="100-120 zł/h")
    assert evaluate_salary_min(_offer([hourly]), 20_000) == "kept"  # 120 x 168 = 20 160
    assert evaluate_salary_min(_offer([hourly]), 20_200) == "below_min"
    # (b) B2B net and UoP gross are only compared on the nominal basis
    b2b = parse_salary("20 000 - 25 000 zł netto + VAT (B2B)")
    assert evaluate_salary_min(_offer(b2b), 15_000, "uop_gross") == "basis_unavailable"
    assert evaluate_salary_min(_offer(b2b), 15_000, "b2b_net") == "kept"
    assert evaluate_salary_min(_offer(b2b), 15_000, "nominal") == "kept"
