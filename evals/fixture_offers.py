"""Parse the recorded detail-page fixtures into JobOffers, offline."""

import json
import re
from pathlib import Path
from typing import Any, Protocol

from job_scout.adapters.bulldogjob import BulldogJobAdapter
from job_scout.adapters.justjoin import JustJoinAdapter
from job_scout.adapters.nofluffjobs import NoFluffJobsAdapter
from job_scout.adapters.pracuj import PracujAdapter
from job_scout.adapters.rocketjobs import RocketJobsAdapter
from job_scout.adapters.theprotocol import TheProtocolAdapter
from job_scout.models import JobOffer

FIXTURES_DIR = Path("tests/fixtures")

class DetailParser(Protocol):
    """Tier-1 adapters parse a detail page without I/O through this (private) method."""

    def _parse_job_posting(self, html_content: str, fallback_url: str) -> JobOffer: ...


DETAIL_ADAPTERS: dict[str, DetailParser] = {
    "pracuj": PracujAdapter(),
    "justjoin": JustJoinAdapter(),
    "rocketjobs": RocketJobsAdapter(),
    "nofluffjobs": NoFluffJobsAdapter(),
    "bulldogjob": BulldogJobAdapter(),
    "theprotocol": TheProtocolAdapter(),
}


def fixture_offers(fixtures_dir: Path = FIXTURES_DIR) -> list[tuple[str, JobOffer]]:
    """(fixture path, parsed offer) for every tier-1 detail fixture, in path order."""
    results: list[tuple[str, JobOffer]] = []
    for board, adapter in DETAIL_ADAPTERS.items():
        for path in sorted((fixtures_dir / board).glob("detail_*.html")):
            html = path.read_text(encoding="utf-8")
            offer = adapter._parse_job_posting(html, f"https://example.com/{board}/{path.stem}")
            results.append((path.relative_to(fixtures_dir).as_posix(), offer))
    return results


def solidjobs_offers(fixtures_dir: Path = FIXTURES_DIR) -> list[tuple[dict[str, Any], JobOffer]]:
    """(raw API offer, parsed offer) for every offer in the recorded SolidJobs JSON listing."""
    from job_scout.adapters.solidjobs import SolidJobsAdapter

    adapter = SolidJobsAdapter()
    data = json.loads((fixtures_dir / "solidjobs" / "listing_1.json").read_text(encoding="utf-8"))
    return [(raw, adapter._parse_offer_dict(raw)) for raw in data.get("offers", [])]


_CODE_NOISE = re.compile(r"[{};<>=]|\(function|catch\(|--[a-z]")
_NAV_NOISE = {
    "aplikuj", "link", "oferty pracy", "privacy policy", "polityka prywatności", "remote",
    "zaloguj się", "regulamin", "cookies", "linkedin", "linked in",
}


def is_requirement_like(text: str) -> bool:
    """Drop the extractor's page-chrome noise (CSS, inline JS, navigation labels)."""
    stripped = text.strip()
    if not 3 <= len(stripped) <= 300 or _CODE_NOISE.search(stripped):
        return False
    if stripped.lower() in _NAV_NOISE:
        return False
    return re.search(r"[^\W\d_]{2}", stripped) is not None


def fixture_requirement_texts(fixtures_dir: Path = FIXTURES_DIR) -> list[str]:
    """Requirement / skill strings from the fixtures, deduplicated, in first-seen order."""
    texts: list[str] = []
    for _, offer in fixture_offers(fixtures_dir):
        texts.extend(offer.requirements + offer.nice_to_have)
    for _, offer in solidjobs_offers(fixtures_dir):
        texts.extend(offer.requirements + offer.nice_to_have)
    return list(dict.fromkeys(t.strip() for t in texts if is_requirement_like(t)))
