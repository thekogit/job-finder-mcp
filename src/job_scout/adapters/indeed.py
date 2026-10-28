import logging

from job_scout.adapters.base import BaseAdapter
from job_scout.http import get_http_client
from job_scout.models import JobOffer, SearchQuery, now_warsaw_iso

logger = logging.getLogger("job_scout.adapters.indeed")


class IndeedAdapter(BaseAdapter):
    id = "indeed"
    tier = 3
    enabled_by_default = False
    expiry_markers = [
        "this job has expired",
        "ogłoszenie wygasło",
    ]

    async def search(self, query: SearchQuery) -> list[JobOffer]:
        client = get_http_client()
        url = "https://pl.indeed.com/jobs?q=python&l=Warszawa"
        resp = await client.get(url)
        if resp.status_code == 403:
            raise RuntimeError("403 challenge page: blocked by Cloudflare bot protection")
        return []

    async def fetch_detail(self, url: str) -> JobOffer:
        client = get_http_client()
        resp = await client.get(url)
        if resp.status_code == 403:
            raise RuntimeError("403 challenge page: blocked by Cloudflare bot protection")
        now_iso = now_warsaw_iso()
        return JobOffer(
            id="indeed_fallback",
            link=url,
            source=self.id,
            title="Unknown",
            description="",
            requirements=[],
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=False,
        )
