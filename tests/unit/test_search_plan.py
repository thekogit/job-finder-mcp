from datetime import date, datetime

import pytest
from pydantic import ValidationError

from job_scout.generation.search_plan import (
    BoardTask,
    DateWindow,
    SearchPlan,
    build_plan,
    execute_plan,
)
from job_scout.models import (
    WARSAW_TZ,
    JobOffer,
    SearchQuery,
    SourceFetchStatus,
    SourceReport,
    ValidityResult,
)
from job_scout.registry import AdapterRegistry

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=WARSAW_TZ)


class FakeCatalog:
    def enabled_source_ids(self, enabled_overrides: dict[str, bool] | None = None) -> list[str]:
        return ["justjoin", "nofluffjobs"]


def _offer(source: str, n: int) -> JobOffer:
    return JobOffer(
        id=f"{source}-{n}",
        link=f"https://example.com/{source}/{n}",
        source=source,
        title=f"Job {n}",
        description="desc",
        first_seen_at=NOW.isoformat(),
        last_checked_at=NOW.isoformat(),
    )


def test_plan_snapshot_for_fixed_query() -> None:
    query = SearchQuery(keywords="python", max_age_days=7, limit=10)
    plan = build_plan(query, FakeCatalog(), now=NOW)

    snapshot = [
        (t.id, t.source, t.kind, t.depends_on, t.date_window.since, t.date_window.until)
        for t in plan.tasks
    ]
    assert snapshot == [
        ("listing:justjoin", "justjoin", "listing", (), date(2026, 11, 1), date(2026, 11, 8)),
        ("listing:nofluffjobs", "nofluffjobs", "listing", (), date(2026, 11, 1), date(2026, 11, 8)),
        (
            "validity:*",
            "*",
            "validity",
            ("listing:justjoin", "listing:nofluffjobs"),
            date(2026, 11, 1),
            date(2026, 11, 8),
        ),
    ]
    assert [[t.id for t in layer] for layer in plan.layers()] == [
        ["listing:justjoin", "listing:nofluffjobs"],
        ["validity:*"],
    ]
    # The plan is plain data: it round-trips through JSON unchanged.
    assert SearchPlan.model_validate_json(plan.model_dump_json()) == plan


def test_plan_is_deterministic_and_respects_explicit_sources() -> None:
    query = SearchQuery(sources=["pracuj", "pracuj", "olx"], verify_validity=False)
    first = build_plan(query, FakeCatalog(), now=NOW)
    assert first == build_plan(query, FakeCatalog(), now=NOW)
    assert [t.id for t in first.tasks] == ["listing:pracuj", "listing:olx"]


def test_date_window_rejects_reversed_range() -> None:
    with pytest.raises(ValidationError, match="is after"):
        DateWindow(since=date(2026, 11, 9), until=date(2026, 11, 8))


def _task(task_id: str, depends_on: tuple[str, ...] = ()) -> BoardTask:
    window = DateWindow(since=date(2026, 11, 1), until=date(2026, 11, 8))
    return BoardTask(
        id=task_id,
        source="justjoin",
        kind="listing",
        query=SearchQuery(),
        date_window=window,
        depends_on=depends_on,
    )


def test_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown dependencies"):
        SearchPlan(query=SearchQuery(), tasks=(_task("a", ("missing",)),), created_at=NOW)


def test_plan_rejects_cycle() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        SearchPlan(
            query=SearchQuery(),
            tasks=(_task("a", ("b",)), _task("b", ("a",))),
            created_at=NOW,
        )


def test_plan_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        SearchPlan(query=SearchQuery(), tasks=(_task("a"), _task("a")), created_at=NOW)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_listing(
        self, source_id: str, query: SearchQuery
    ) -> tuple[list[JobOffer], SourceReport]:
        self.calls.append(f"listing:{source_id}")
        if source_id == "broken":
            raise RuntimeError("adapter exploded")
        offers = [_offer(source_id, i) for i in range(3)]
        return offers, SourceReport(id=source_id, status=SourceFetchStatus.OK, count=3)

    async def check_validity(self, urls: list[str]) -> list[ValidityResult]:
        self.calls.append("validity")
        return [
            ValidityResult(url=u, is_valid=not u.endswith("/1"), checked_at=NOW.isoformat())
            for u in urls
        ]


async def test_executor_runs_layers_in_order_and_reports_failed_sources() -> None:
    query = SearchQuery(sources=["justjoin", "broken", "olx"], limit=50)
    plan = build_plan(query, FakeCatalog(), now=NOW)
    runner = FakeRunner()
    seen_by_hook: list[int] = []

    def after_listings(offers: list[JobOffer]) -> list[JobOffer]:
        seen_by_hook.append(len(offers))
        return offers

    execution = await execute_plan(plan, runner, after_listings=after_listings)

    assert runner.calls[-1] == "validity"
    assert set(runner.calls[:-1]) == {"listing:justjoin", "listing:broken", "listing:olx"}
    assert seen_by_hook == [6]  # hook ran once, after all listings, before validity
    reports = {r.id: r for r in execution.reports}
    assert set(reports) == {"justjoin", "broken", "olx"}  # the failed source is not dropped
    assert reports["broken"].status == SourceFetchStatus.ERROR
    assert reports["broken"].error == "adapter exploded"
    # validity removed the two offers whose URL ends in /1
    assert len(execution.offers) == 4
    assert all(not o.link.endswith("/1") for o in execution.offers)


async def test_registry_run_listing_reports_unknown_source() -> None:
    offers, report = await AdapterRegistry().run_listing("nope", SearchQuery())
    assert offers == []
    assert report.status == SourceFetchStatus.ERROR
    assert "not found" in (report.error or "")
