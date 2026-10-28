import json
import logging
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

from job_scout.http import setup_logging
from job_scout.models import (
    WARSAW_TZ,
    JobOffer,
    SalaryPeriod,
    SearchQuery,
    SearchResult,
    SourceStatus,
    ValidityResult,
    now_warsaw_iso,
)
from job_scout.registry import registry
from job_scout.store import JobStore, canonicalize_url

setup_logging()
logger = logging.getLogger("job_scout.server")

mcp = FastMCP("job-scout")
store = JobStore()


def _is_within_max_age(posted_at: str | None, max_age_days: int) -> bool:
    if not posted_at:
        return True
    try:
        dt = datetime.fromisoformat(posted_at)
        now = datetime.now(WARSAW_TZ)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=WARSAW_TZ)
        cutoff = now - timedelta(days=max_age_days)
        return dt >= cutoff
    except Exception:
        return True


def _matches_salary_min(offer: JobOffer, min_pln_month: int) -> bool:
    if not offer.salary:
        return True

    for s in offer.salary:
        val = s.max if s.max is not None else s.min
        if val is None:
            continue
        # Convert to monthly equivalent
        multiplier = 1.0
        if s.period == SalaryPeriod.HOUR:
            multiplier = 168.0
        elif s.period == SalaryPeriod.DAY:
            multiplier = 21.0
        elif s.period == SalaryPeriod.YEAR:
            multiplier = 1.0 / 12.0

        monthly_val = float(val) * multiplier
        if monthly_val >= float(min_pln_month):
            return True

    return False


