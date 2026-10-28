import asyncio
import logging
from urllib.parse import urlparse

from job_scout.adapters.aplikuj import AplikujAdapter
from job_scout.adapters.base import BaseAdapter
from job_scout.adapters.bulldogjob import BulldogJobAdapter
from job_scout.adapters.glassdoor import GlassdoorAdapter
from job_scout.adapters.indeed import IndeedAdapter
from job_scout.adapters.justjoin import JustJoinAdapter
from job_scout.adapters.linkedin import LinkedInAdapter
from job_scout.adapters.nofluffjobs import NoFluffJobsAdapter
from job_scout.adapters.olx import OlxAdapter
from job_scout.adapters.pracapl import PracaPlAdapter
from job_scout.adapters.pracuj import PracujAdapter
from job_scout.adapters.rocketjobs import RocketJobsAdapter
from job_scout.adapters.solidjobs import SolidJobsAdapter
from job_scout.adapters.theprotocol import TheProtocolAdapter
from job_scout.http import get_http_client
from job_scout.models import (
    JobOffer,
    SearchQuery,
    SourceFetchStatus,
    SourceReport,
    SourceStatus,
    ValidityResult,
    now_warsaw_iso,
)

logger = logging.getLogger("job_scout.registry")


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._last_success: dict[str, str] = {}
        self._last_error: dict[str, str] = {}

    def register(self, adapter: BaseAdapter) -> None:
        self._adapters[adapter.id] = adapter

    def get_adapter(self, source_id: str) -> BaseAdapter | None:
        return self._adapters.get(source_id)

    def get_adapter_for_url(self, url: str) -> BaseAdapter | None:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        for adapter in self._adapters.values():
            if adapter.id in host:
                return adapter
        if "pracuj.pl" in host:
            return self._adapters.get("pracuj")
        if "justjoin.it" in host:
            return self._adapters.get("justjoin")
        if "rocketjobs.pl" in host:
            return self._adapters.get("rocketjobs")
        if "nofluffjobs.com" in host:
            return self._adapters.get("nofluffjobs")
        if "bulldogjob.pl" in host:
            return self._adapters.get("bulldogjob")
        if "theprotocol.it" in host:
            return self._adapters.get("theprotocol")
        if "linkedin.com" in host:
            return self._adapters.get("linkedin")
        if "olx.pl" in host:
            return self._adapters.get("olx")
        if "praca.pl" in host:
            return self._adapters.get("pracapl")
        if "solid.jobs" in host:
            return self._adapters.get("solidjobs")
        if "aplikuj.pl" in host:
            return self._adapters.get("aplikuj")
        if "glassdoor" in host:
            return self._adapters.get("glassdoor")
        if "indeed" in host:
            return self._adapters.get("indeed")
        return None

    def list_sources(self, enabled_overrides: dict[str, bool] | None = None) -> list[SourceStatus]:
        results: list[SourceStatus] = []
        for s_id, adapter in self._adapters.items():
            is_enabled = adapter.enabled_by_default
            if enabled_overrides and s_id in enabled_overrides:
                is_enabled = enabled_overrides[s_id]

            results.append(
                SourceStatus(
                    id=s_id,
                    tier=adapter.tier,
                    enabled=is_enabled,
                    robots_ok=True,
                    last_success_at=self._last_success.get(s_id),
                    last_error=self._last_error.get(s_id),
                )
            )
        return results

    async def _search_source(
        self, adapter: BaseAdapter, query: SearchQuery
    ) -> tuple[list[JobOffer], SourceReport]:
        try:
            offers = await asyncio.wait_for(adapter.search(query), timeout=45.0)
            now_iso = now_warsaw_iso()
            self._last_success[adapter.id] = now_iso
            return (
                offers,
                SourceReport(
                    id=adapter.id,
                    status=SourceFetchStatus.OK,
                    count=len(offers),
                    error=None,
                ),
            )
        except TimeoutError:
            err_msg = "Request timed out after 45s"
            self._last_error[adapter.id] = err_msg
            return (
                [],
                SourceReport(
                    id=adapter.id,
                    status=SourceFetchStatus.TIMEOUT,
                    count=0,
                    error=err_msg,
                ),
            )
        except Exception as e:
            err_msg = str(e)
            self._last_error[adapter.id] = err_msg
            status = SourceFetchStatus.ERROR
            if "403" in err_msg or "challenge" in err_msg.lower() or "blocked" in err_msg.lower():
                status = SourceFetchStatus.BLOCKED
            return (
                [],
                SourceReport(
                    id=adapter.id,
                    status=status,
                    count=0,
                    error=err_msg,
                ),
            )

    async def execute_search(
        self,
        query: SearchQuery,
        enabled_overrides: dict[str, bool] | None = None,
    ) -> tuple[list[JobOffer], list[SourceReport]]:
        target_ids = query.sources
        if target_ids is None:
            target_ids = [
                s_id
                for s_id, a in self._adapters.items()
                if (enabled_overrides.get(s_id) if enabled_overrides and s_id in enabled_overrides else a.enabled_by_default)
            ]

        tasks = []
        reports: list[SourceReport] = []
        for s_id in target_ids:
            adapter = self._adapters.get(s_id)
            if not adapter:
                reports.append(
                    SourceReport(
                        id=s_id,
                        status=SourceFetchStatus.ERROR,
                        count=0,
                        error=f"Source '{s_id}' not found in registry",
                    )
                )
                continue
            tasks.append(self._search_source(adapter, query))

        if not tasks:
            return ([], reports)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_offers: list[JobOffer] = []
        for res in results:
            if isinstance(res, BaseException):
                logger.error("Unexpected error in search runner: %s", res)
                continue
            offers, report = res
            reports.append(report)
            all_offers.extend(offers)

        return (all_offers, reports)

    async def check_validity(self, urls: list[str]) -> list[ValidityResult]:
        results: list[ValidityResult] = []
        client = get_http_client()
        for url in urls[:50]:
            adapter = self.get_adapter_for_url(url)
            if adapter:
                res = await adapter.check_valid(url)
                results.append(res)
            else:
                now_iso = now_warsaw_iso()
                try:
                    resp = await client.get(url)
                    is_val = resp.status_code == 200
                    reason = None if is_val else f"HTTP {resp.status_code}"
                    results.append(
                        ValidityResult(
                            url=url,
                            is_valid=is_val,
                            reason=reason,
                            checked_at=now_iso,
                        )
                    )
                except Exception as e:
                    results.append(
                        ValidityResult(
                            url=url,
                            is_valid=False,
                            reason=str(e),
                            checked_at=now_iso,
                        )
                    )
        return results


registry = AdapterRegistry()

for inst in [
    PracujAdapter(),
    JustJoinAdapter(),
    RocketJobsAdapter(),
    NoFluffJobsAdapter(),
    BulldogJobAdapter(),
    TheProtocolAdapter(),
    LinkedInAdapter(),
    OlxAdapter(),
    PracaPlAdapter(),
    SolidJobsAdapter(),
    AplikujAdapter(),
    GlassdoorAdapter(),
    IndeedAdapter(),
]:
    registry.register(inst)
