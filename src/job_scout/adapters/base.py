import logging
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from job_scout.http import get_http_client
from job_scout.models import (
    JobOffer,
    SearchQuery,
    ValidityResult,
    now_warsaw_iso,
)

logger = logging.getLogger("job_scout.adapters.base")

COMMON_EXPIRY_MARKERS = [
    "oferta wygasła",
    "ogłoszenie jest nieaktualne",
    "ogłoszenie wygasło",
    "ta oferta jest już nieaktualna",
    "this job is no longer available",
    "no longer accepting applications",
    "this position has been filled",
    "ogłoszenie zakończone",
    "oferta nie jest już dostępna",
    "nie znaleziono oferty",
    "ta oferta pracy wygasła",
]


class BaseAdapter(ABC):
    id: str
    tier: int
    enabled_by_default: bool = True
    expiry_markers: list[str] = COMMON_EXPIRY_MARKERS

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[JobOffer]:
        return []

    @abstractmethod
    async def fetch_detail(self, url: str) -> JobOffer:
        now_iso = now_warsaw_iso()
        return JobOffer(
            id="fallback",
            link=url,
            source=self.id,
            title="Unknown",
            description="",
            requirements=[],
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=False,
        )

    async def check_valid(self, url: str) -> ValidityResult:
        now_iso = now_warsaw_iso()
        client = get_http_client()
        try:
            resp = await client.get(url)
            if resp.status_code in (404, 410):
                return ValidityResult(
                    url=url,
                    is_valid=False,
                    reason=f"HTTP {resp.status_code}",
                    checked_at=now_iso,
                )

            # Check if redirected to search or listing page
            target_path = str(resp.url.path).lower()
            if any(p in target_path for p in ("/search", "/praca?", "/oferty-pracy", "/jobs?", "/wyniki")):
                orig_path = str(urlparse(url).path).lower()
                if orig_path != target_path:
                    return ValidityResult(
                        url=url,
                        is_valid=False,
                        reason=f"Redirected to listing page: {resp.url}",
                        checked_at=now_iso,
                    )

            body_lower = resp.text.lower()
            all_markers = self.expiry_markers + COMMON_EXPIRY_MARKERS
            for marker in all_markers:
                if marker.lower() in body_lower:
                    return ValidityResult(
                        url=url,
                        is_valid=False,
                        reason=f"Expiry marker found: '{marker}'",
                        checked_at=now_iso,
                    )

            return ValidityResult(
                url=url,
                is_valid=True,
                reason=None,
                checked_at=now_iso,
            )
        except Exception as e:
            return ValidityResult(
                url=url,
                is_valid=False,
                reason=f"Request error: {e}",
                checked_at=now_iso,
            )
