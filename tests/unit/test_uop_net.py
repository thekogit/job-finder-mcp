"""UoP gross <-> net for tax year 2026.

Expected values are hand arithmetic from the statutory parameters in salary_constants.py,
e.g. for 10 000 zł/month: social = 120 000 x 13.71% = 16 452; health = 9% x 103 548
= 9 319.32; PIT = 12% x (120 000 - 16 452 - 3 000) - 3 600 = 8 465.76;
net = 120 000 - 16 452 - 9 319.32 - 8 465.76 = 85 762.92 per year.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from job_scout.generation.salary import normalize_salary
from job_scout.generation.uop import uop_annual, uop_monthly_gross_from_net, uop_monthly_net
from job_scout.models import SalaryContract, SalaryGrossNet, SalaryRange


def test_employee_contributions_match_the_government_example() -> None:
    # biznes.gov.pl "Ile kosztuje zatrudnienie pracownika" example at the 2026 minimum
    # wage (4 806 zł): pension 469.07, disability 72.09, sickness 117.75 per month.
    b = uop_annual(4806)
    assert (b.pension / 12).quantize(Decimal("0.01")) == Decimal("469.07")
    assert (b.disability / 12).quantize(Decimal("0.01")) == Decimal("72.09")
    assert (b.sickness / 12).quantize(Decimal("0.01")) == Decimal("117.75")


def test_first_bracket() -> None:
    b = uop_annual(10_000)
    assert b.social == Decimal("16452.00")
    assert b.health == Decimal("9319.3200")
    assert b.tax_base == Decimal("100548.00")
    assert b.pit == Decimal("8465.7600")
    assert b.annual_net == Decimal("85762.9200")
    assert uop_monthly_net(10_000) == pytest.approx(7146.91)


def test_second_bracket_and_contribution_cap() -> None:
    # 360 000 zł/year: pension and disability stop at the 282 600 zł cap, sickness does not.
    b = uop_annual(30_000)
    assert b.pension == Decimal("27581.76")
    assert b.disability == Decimal("4239.000")
    assert b.sickness == Decimal("8820.00")
    assert b.health == Decimal("28742.3316")
    assert b.pit == Decimal("73634.9568")
    assert b.annual_net == Decimal("216981.9516")


def test_commuter_costs_lower_the_tax() -> None:
    assert uop_annual(10_000, commuter=True).pit == uop_annual(10_000).pit - Decimal("72")


def test_tax_never_negative() -> None:
    assert uop_annual(1_000).pit == 0


def test_unknown_tax_year_is_refused() -> None:
    with pytest.raises(KeyError, match="2031"):
        uop_annual(10_000, year=2031)


@given(st.floats(min_value=4806, max_value=200_000, allow_nan=False))
def test_net_to_gross_inverts_gross_to_net(gross: float) -> None:
    net = uop_monthly_net(gross)
    assert uop_monthly_gross_from_net(net) == pytest.approx(gross, abs=0.01)


@given(st.floats(min_value=4806, max_value=200_000), st.floats(min_value=1, max_value=5_000))
def test_net_increases_with_gross(gross: float, raise_by: float) -> None:
    assert uop_monthly_net(gross + raise_by) > uop_monthly_net(gross)


def test_normalized_uop_gross_gets_a_net_estimate() -> None:
    band = SalaryRange(
        min=10_000, max=30_000, contract=SalaryContract.UOP, gross_net=SalaryGrossNet.GROSS, raw="x"
    )
    norm = normalize_salary(band)
    assert norm.uop_monthly_net_estimate is not None
    assert norm.uop_monthly_net_estimate.min == pytest.approx(7146.91)
    assert norm.monthly_gross_pln_equivalent == norm.monthly


def test_normalized_uop_net_gets_a_gross_equivalent() -> None:
    band = SalaryRange(
        min=7146.91, contract=SalaryContract.UOP, gross_net=SalaryGrossNet.NET, raw="7146,91 netto"
    )
    norm = normalize_salary(band)
    assert norm.monthly_gross_pln_equivalent is not None
    assert norm.monthly_gross_pln_equivalent.min == pytest.approx(10_000, abs=0.01)
    assert norm.uop_monthly_net_estimate == norm.monthly


def test_b2b_and_unknown_contracts_get_no_uop_estimate() -> None:
    for contract in (SalaryContract.B2B, SalaryContract.UNKNOWN):
        band = SalaryRange(min=10_000, contract=contract, gross_net=SalaryGrossNet.GROSS, raw="x")
        assert normalize_salary(band).uop_monthly_net_estimate is None