@mcp.tool()
async def search_jobs(
    keywords: str | None = None,
    sources: list[str] | None = None,
    max_age_days: int = 14,
    work_modes: list[str] | None = None,
    salary_min_pln_month: int | None = None,
    only_with_salary: bool = False,
    include_metro: bool = False,
    verify_validity: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> SearchResult:
    """Search fresh, verified job offers in Warsaw or remote open to Poland.

    Use this tool when you need to find current job opportunities across multiple Polish
    job boards (JustJoinIT, RocketJobs, NoFluffJobs, BulldogJob, TheProtocol, Pracuj.pl, etc.).

    Args:
        keywords: Optional search query (e.g. "python", "devops", "data engineer").
        sources: List of source IDs to query. Defaults to all enabled platforms.
        max_age_days: Maximum age of postings in days (1 to 60). Default is 14 days.
        work_modes: Filter by work mode: ["onsite", "hybrid", "remote"].
        salary_min_pln_month: Minimum monthly PLN gross salary equivalent.
        only_with_salary: If True, returns only postings that display published compensation.
        include_metro: If True, includes Warsaw metropolitan suburbs (e.g. Piaseczno, Pruszków).
        verify_validity: If True, checks that returned URLs are active and non-expired.
        limit: Number of results to return (1 to 200). Default is 50.
        offset: Offset for pagination. Default is 0.
    """
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    if max_age_days < 1 or max_age_days > 60:
        raise ValueError("max_age_days must be between 1 and 60")

    if sources:
        for s in sources:
            if not registry.get_adapter(s):
                raise ValueError(f"Unknown source ID: '{s}'")

    query_params = {
        "keywords": keywords,
        "sources": sources,
        "max_age_days": max_age_days,
        "work_modes": work_modes,
        "salary_min_pln_month": salary_min_pln_month,
        "only_with_salary": only_with_salary,
        "include_metro": include_metro,
        "verify_validity": verify_validity,
        "limit": limit,
        "offset": offset,
    }

    cache_key = f"search:{json.dumps(query_params, sort_keys=True)}"
    cached = store.get_cached(cache_key)
    if cached:
        logger.info("Serving search_jobs from cache")
        return SearchResult.model_validate_json(cached)

    search_query = SearchQuery(
        keywords=keywords,
        sources=sources,
        max_age_days=max_age_days,
        work_modes=work_modes,
        salary_min_pln_month=salary_min_pln_month,
        only_with_salary=only_with_salary,
        include_metro=include_metro,
        verify_validity=verify_validity,
        limit=limit,
        offset=offset,
    )

    all_offers, source_reports = await registry.execute_search(search_query)

    # Filter by age
    filtered = [o for o in all_offers if _is_within_max_age(o.posted_at, max_age_days)]

    # Filter by work mode
    if work_modes:
        target_modes = {m.lower() for m in work_modes}
        filtered = [
            o
            for o in filtered
            if o.work_mode and any(str(m.value).lower() in target_modes for m in o.work_mode)
        ]

    # Filter by salary presence
    if only_with_salary:
        filtered = [o for o in filtered if o.salary and len(o.salary) > 0]

    # Filter by minimum salary
    if salary_min_pln_month:
        filtered = [o for o in filtered if _matches_salary_min(o, salary_min_pln_month)]

    # Save to store and deduplicate
    saved_offers = [store.save_or_update_job(o) for o in filtered]
    deduped = store.deduplicate_offers(saved_offers)

    # Optional validity check on returned results
    if verify_validity and deduped:
        urls_to_check = [o.link for o in deduped[:limit]]
        validity_res = await registry.check_validity(urls_to_check)
        validity_map = {v.url: v.is_valid for v in validity_res}
        deduped = [o for o in deduped if validity_map.get(o.link, True)]

    total_count = len(deduped)
    paginated = deduped[offset : offset + limit]

    result = SearchResult(
        query=query_params,
        generated_at=now_warsaw_iso(),
        sources=source_reports,
        total=total_count,
        offset=offset,
        returned=len(paginated),
        jobs=paginated,
    )

    # Cache for 30 minutes (1800s per Section 7.4)
    store.set_cached(cache_key, result.model_dump_json(), ttl_seconds=1800.0, cache_type="listing")
    return result


@mcp.tool()
async def get_job_details(url: str) -> JobOffer:
    """Retrieve full un-truncated details and complete description for a specific job offer.

    Use this tool when you need the complete job description, requirements list, and metadata
    for a specific URL returned by search_jobs.

    Args:
        url: The absolute HTTPS URL of the job posting.
    """
    canon_url = canonicalize_url(url)
    cache_key = f"detail:{canon_url}"
    cached = store.get_cached(cache_key)
    if cached:
        logger.info("Serving get_job_details from cache")
        return JobOffer.model_validate_json(cached)

    adapter = registry.get_adapter_for_url(canon_url)
    if adapter:
        offer = await adapter.fetch_detail(canon_url)
    else:
        # Generic fetcher
        now_iso = now_warsaw_iso()
        offer = JobOffer(
            id="unknown",
            link=canon_url,
            source="unknown",
            title="Unknown Job Offer",
            description="",
            description_truncated=False,
            requirements=[],
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=True,
        )

    # Persist and cache for 6 hours (21600s per Section 7.4)
    updated = store.save_or_update_job(offer)
    store.set_cached(cache_key, updated.model_dump_json(), ttl_seconds=21600.0, cache_type="detail")
    return updated


@mcp.tool()
async def check_validity(urls: list[str]) -> list[ValidityResult]:
    """Check whether a list of job offer URLs are currently valid and accepting applications.

    Use this tool to batch verify the current online validity, HTTP status, and expiration
    markers of up to 50 URLs.

    Args:
        urls: List of job offer URLs to verify (maximum 50 items).
    """
    if len(urls) > 50:
        raise ValueError("Maximum 50 URLs allowed per check_validity call")

    results: list[ValidityResult] = []
    uncached_urls: list[str] = []

    for url in urls:
        canon_url = canonicalize_url(url)
        cache_key = f"validity:{canon_url}"
        cached = store.get_cached(cache_key)
        if cached:
            results.append(ValidityResult.model_validate_json(cached))
        else:
            uncached_urls.append(url)

    if uncached_urls:
        checked = await registry.check_validity(uncached_urls)
        for res in checked:
            canon_url = canonicalize_url(res.url)
            cache_key = f"validity:{canon_url}"
            # Cache for 2 hours (7200s per Section 7.4)
            store.set_cached(
                cache_key, res.model_dump_json(), ttl_seconds=7200.0, cache_type="validity"
            )
            results.append(res)

    return results


@mcp.tool()
def list_sources() -> list[SourceStatus]:
    """List all supported job board sources, their tier, enablement status, and health metrics.

    Use this tool to discover available platforms, check which boards are currently active,
    and inspect recent error or success timestamps.
    """
    return registry.list_sources()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
