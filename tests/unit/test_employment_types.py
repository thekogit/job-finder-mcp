"""Regression: JSON-LD employmentType may be a string or a list (schema.org allows both).

The 2026-11-08 live skew run saw justjoin and rocketjobs switch from "FULL_TIME" to
["FULL_TIME", "CONTRACTOR"]; adapters then stored the list's repr as one contract type.
"""

from pathlib import Path

import pytest

from job_scout.adapters.justjoin import JustJoinAdapter
from job_scout.adapters.rocketjobs import RocketJobsAdapter
from job_scout.normalize.employment import normalize_employment_types

FIXTURES = Path("tests/fixtures")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FULL_TIME", ["FULL_TIME"]),
        (["FULL_TIME", "CONTRACTOR"], ["FULL_TIME", "CONTRACTOR"]),
        ([" FULL_TIME ", "FULL_TIME", "", None], ["FULL_TIME"]),
        ("", []),
        (None, []),
        ([], []),
        (42, []),
    ],
)
def test_normalize_employment_types(raw: object, expected: list[str]) -> None:
    assert normalize_employment_types(raw) == expected


@pytest.mark.parametrize(
    ("adapter", "board"), [(JustJoinAdapter(), "justjoin"), (RocketJobsAdapter(), "rocketjobs")]
)
def test_adapters_store_each_listed_employment_type(adapter: object, board: str) -> None:
    html = (FIXTURES / board / "detail_1.html").read_text(encoding="utf-8")
    assert '"employmentType":"' in html
    as_list = html.replace('"employmentType":"OTHER"', '"employmentType":["FULL_TIME","CONTRACTOR"]', 1)
    assert as_list != html, "fixture no longer has the employmentType this test rewrites"
    offer = adapter._parse_job_posting(as_list, f"https://example.com/{board}/x")  # type: ignore[attr-defined]
    assert offer.contract_types == ["FULL_TIME", "CONTRACTOR"]
