"""Typed search planning: build an inspectable plan first, then execute it.

``build_plan`` is pure (no I/O, no clock unless you leave ``now`` out) and turns a
``SearchQuery`` into a DAG of ``BoardTask`` objects. ``execute_plan`` runs the DAG in
topological layers, one ``asyncio.gather`` per layer, and always returns one
``SourceReport`` per planned source, including the ones that failed.

Task kinds produced today:

* ``listing``: one per board. The adapters fetch the detail pages inside their listing
  call, so there are no separate ``detail`` tasks yet (DEVIATIONS.md, DEV-003). The kind
  stays in the type so a plan can describe them once adapters expose detail fetching.
* ``validity``: one task that depends on every listing task, because the validity check
  runs on the filtered and deduplicated result, not per board (this keeps the request
  volume the same as before: at most ``limit`` URLs).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from job_scout.models import (
    WARSAW_TZ,
    JobOffer,
    SearchQuery,
    SourceFetchStatus,
    SourceReport,
    ValidityResult,
)

logger = logging.getLogger(__name__)

TaskKind = Literal["listing", "detail", "validity"]
ALL_SOURCES = "*"


class DateWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    since: date
    until: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.since > self.until:
            raise ValueError(f"since ({self.since}) is after until ({self.until})")
        return self


class BoardTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Board id, or '*' for a cross-board task.")
    kind: TaskKind
    query: SearchQuery
    date_window: DateWindow
    depends_on: tuple[str, ...] = ()


def _topological_layers(tasks: Sequence[BoardTask]) -> list[list[BoardTask]]:
    """Kahn's algorithm, grouped by depth. Raises ValueError on a cycle."""
    pending = {t.id: set(t.depends_on) for t in tasks}
    by_id = {t.id: t for t in tasks}
    layers: list[list[BoardTask]] = []
    done: set[str] = set()
    while pending:
        ready = sorted(tid for tid, deps in pending.items() if deps <= done)
        if not ready:
            raise ValueError(f"dependency cycle among tasks: {sorted(pending)}")
        layers.append([by_id[tid] for tid in ready])
        for tid in ready:
            del pending[tid]
        done.update(ready)
    return layers


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: SearchQuery
    tasks: tuple[BoardTask, ...]
    created_at: datetime

    @model_validator(mode="after")
    def _valid_graph(self) -> Self:
        ids = [t.id for t in self.tasks]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate task ids: {duplicates}")
        known = set(ids)
        unknown = sorted(
            f"{t.id} -> {dep}" for t in self.tasks for dep in t.depends_on if dep not in known
        )
        if unknown:
            raise ValueError(f"unknown dependencies: {unknown}")
        _topological_layers(self.tasks)  # raises on a cycle
        return self

    def layers(self) -> list[list[BoardTask]]:
        return _topological_layers(self.tasks)

    def sources(self) -> list[str]:
        return [t.source for t in self.tasks if t.kind == "listing"]


class SourceCatalog(Protocol):
    def enabled_source_ids(self, enabled_overrides: dict[str, bool] | None = None) -> list[str]: ...


def build_plan(
    query: SearchQuery,
    catalog: SourceCatalog,
    now: datetime | None = None,
    enabled_overrides: dict[str, bool] | None = None,
) -> SearchPlan:
    """Turn a query into a plan. Deterministic for a fixed ``now``; does no I/O."""
    created_at = now or datetime.now(WARSAW_TZ)
    until = created_at.date()
    window = DateWindow(since=until - timedelta(days=query.max_age_days), until=until)
    source_ids = (
        list(dict.fromkeys(query.sources))
        if query.sources is not None
        else catalog.enabled_source_ids(enabled_overrides)
    )

    tasks: list[BoardTask] = [
        BoardTask(
            id=f"listing:{source}",
            source=source,
            kind="listing",
            query=query,
            date_window=window,
        )
        for source in source_ids
    ]
    if query.verify_validity and tasks:
        tasks.append(
            BoardTask(
                id="validity:*",
                source=ALL_SOURCES,
                kind="validity",
                query=query,
                date_window=window,
                depends_on=tuple(t.id for t in tasks),
            )
        )
    return SearchPlan(query=query, tasks=tuple(tasks), created_at=created_at)


class PlanRunner(Protocol):
    def run_listing(
        self, source_id: str, query: SearchQuery
    ) -> Awaitable[tuple[list[JobOffer], SourceReport]]: ...

    def check_validity(self, urls: list[str]) -> Awaitable[list[ValidityResult]]: ...


@dataclass
class PlanExecution:
    offers: list[JobOffer]
    reports: list[SourceReport]
    validity: dict[str, bool] = field(default_factory=dict)
    task_log: list[tuple[int, str, str]] = field(default_factory=list)
    """(layer index, task id, outcome) in execution order."""


async def execute_plan(
    plan: SearchPlan,
    runner: PlanRunner,
    after_listings: Callable[[list[JobOffer]], list[JobOffer]] | None = None,
) -> PlanExecution:
    """Run the plan layer by layer.

    ``after_listings`` (filter, persist, deduplicate) runs once all listing tasks are done
    and before any validity task; its output is what the validity task checks and what
    ``PlanExecution.offers`` holds. Offers that the validity check marks invalid are
    removed; an offer whose check failed or was skipped is kept, as before.
    """
    execution = PlanExecution(offers=[], reports=[])
    listings_done = False

    async def run_task(task: BoardTask) -> str:
        if task.kind == "listing":
            offers, report = await runner.run_listing(task.source, task.query)
            execution.offers.extend(offers)
            execution.reports.append(report)
            return report.status.value
        if task.kind == "validity":
            urls = [o.link for o in execution.offers[: task.query.limit]]
            results = await runner.check_validity(urls)
            execution.validity.update({r.url: r.is_valid for r in results})
            return f"checked {len(results)}"
        raise NotImplementedError(f"task kind {task.kind!r} has no executor yet")

    for depth, layer in enumerate(plan.layers()):
        if not listings_done and all(t.kind != "listing" for t in layer):
            listings_done = True
            if after_listings is not None:
                execution.offers = after_listings(execution.offers)
        results = await asyncio.gather(*(run_task(t) for t in layer), return_exceptions=True)
        for task, outcome in zip(layer, results, strict=True):
            if isinstance(outcome, BaseException):
                logger.error("Task %s failed: %s", task.id, outcome)
                if task.kind == "listing":
                    execution.reports.append(
                        SourceReport(
                            id=task.source,
                            status=SourceFetchStatus.ERROR,
                            count=0,
                            error=str(outcome) or type(outcome).__name__,
                        )
                    )
                execution.task_log.append((depth, task.id, f"error: {outcome}"))
            else:
                execution.task_log.append((depth, task.id, outcome))

    if not listings_done and after_listings is not None:
        execution.offers = after_listings(execution.offers)
    if execution.validity:
        execution.offers = [o for o in execution.offers if execution.validity.get(o.link, True)]
    return execution
