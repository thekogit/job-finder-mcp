import json
import logging
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser

logger = logging.getLogger("job_scout.extract.jsonld")


def extract_job_posting_jsonld(html_content: str) -> dict[str, Any] | None:
    if not html_content:
        return None

    tree = HTMLParser(html_content)
    scripts = tree.css('script[type="application/ld+json"]')

    for script in scripts:
        raw_text = script.text(strip=True)
        if not raw_text:
            continue
        try:
            data = json.loads(raw_text)
        except Exception:
            continue

        candidate = _find_job_posting_in_obj(data)
        if candidate is not None:
            return candidate

    return None


def _find_job_posting_in_obj(obj: Any) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        obj_type = obj.get("@type")
        if obj_type == "JobPosting" or (
            isinstance(obj_type, list) and "JobPosting" in obj_type
        ):
            return obj

        if "@graph" in obj and isinstance(obj["@graph"], list):
            for item in obj["@graph"]:
                found = _find_job_posting_in_obj(item)
                if found:
                    return found

        for v in obj.values():
            if isinstance(v, (dict, list)):
                found = _find_job_posting_in_obj(v)
                if found:
                    return found

    elif isinstance(obj, list):
        for item in obj:
            found = _find_job_posting_in_obj(item)
            if found:
                return found

    return None
