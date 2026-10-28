import logging
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from job_scout.adapters.base import BaseAdapter
from job_scout.extract.jsonld import extract_job_posting_jsonld
from job_scout.http import get_http_client
from job_scout.models import (
    JobOffer,
    SalaryContract,
    SalaryGrossNet,
    SalaryPeriod,
    SalaryRange,
    SearchQuery,
    now_warsaw_iso,
)
from job_scout.normalize.dates import parse_date
from job_scout.normalize.location import is_warsaw_location
from job_scout.normalize.requirements import normalize_requirements
from job_scout.normalize.text import html_to_plain_text, truncate_description
from job_scout.normalize.work_mode import normalize_work_mode
from job_scout.store import canonicalize_url, compute_job_id

logger = logging.getLogger("job_scout.adapters.nofluffjobs")


class NoFluffJobsAdapter(BaseAdapter):
    id = "nofluffjobs"
    tier = 1
    enabled_by_default = True
    expiry_markers = [
        "ogłoszenie nie jest już aktywne",
        "oferta wygasła",
        "this job is no longer available",
        "nie znaleziono oferty",
    ]

    def _parse_job_posting(self, html_content: str, fallback_url: str) -> JobOffer:
        now_iso = now_warsaw_iso()
        canon_url = canonicalize_url(fallback_url)
        job_id = compute_job_id(canon_url)

        jp = extract_job_posting_jsonld(html_content) or {}
        tree = HTMLParser(html_content)

        title = jp.get("title")
        if not title:
            h1 = tree.css_first("h1")
            title = h1.text(strip=True) if h1 else "Job Offer"

        company = None
        org = jp.get("hiringOrganization")
        if isinstance(org, dict):
            company = org.get("name")
        elif isinstance(org, str):
            company = org

        location = "Warszawa"
        loc_obj = jp.get("jobLocation")
        if isinstance(loc_obj, dict):
            addr = loc_obj.get("address")
            if isinstance(addr, dict):
                location = addr.get("addressLocality") or addr.get("streetAddress") or "Warszawa"
        elif isinstance(loc_obj, list) and loc_obj:
            first = loc_obj[0]
            if isinstance(first, dict):
                addr = first.get("address")
                if isinstance(addr, dict):
                    location = addr.get("addressLocality") or "Warszawa"

        raw_desc = jp.get("description") or tree.text(separator="\n")
        full_text = html_to_plain_text(raw_desc)
        clean_desc, is_truncated = truncate_description(full_text)

        reqs, nice, req_conf = normalize_requirements(html_or_text=tree.text(separator="\n"))

        salary: list[SalaryRange] | None = None
        base_sal = jp.get("baseSalary")
        if isinstance(base_sal, dict):
            val_obj = base_sal.get("value")
            cur = base_sal.get("currency", "PLN")
            if isinstance(val_obj, dict):
                min_v = val_obj.get("minValue") or val_obj.get("value")
                max_v = val_obj.get("maxValue") or val_obj.get("value")
                unit_str = str(val_obj.get("unitText", "Month")).lower()
                period = SalaryPeriod.MONTH
                if "hour" in unit_str:
                    period = SalaryPeriod.HOUR
                elif "year" in unit_str:
                    period = SalaryPeriod.YEAR

                salary = [
                    SalaryRange(
                        min=min_v,
                        max=max_v,
                        currency=cur,
                        period=period,
                        gross_net=SalaryGrossNet.UNKNOWN,
                        contract=SalaryContract.UNKNOWN,
                        raw=f"{min_v} - {max_v} {cur} / {unit_str}",
                    )
                ]
            elif isinstance(val_obj, (int, float)):
                salary = [
                    SalaryRange(
                        min=val_obj,
                        max=val_obj,
                        currency=cur,
                        period=SalaryPeriod.MONTH,
                        gross_net=SalaryGrossNet.UNKNOWN,
                        contract=SalaryContract.UNKNOWN,
                        raw=f"{val_obj} {cur} / month",
                    )
                ]

        loc_type = jp.get("jobLocationType")
        emp_type = jp.get("employmentType")
        work_modes, raw_wm = normalize_work_mode(loc_type or tree.text(separator="\n"))

        posted_at, date_conf = parse_date(jp.get("datePosted"))
        valid_until, _ = parse_date(jp.get("validThrough"))

        return JobOffer(
            id=job_id,
            link=canon_url,
            source=self.id,
            title=title,
            company=company,
            location=location,
            description=clean_desc,
            description_truncated=is_truncated,
            requirements=reqs,
            requirements_confidence=req_conf,
            nice_to_have=nice,
            salary=salary,
            work_mode=work_modes,
            raw_work_mode=raw_wm,
            contract_types=[str(emp_type)] if emp_type else [],
            posted_at=posted_at,
            valid_until=valid_until,
            date_confidence=date_conf,
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=True,
            also_on=[],
        )

    async def search(self, query: SearchQuery) -> list[JobOffer]:
        client = get_http_client()
        url = "https://nofluffjobs.com/pl/warszawa"
        params: dict[str, str | int] = {}
        if query.keywords:
            params["criteria"] = f"keyword={query.keywords}"

        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.warning("NoFluffJobs listing returned %d", resp.status_code)
            return []

        tree = HTMLParser(resp.text)
        links = []
        for a in tree.css("a"):
            href = str(a.attributes.get("href") or "")
            if "/job/" in href:
                full = urljoin("https://nofluffjobs.com", href)
                links.append(full)

        uniq_links = list(dict.fromkeys(links))
        limit = min(query.limit, 100)
        target_links = uniq_links[:limit]

        offers: list[JobOffer] = []
        for link in target_links:
            try:
                offer = await self.fetch_detail(link)
                if is_warsaw_location(offer.location, offer.work_mode, query.include_metro):
                    offers.append(offer)
            except Exception as e:
                logger.debug("Failed fetching NFJ detail %s: %s", link, e)

        return offers

    async def fetch_detail(self, url: str) -> JobOffer:
        client = get_http_client()
        resp = await client.get(url)
        return self._parse_job_posting(resp.text, url)
