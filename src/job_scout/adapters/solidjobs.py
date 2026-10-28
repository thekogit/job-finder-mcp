import json
import logging
from typing import Any

from job_scout.adapters.base import BaseAdapter
from job_scout.http import get_http_client
from job_scout.models import (
    JobOffer,
    SalaryContract,
    SalaryGrossNet,
    SalaryPeriod,
    SalaryRange,
    SearchQuery,
    WorkMode,
    now_warsaw_iso,
)
from job_scout.normalize.dates import parse_date
from job_scout.normalize.location import is_warsaw_location
from job_scout.normalize.requirements import normalize_requirements
from job_scout.store import canonicalize_url, compute_job_id

logger = logging.getLogger("job_scout.adapters.solidjobs")


class SolidJobsAdapter(BaseAdapter):
    id = "solidjobs"
    tier = 2
    enabled_by_default = True
    expiry_markers = [
        "not found",
        "ogłoszenie wygasło",
        "oferta wygasła",
        "nie znaleziono oferty",
    ]

    def _parse_offer_dict(self, o: dict[str, Any]) -> JobOffer:
        now_iso = now_warsaw_iso()
        raw_url = str(o.get("jobOfferUrl") or f"https://solid.jobs/praca/{o.get('id')}")
        canon_url = canonicalize_url(raw_url)
        job_id = compute_job_id(canon_url)

        title = str(o.get("jobTitle") or "Job Offer")
        company = o.get("companyName")
        city = o.get("companyCity") or "Warszawa"

        # Skills -> requirements (structured!)
        req_list: list[str] = []
        skills = o.get("requiredSkills")
        if isinstance(skills, list):
            for s in skills:
                if isinstance(s, dict):
                    name = s.get("name") or s.get("skillName")
                    if name:
                        req_list.append(str(name))
                elif isinstance(s, str):
                    req_list.append(s)

        reqs, nice, req_conf = normalize_requirements(structured_reqs=req_list)

        # Salary
        salary: list[SalaryRange] | None = None
        sr = o.get("salaryRange")
        if isinstance(sr, dict):
            min_v = sr.get("lowerBound")
            max_v = sr.get("upperBound")
            cur = str(sr.get("currency") or "PLN")
            p_str = str(sr.get("salaryPeriod") or "Month").lower()
            emp_str = str(sr.get("employmentType") or "other").lower()

            period = SalaryPeriod.MONTH
            if "hour" in p_str:
                period = SalaryPeriod.HOUR
            elif "year" in p_str:
                period = SalaryPeriod.YEAR

            contract = SalaryContract.UNKNOWN
            if "b2b" in emp_str:
                contract = SalaryContract.B2B
            elif "uop" in emp_str or "permanent" in emp_str:
                contract = SalaryContract.UOP

            raw_str = f"{min_v} - {max_v} {cur} / {p_str} ({emp_str})"
            salary = [
                SalaryRange(
                    min=min_v,
                    max=max_v,
                    currency=cur,
                    period=period,
                    gross_net=SalaryGrossNet.UNKNOWN,
                    contract=contract,
                    raw=raw_str,
                )
            ]

        # Work mode
        work_modes: list[WorkMode] = [WorkMode.ONSITE]
        if o.get("remotePossible"):
            work_modes.append(WorkMode.REMOTE)

        posted_at, date_conf = parse_date(o.get("validFrom"))
        valid_until, _ = parse_date(o.get("validTo"))

        desc = f"{title} at {company or 'Company'}. Experience level: {o.get('experienceLevel', 'Not specified')}."

        return JobOffer(
            id=job_id,
            link=canon_url,
            source=self.id,
            title=title,
            company=company,
            location=city,
            description=desc,
            description_truncated=False,
            requirements=reqs,
            requirements_confidence=req_conf,
            nice_to_have=[],
            salary=salary,
            work_mode=work_modes,
            raw_work_mode="remote" if o.get("remotePossible") else "onsite",
            contract_types=[str(o.get("employmentType"))] if o.get("employmentType") else [],
            posted_at=posted_at,
            valid_until=valid_until,
            date_confidence=date_conf,
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=True,
            also_on=[],
        )

    def _parse_job_posting(self, html_or_json: str, fallback_url: str) -> JobOffer:
        try:
            data = json.loads(html_or_json)
            if isinstance(data, dict):
                return self._parse_offer_dict(data)
        except Exception:
            logger.debug("Solidjobs payload is not raw JSON, falling back")

        now_iso = now_warsaw_iso()
        canon_url = canonicalize_url(fallback_url)
        return JobOffer(
            id=compute_job_id(canon_url),
            link=canon_url,
            source=self.id,
            title="Job Offer",
            company="Company",
            location="Warszawa",
            description="",
            requirements=[],
            first_seen_at=now_iso,
            last_checked_at=now_iso,
            is_valid=True,
        )

    async def search(self, query: SearchQuery) -> list[JobOffer]:
        client = get_http_client()
        url = "https://solid.jobs/api/praca/warszawa"
        resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning("Solid.jobs API returned %d", resp.status_code)
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        raw_offers = data.get("offers", [])
        offers: list[JobOffer] = []
        for o in raw_offers:
            if not isinstance(o, dict):
                continue
            offer = self._parse_offer_dict(o)
            if query.keywords:
                kw = query.keywords.lower()
                if kw not in offer.title.lower() and kw not in offer.description.lower():
                    continue
            if is_warsaw_location(offer.location, offer.work_mode, query.include_metro):
                offers.append(offer)

        limit = min(query.limit, 100)
        return offers[:limit]

    async def fetch_detail(self, url: str) -> JobOffer:
        # Check if URL ends with ID or has key
        client = get_http_client()
        resp = await client.get(url)
        return self._parse_job_posting(resp.text, url)
