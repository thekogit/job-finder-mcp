from datetime import datetime

import pytest

from job_scout.models import (
    WARSAW_TZ,
    JobOffer,
    SalaryContract,
    SalaryGrossNet,
    SalaryPeriod,
    WorkMode,
)
from job_scout.normalize.dates import parse_date
from job_scout.normalize.location import is_warsaw_location
from job_scout.normalize.requirements import normalize_requirements
from job_scout.normalize.salary import parse_salary
from job_scout.normalize.work_mode import normalize_work_mode
from job_scout.store import JobStore


# =====================================================================
# SALARY TESTS (≥ 20 cases, all 5.4 examples included)
# =====================================================================
@pytest.mark.parametrize(
    "raw_input, expected_min, expected_max, expected_cur, expected_period, expected_gn, expected_contract",
    [
        # 5.4 required examples:
        ("10 000 – 15 000 zł", 10000, 15000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("10 000–15 000 PLN brutto / mies.", 10000, 15000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UNKNOWN),
        ("120–150 zł netto (+ VAT) / godz.", 120, 150, "PLN", SalaryPeriod.HOUR, SalaryGrossNet.NET, SalaryContract.B2B),
        ("15k–20k PLN", 15000, 20000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("do 12 000 zł", None, 12000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("od 8 000 zł", 8000, None, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("25 000 - 30 000 PLN + VAT (B2B)", 25000, 30000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.NET, SalaryContract.B2B),
        # Number separators: non-breaking space U+00A0 and U+202F
        ("18\xa0000 - 24\xa0000 PLN", 18000, 24000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("20\u202f000 - 25\u202f000 zł brutto", 20000, 25000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UNKNOWN),
        ("14.000 - 18.000 PLN", 14000, 18000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        # Periods: day, year, hour
        ("1 000 - 1 500 PLN / dzień", 1000, 1500, "PLN", SalaryPeriod.DAY, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("120 000 - 180 000 PLN / rok", 120000, 180000, "PLN", SalaryPeriod.YEAR, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("90 - 120 zł / h", 90, 120, "PLN", SalaryPeriod.HOUR, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        # Currencies: EUR, USD, GBP, CHF
        ("4000 - 6000 EUR", 4000, 6000, "EUR", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("5000 - 8000 USD gross / month", 5000, 8000, "USD", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UNKNOWN),
        ("50 - 70 GBP / hour", 50, 70, "GBP", SalaryPeriod.HOUR, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        ("8000 - 12000 CHF", 8000, 12000, "CHF", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UNKNOWN),
        # Contract types: UoP, UZ, UoD
        ("12 000 - 16 000 zł brutto (Umowa o pracę)", 12000, 16000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UOP),
        ("6 000 - 8 000 zł brutto (Umowa zlecenie)", 6000, 8000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UZ),
        ("5 000 - 7 000 zł (Umowa o dzieło)", 5000, 7000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.UNKNOWN, SalaryContract.UOD),
        # Em-dash
        ("16 000 — 22 000 PLN brutto", 16000, 22000, "PLN", SalaryPeriod.MONTH, SalaryGrossNet.GROSS, SalaryContract.UNKNOWN),
    ],
)
def test_salary_parsing(raw_input, expected_min, expected_max, expected_cur, expected_period, expected_gn, expected_contract):
    res = parse_salary(raw_input)
    assert res is not None
    assert len(res) >= 1
    s = res[0]
    assert s.min == expected_min
    assert s.max == expected_max
    assert s.currency == expected_cur
    assert s.period == expected_period
    assert s.gross_net == expected_gn
    assert s.contract == expected_contract


def test_salary_both_uop_and_b2b():
    raw = "12 000 - 16 000 zł brutto (UoP) | 16 000 - 20 000 zł + VAT (B2B)"
    res = parse_salary(raw)
    assert res is not None
    assert len(res) == 2
    assert res[0].contract == SalaryContract.UOP
    assert res[0].gross_net == SalaryGrossNet.GROSS
    assert res[1].contract == SalaryContract.B2B
    assert res[1].gross_net == SalaryGrossNet.NET


def test_salary_null_on_empty():
    assert parse_salary(None) is None
    assert parse_salary("") is None
    assert parse_salary("Wynagrodzenie do uzgodnienia") is None


# =====================================================================
# WORK MODE TESTS (≥ 12 cases)
# =====================================================================
@pytest.mark.parametrize(
    "raw_input, expected_modes, expect_raw",
    [
        ("praca stacjonarna", [WorkMode.ONSITE], "praca stacjonarna"),
        ("Office", [WorkMode.ONSITE], "Office"),
        ("On-site", [WorkMode.ONSITE], "On-site"),
        ("praca hybrydowa", [WorkMode.HYBRID], "praca hybrydowa"),
        ("Hybrid", [WorkMode.HYBRID], "Hybrid"),
        ("praca zdalna", [WorkMode.REMOTE], "praca zdalna"),
        ("Remote", [WorkMode.REMOTE], "Remote"),
        ("Fully remote", [WorkMode.REMOTE], "Fully remote"),
        ("TELECOMMUTE", [WorkMode.REMOTE], "TELECOMMUTE"),
        ("praca mobilna", [WorkMode.ONSITE], "praca mobilna"),
        ("Hybrid / Remote", [WorkMode.HYBRID, WorkMode.REMOTE], "Hybrid / Remote"),
        ("praca hybrydowa lub w biurze", [WorkMode.ONSITE, WorkMode.HYBRID], "praca hybrydowa lub w biurze"),
        ("dowolny elastyczny czas", None, "dowolny elastyczny czas"),
    ],
)
def test_work_mode_normalization(raw_input, expected_modes, expect_raw):
    modes, raw = normalize_work_mode(raw_input)
    assert modes == expected_modes
    assert raw == expect_raw


# =====================================================================
# DATES TESTS (≥ 12 cases, all 5.8 forms + DST boundary)
# =====================================================================
def test_dates_parsing():
    ref_time = datetime(2026, 10, 11, 14, 0, 0, tzinfo=WARSAW_TZ)

    # 1. Absolute Polish: "Opublikowana: 8 października 2026"
    iso, conf = parse_date("Opublikowana: 8 października 2026", reference_time=ref_time)
    assert conf == "exact"
    assert iso == "2026-10-08T00:00:00+02:00"

    # 2. Month genitives: listopada, grudnia, stycznia, marca
    iso_list, _ = parse_date("15 listopada 2026", reference_time=ref_time)
    assert iso_list == "2026-11-15T00:00:00+01:00"  # Nov is UTC+1 in Poland!

    iso_dec, _ = parse_date("1 grudnia 2026", reference_time=ref_time)
    assert iso_dec == "2026-12-01T00:00:00+01:00"

    iso_jan, _ = parse_date("10 stycznia 2026", reference_time=ref_time)
    assert iso_jan == "2026-01-10T00:00:00+01:00"

    iso_mar, _ = parse_date("5 marca 2026", reference_time=ref_time)
    assert iso_mar == "2026-03-05T00:00:00+01:00"

    # 3. Relative: dzisiaj
    iso_dzi, conf_dzi = parse_date("dzisiaj", reference_time=ref_time)
    assert conf_dzi == "relative"
    assert iso_dzi == "2026-10-11T00:00:00+02:00"

    # 4. Relative: wczoraj
    iso_wcz, conf_wcz = parse_date("wczoraj", reference_time=ref_time)
    assert conf_wcz == "relative"
    assert iso_wcz == "2026-10-10T00:00:00+02:00"

    # 5. Relative: 3 dni temu
    iso_3d, conf_3d = parse_date("3 dni temu", reference_time=ref_time)
    assert conf_3d == "relative"
    assert iso_3d == "2026-10-08T00:00:00+02:00"

    # 6. Relative: dodana 2 tyg. temu
    iso_2w, conf_2w = parse_date("dodana 2 tyg. temu", reference_time=ref_time)
    assert conf_2w == "relative"
    assert iso_2w == "2026-09-27T00:00:00+02:00"

    # 7. Relative: 2 days ago
    iso_2da, conf_2da = parse_date("2 days ago", reference_time=ref_time)
    assert conf_2da == "relative"
    assert iso_2da == "2026-10-09T00:00:00+02:00"

    # 8. ISO format with timezone
    iso_iso, conf_iso = parse_date("2026-10-08T12:30:00+02:00", reference_time=ref_time)
    assert conf_iso == "exact"
    assert iso_iso == "2026-10-08T12:30:00+02:00"

    # 9. Numeric DD.MM.YYYY
    iso_num, conf_num = parse_date("08.10.2026", reference_time=ref_time)
    assert conf_num == "exact"
    assert iso_num == "2026-10-08T00:00:00+02:00"

    # 10. DST Boundary: 2026-10-25 transition day
    # Before DST change (early morning 01:00 CEST -> +02:00)
    iso_before, _ = parse_date("2026-10-25T01:00:00+02:00", reference_time=ref_time)
    assert iso_before == "2026-10-25T01:00:00+02:00"

    # After DST change (2026-10-26 in CET -> +01:00)
    iso_after, _ = parse_date("26 października 2026", reference_time=ref_time)
    assert iso_after == "2026-10-26T00:00:00+01:00"

    # 11. Unknown string
    iso_unk, conf_unk = parse_date("dawno temu", reference_time=ref_time)
    assert conf_unk == "unknown"
    assert iso_unk is None

    # 12. None input
    iso_none, conf_none = parse_date(None)
    assert conf_none == "unknown"
    assert iso_none is None


# =====================================================================
# LOCATION TESTS (districts, diacritics, metro, exclusions)
# =====================================================================
def test_location_districts_and_diacritics():
    # Standard Warsaw
    assert is_warsaw_location("Warszawa")
    assert is_warsaw_location("Warsaw")
    assert is_warsaw_location("warszawa, mazowieckie")

    # Districts with and without diacritics
    assert is_warsaw_location("Mokotów")
    assert is_warsaw_location("mokotow")
    assert is_warsaw_location("Śródmieście")
    assert is_warsaw_location("srodmiescie")
    assert is_warsaw_location("Białołęka")
    assert is_warsaw_location("bialoleka")
    assert is_warsaw_location("Wola")
    assert is_warsaw_location("Żoliborz")
    assert is_warsaw_location("zoliborz")
    assert is_warsaw_location("Praga-Południe")
    assert is_warsaw_location("Praga Poludnie")

    # Other Polish cities (should be False unless remote)
    assert not is_warsaw_location("Kraków")
    assert not is_warsaw_location("Wrocław")
    assert not is_warsaw_location("Gdańsk")

    # Metro suburbs: default False, True when include_metro=True
    assert not is_warsaw_location("Piaseczno", include_metro=False)
    assert is_warsaw_location("Piaseczno", include_metro=True)
    assert is_warsaw_location("Pruszków", include_metro=True)
    assert is_warsaw_location("Konstancin-Jeziorna", include_metro=True)

    # Remote allowances: Poland or EU
    assert is_warsaw_location("Remote, Poland", work_modes=[WorkMode.REMOTE])
    assert is_warsaw_location("Zdalna (Polska)", work_modes=[WorkMode.REMOTE])
    assert is_warsaw_location("Remote (EU)", work_modes=[WorkMode.REMOTE])

    # Remote exclusions: US only, Germany only
    assert not is_warsaw_location("Remote (US only)", work_modes=[WorkMode.REMOTE])
    assert not is_warsaw_location("USA (Remote)", work_modes=[WorkMode.REMOTE])
    assert not is_warsaw_location("Germany only (Remote)", work_modes=[WorkMode.REMOTE])


# =====================================================================
# REQUIREMENTS TESTS (≥ 6 fixture samples)
# =====================================================================
def test_requirements_extraction():
    # 1. Structured requirements
    reqs, nice, conf = normalize_requirements(
        structured_reqs=["Python 3.12+", "PostgreSQL", "Docker"],
        structured_nice=["Kubernetes"],
    )
    assert conf == "structured"
    assert len(reqs) == 3
    assert len(nice) == 1

    # 2. Section headed by "Wymagania:"
    text2 = """
    O firmie:
    Jesteśmy liderem branży IT.

    Wymagania:
    - Minimum 3 lata doświadczenia w Python
    - Znajomość FastAPI i PostgreSQL
    - Doświadczenie z Git

    Oferujemy:
    - Kartę Multisport
    """
    reqs2, nice2, conf2 = normalize_requirements(html_or_text=text2)
    assert conf2 == "section"
    assert len(reqs2) == 3
    assert "Minimum 3 lata doświadczenia w Python" in reqs2

    # 3. Section headed by "Nasze wymagania" and "Mile widziane"
    text3 = """
    Nasze wymagania:
    • 5+ lat w inżynierii danych
    • Biegła znajomość SQL i Spark
    
    Mile widziane:
    • Certyfikat AWS
    • Doświadczenie z dbt
    """
    reqs3, nice3, conf3 = normalize_requirements(html_or_text=text3)
    assert conf3 == "section"
    assert len(reqs3) == 2
    assert len(nice3) == 2

    # 4. Section headed by "Requirements" and "Nice to have"
    text4 = """
    Requirements:
    1. Strong background in Linux
    2. Kubernetes administration
    
    Nice to have:
    1. Terraform skills
    """
    reqs4, nice4, conf4 = normalize_requirements(html_or_text=text4)
    assert conf4 == "section"
    assert len(reqs4) == 2
    assert len(nice4) == 1

    # 5. Section headed by "Nasze oczekiwania"
    text5 = """
    Nasze oczekiwania:
    - Wykształcenie wyższe techniczne
    - Umiejętność pracy w zespole
    """
    reqs5, nice5, conf5 = normalize_requirements(html_or_text=text5)
    assert conf5 == "section"
    assert len(reqs5) == 2

    # 6. Section headed by "Obowiązkowe" (NoFluffJobs pattern)
    text6 = """
    Obowiązkowe:
    - Python
    - Django
    
    Mile widziane:
    - React
    """
    reqs6, nice6, conf6 = normalize_requirements(html_or_text=text6)
    assert conf6 == "section"
    assert len(reqs6) == 2
    assert len(nice6) == 1

    # 7. No requirements found
    text7 = "Tylko opis stanowiska bez listy wymagań."
    reqs7, nice7, conf7 = normalize_requirements(html_or_text=text7)
    assert conf7 == "not_found"
    assert len(reqs7) == 0


# =====================================================================
# DEDUPLICATION TESTS (merge cross-source with also_on)
# =====================================================================
def test_deduplication_cross_platform(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    test_store = JobStore(db_path=db_file)

    offer1 = JobOffer(
        id="hash1",
        link="https://justjoin.it/job-offer/acme-corp-python-dev-warszawa",
        source="justjoin",
        title="Python Developer",
        company="Acme Corp Sp. z o.o.",
        location="Warszawa",
        description="Short description",
        requirements=["Python"],
        salary=None,
        first_seen_at="2026-10-10T10:00:00+02:00",
        last_checked_at="2026-10-10T10:00:00+02:00",
        is_valid=True,
    )

    offer2 = JobOffer(
        id="hash2",
        link="https://www.pracuj.pl/praca/python-developer-warszawa,oferta,99999",
        source="pracuj",
        title="Python Developer",
        company="Acme Corp",
        location="Warszawa, Śródmieście",
        description="Much richer and longer description with details",
        requirements=["Python", "Django"],
        salary=parse_salary("15 000 - 20 000 PLN brutto"),
        first_seen_at="2026-10-11T12:00:00+02:00",
        last_checked_at="2026-10-11T12:00:00+02:00",
        is_valid=True,
    )

    merged = test_store.deduplicate_offers([offer1, offer2])
    assert len(merged) == 1
    primary = merged[0]
    # Primary should be offer2 because it has a salary!
    assert primary.source == "pracuj"
    assert len(primary.salary or []) == 1
    assert "https://justjoin.it/job-offer/acme-corp-python-dev-warszawa" in primary.also_on
