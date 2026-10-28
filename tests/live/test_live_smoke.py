from datetime import datetime, timedelta

import pytest

from job_scout.http import get_http_client
from job_scout.models import WARSAW_TZ, SearchQuery
from job_scout.registry import registry

TIER_1_SOURCES = ["justjoin", "rocketjobs", "nofluffjobs", "bulldogjob", "theprotocol", "pracuj"]


@pytest.mark.live
@pytest.mark.parametrize("source_id", TIER_1_SOURCES)
async def test_tier1_live_smoke(source_id):
    adapter = registry.get_adapter(source_id)
    assert adapter is not None, f"Adapter {source_id} not registered"

    query = SearchQuery(sources=[source_id], limit=10, max_age_days=30)
    offers = await adapter.search(query)

    print(f"\n[{source_id}] Live offers fetched: {len(offers)}")
    assert len(offers) >= 5, f"{source_id} returned {len(offers)} offers, expected >= 5"

    client = get_http_client()
    now = datetime.now(WARSAW_TZ)
    recent_count = 0
    with_salary_count = 0
    with_workmode_count = 0
    with_req_count = 0

    # Spot check returned links (up to 5)
    for offer in offers[:5]:
        assert offer.link.startswith("http"), f"Invalid link: {offer.link}"
        assert offer.title, f"Missing title in {offer.link}"

        # Check HTTP 200
        resp = await client.get(offer.link)
        assert resp.status_code == 200, f"Link {offer.link} returned HTTP {resp.status_code}"

        # Check date within 14 days
        if offer.posted_at:
            try:
                dt = datetime.fromisoformat(offer.posted_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=WARSAW_TZ)
                if now - dt <= timedelta(days=14):
                    recent_count += 1
            except Exception:
                pass
        elif offer.date_confidence == "unknown":
            recent_count += 1

        if offer.salary and len(offer.salary) > 0:
            with_salary_count += 1
        if offer.work_mode and len(offer.work_mode) > 0:
            with_workmode_count += 1
        if offer.requirements and len(offer.requirements) > 0:
            with_req_count += 1

    assert recent_count >= 1, f"{source_id} has no offers posted within 14 days"
    print(
        f"[{source_id}] Metrics (top 5): "
        f"Salary: {with_salary_count}/5, "
        f"WorkMode: {with_workmode_count}/5, "
        f"Reqs: {with_req_count}/5"
    )
