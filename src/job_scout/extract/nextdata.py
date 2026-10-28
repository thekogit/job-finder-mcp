import json
import logging
import re
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser

logger = logging.getLogger("job_scout.extract.nextdata")


def extract_next_data(html_content: str) -> dict[str, Any] | None:
    if not html_content:
        return None

    tree = HTMLParser(html_content)
    script = tree.css_first('script#__NEXT_DATA__[type="application/json"]')
    if script:
        raw_text = script.text(strip=True)
        if raw_text:
            try:
                data = json.loads(raw_text)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.debug("Failed parsing __NEXT_DATA__: %s", e)

    # Fallback to regex pattern for __NEXT_DATA__
    match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application\/json">([^<]+)<\/script>',
        html_content,
    )
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception as err:
            logger.debug("Failed parsing regex NEXT_DATA: %s", err)

    # Look for window.__INITIAL_STATE__
    state_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});", html_content, re.DOTALL
    )
    if state_match:
        try:
            data = json.loads(state_match.group(1))
            if isinstance(data, dict):
                return data
        except Exception as err:
            logger.debug("Failed parsing window.__INITIAL_STATE__: %s", err)

    return None
