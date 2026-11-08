"""search_jobs end to end with fake boards: plan -> execute -> filter -> dedup. No network."""

from datetime import datetime
from pathlib import Path

import pytest

from job_scout import server
from job_scout.models import (
    WARSAW_TZ,
    JobOffer,
    SalaryRange,
    SearchQuery,
    SourceFetchStatus,
    SourceReport,
    ValidityResult,
)
from job_scout.normalize.salary import parse_salary
from job_scout.store import JobStore

NOW_ISO = datetime.now(WARSAW_TZ).isoformat()


def _offer(n: int, salary: list[SalaryRange] | None, title: str = "Python Developer") -> JobOffer:
    return JobOffer(
        id=f"id{n}",
        link=f"https://justjoin.it/job-offer/{n}",
        source="justjoin",
        title=f"{title} {n}",
        company=f"Company {n}",
        location="Warszawa",
        description="Opis stanowiska",
        salary=salary,
        posted_at=NOW_ISO,
        first_seen_at=NOW_ISO,
        last_checked_at=NOW_ISO,
    )


class FakeRegistry:
    def get_adapter(self, source_id: str) -> object:
        return object()

    def enabled_source_ids(self, enabled_overrides: dict[str, bool] | None = None) -> list[str]:
        return ["justjoin", "broken"]

    async def run_listing(
        self, source_id: str, query: SearchQuery
    ) -> tuple[list[JobOffer], SourceReport]:
        if source_id == "broken":
            return [], SourceReport(id="broken", status=SourceFetchStatus.ERROR, error="boom")
        offers = [
            _offer(1, parse_salary("20 000 - 25 000 zł netto + VAT (B2B)"), "Senior Python Developer"),
            _offer(2, parse_salary("8 000 - 9 000 zł brutto UoP")),
            _offer(3, [SalaryRange(min=6_000, max=7_000, currency="EUR", raw="6000-7000 EUR")]),
            _offer(4, None),
        ]
        return offers, SourceReport(id="justjoin", status=SourceFetchStatus.OK, count=len(offers))

    async def check_validity(self, urls: list[str]) -> list[ValidityResult]:
        return [ValidityResult(url=u, is_valid=True, checked_at=NOW_ISO) for u in urls]


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server, "registry", FakeRegistry())
    monkeypatch.setattr(server, "store", JobStore(tmp_path / "jobs.db"))


async def test_search_jobs_reports_salary_exclusions_and_plan(fake_server: None) -> None:
    result = await server.search_jobs(salary_min_pln_month=15_000, return_plan=True)

    assert [j.id for j in result.jobs] != []
    assert {j.title for j in result.jobs} == {"Senior Python Developer 1"}
    assert result.salary_filter is not None
    report = result.salary_filter
    assert (report.kept, report.excluded_below_min, report.excluded_non_pln, report.excluded_no_salary) == (1, 1, 1, 1)

    # the failed board is reported, not dropped
    assert {r.id: r.status for r in result.sources} == {
        "justjoin": SourceFetchStatus.OK,
        "broken": SourceFetchStatus.ERROR,
    }
    assert result.plan is not None
    assert [t["id"] for t in result.plan["tasks"]] == ["listing:justjoin", "listing:broken", "validity:*"]

    # deterministic grounding ran: seniority comes with its verbatim quote
    job = result.jobs[0]
    assert job.seniority == "senior"
    assert job.seniority_evidence is not None and job.seniority_evidence.quote == "Senior"


async def test_uop_gross_basis_excludes_b2b(fake_server: None) -> None:
    result = await server.search_jobs(
        salary_min_pln_month=5_000, salary_basis="uop_gross", verify_validity=False
    )
    assert {j.title for j in result.jobs} == {"Python Developer 2"}
    assert result.salary_filter is not None
    assert result.salary_filter.excluded_basis_unavailable == 1
    assert result.plan is None
