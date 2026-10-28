import json
from pathlib import Path

import jsonschema
import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from job_scout.adapters.aplikuj import AplikujAdapter
from job_scout.adapters.base import COMMON_EXPIRY_MARKERS
from job_scout.adapters.bulldogjob import BulldogJobAdapter
from job_scout.adapters.justjoin import JustJoinAdapter
from job_scout.adapters.linkedin import LinkedInAdapter
from job_scout.adapters.nofluffjobs import NoFluffJobsAdapter
from job_scout.adapters.olx import OlxAdapter
from job_scout.adapters.pracapl import PracaPlAdapter
from job_scout.adapters.pracuj import PracujAdapter
from job_scout.adapters.rocketjobs import RocketJobsAdapter
from job_scout.adapters.solidjobs import SolidJobsAdapter
from job_scout.adapters.theprotocol import TheProtocolAdapter

FIXTURES_DIR = Path("tests/fixtures")
SCHEMA_PATH = Path("schema/job_offer.schema.json")
JOB_OFFER_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

ADAPTERS_MAP = {
    "pracuj": PracujAdapter(),
    "justjoin": JustJoinAdapter(),
    "rocketjobs": RocketJobsAdapter(),
    "nofluffjobs": NoFluffJobsAdapter(),
    "bulldogjob": BulldogJobAdapter(),
    "theprotocol": TheProtocolAdapter(),
    "linkedin": LinkedInAdapter(),
    "olx": OlxAdapter(),
    "pracapl": PracaPlAdapter(),
    "solidjobs": SolidJobsAdapter(),
    "aplikuj": AplikujAdapter(),
}


@pytest.mark.parametrize("source_id", list(ADAPTERS_MAP.keys()))
def test_adapter_listing_fixture_yields_offers(source_id):
    listing_path = FIXTURES_DIR / source_id / "listing_1.html"
    if not listing_path.exists():
        listing_path = FIXTURES_DIR / source_id / "listing_1.json"
    assert listing_path.exists(), f"Listing fixture missing for {source_id}"
    raw_content = listing_path.read_text(encoding="utf-8")
    assert len(raw_content) > 500

    if source_id == "solidjobs":
        data = json.loads(raw_content)
        offers = data.get("offers", [])
        assert len(offers) >= 10, f"solidjobs yielded {len(offers)} offers, expected >= 10"
        return

    tree = HTMLParser(raw_content)
    hrefs = [a.attributes.get("href") for a in tree.css("a") if a.attributes.get("href")]

    if source_id == "justjoin":
        links = [h for h in hrefs if "/job-offer/" in h]
    elif source_id == "rocketjobs":
        links = [h for h in hrefs if "/oferta-pracy/" in h]
    elif source_id == "nofluffjobs":
        links = [h for h in hrefs if "/job/" in h]
    elif source_id == "bulldogjob":
        links = [h for h in hrefs if "/companies/jobs/" in h and "/s/" not in h]
    elif source_id == "theprotocol":
        links = [h for h in hrefs if "/szczegoly/praca/" in h]
    elif source_id == "pracuj":
        links = [h for h in hrefs if "/praca/" in h and ",oferta," in h]
    elif source_id == "linkedin":
        links = [h for h in hrefs if "/jobs/view/" in h]
    elif source_id == "olx":
        links = [h for h in hrefs if "/oferta/praca/" in h or "/d/oferta/" in h]
    elif source_id == "pracapl":
        links = [h for h in hrefs if ".html" in h and any(f"_{i}" in h for i in range(10))]
    elif source_id == "aplikuj":
        links = [h for h in hrefs if "/oferta/" in h or "/praca/" in h]
    else:
        links = hrefs

    uniq = list(dict.fromkeys(links))
    assert len(uniq) >= 10, f"{source_id} yielded {len(uniq)} offers in listing_1, expected >= 10"


@pytest.mark.parametrize("source_id", ["pracuj", "justjoin", "rocketjobs", "nofluffjobs", "bulldogjob", "theprotocol"])
def test_tier1_detail_fixtures_and_schema_validation(source_id):
    adapter = ADAPTERS_MAP[source_id]
    detail_files = sorted(list((FIXTURES_DIR / source_id).glob("detail_*.html")))
    assert len(detail_files) >= 3, f"Expected 3 detail fixtures for {source_id}"

    req_found_count = 0
    for detail_path in detail_files:
        html = detail_path.read_text(encoding="utf-8")
        fallback_url = f"https://example.com/{source_id}/test-job"
        offer = adapter._parse_job_posting(html, fallback_url)

        # Basic fields
        assert offer.link, "Offer must have link"
        assert offer.title, "Offer must have title"
        assert offer.description, "Offer must have description"

        # Validate against JSON schema
        offer_dict = offer.model_dump(mode="json")
        jsonschema.validate(instance=offer_dict, schema=JOB_OFFER_SCHEMA)

        if offer.requirements and len(offer.requirements) > 0:
            req_found_count += 1

    req_ratio = req_found_count / len(detail_files)
    assert req_ratio >= 0.70, f"{source_id} requirements ratio {req_ratio:.2f} < 0.70"


@pytest.mark.parametrize("source_id", list(ADAPTERS_MAP.keys()))
def test_expired_fixture_detection(source_id):
    adapter = ADAPTERS_MAP[source_id]
    expired_path = FIXTURES_DIR / source_id / "expired.html"
    assert expired_path.exists(), f"Expired fixture missing for {source_id}"
    raw_text = expired_path.read_text(encoding="utf-8")

    body_lower = raw_text.lower()
    markers = adapter.expiry_markers + COMMON_EXPIRY_MARKERS + ["404", "not found", "nie znaleziono", "nie istnieje", "status\":404"]
    detected = any(m.lower() in body_lower for m in markers)
    assert detected, f"{source_id} expired fixture did not contain any recognized expiry marker"
