import re
from datetime import datetime, timedelta
from typing import Literal

from job_scout.models import WARSAW_TZ

POLISH_MONTHS = {
    "stycznia": 1,
    "styczen": 1,
    "styczeń": 1,
    "lutego": 2,
    "luty": 2,
    "marca": 3,
    "marzec": 3,
    "kwietnia": 4,
    "kwiecien": 4,
    "kwiecień": 4,
    "maja": 5,
    "maj": 5,
    "czerwca": 6,
    "czerwiec": 6,
    "lipca": 7,
    "lipiec": 7,
    "sierpnia": 8,
    "sierpien": 8,
    "sierpień": 8,
    "wrzesnia": 9,
    "wrzesień": 9,
    "września": 9,
    "pazdziernika": 10,
    "pazdziernik": 10,
    "października": 10,
    "październik": 10,
    "listopada": 11,
    "listopad": 11,
    "grudnia": 12,
    "grudzien": 12,
    "grudzień": 12,
}

ENGLISH_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def parse_date(
    date_str: str | None,
    reference_time: datetime | None = None,
) -> tuple[str | None, Literal["exact", "relative", "unknown"]]:
    if not date_str:
        return (None, "unknown")

    raw = str(date_str).strip()
    if not raw:
        return (None, "unknown")

    now = reference_time if reference_time is not None else datetime.now(WARSAW_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=WARSAW_TZ)
    else:
        now = now.astimezone(WARSAW_TZ)

    # 1. Try ISO 8601 parsing first
    iso_clean = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=WARSAW_TZ)
        else:
            dt = dt.astimezone(WARSAW_TZ)
        return (dt.isoformat(), "exact")
    except ValueError:
        dt = None

    clean = raw.lower().replace("opublikowana:", "").replace("dodana:", "").strip()

    # 2. Relative dates
    if any(clean.startswith(prefix) for prefix in ("dzisiaj", "today")):
        dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.isoformat(), "relative")

    if any(clean.startswith(prefix) for prefix in ("wczoraj", "yesterday")):
        dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.isoformat(), "relative")

    # X hours ago / godz. temu
    hour_match = re.search(r"(\d+)\s*(?:godz\.|godzin|godziny|godzinę|hour|hours|h)\s*(?:temu|ago)?", clean)
    if hour_match:
        hours = int(hour_match.group(1))
        dt = now - timedelta(hours=hours)
        return (dt.isoformat(), "relative")

    # X days ago / dni temu
    day_match = re.search(r"(\d+)\s*(?:dni|dnia|dzień|d\.|days|day|d)\s*(?:temu|ago)", clean)
    if day_match:
        days = int(day_match.group(1))
        dt = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.isoformat(), "relative")

    # X weeks ago / tyg. temu
    week_match = re.search(r"(\d+)\s*(?:tyg\.|tygodni|tygodnie|tydzień|weeks|week|w)\s*(?:temu|ago)", clean)
    if week_match:
        weeks = int(week_match.group(1))
        dt = (now - timedelta(days=weeks * 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.isoformat(), "relative")

    # X months ago / mies. temu
    month_match = re.search(r"(\d+)\s*(?:mies\.|miesięcy|miesiące|miesiąc|months|month|m)\s*(?:temu|ago)", clean)
    if month_match:
        months = int(month_match.group(1))
        dt = (now - timedelta(days=months * 30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.isoformat(), "relative")

    # 3. Polish absolute date: "8 października 2026"
    polish_match = re.search(
        r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})",
        clean,
    )
    if polish_match:
        day = int(polish_match.group(1))
        m_name = polish_match.group(2)
        year = int(polish_match.group(3))
        month = POLISH_MONTHS.get(m_name) or ENGLISH_MONTHS.get(m_name)
        if month:
            dt = datetime(year, month, day, 0, 0, 0, tzinfo=WARSAW_TZ)
            return (dt.isoformat(), "exact")

    # Polish date with dots or slashes: "08.10.2026" or "08/10/2026"
    dmy_match = re.search(r"(\d{1,2})[\.\/](\d{1,2})[\.\/](\d{4})", clean)
    if dmy_match:
        day = int(dmy_match.group(1))
        month = int(dmy_match.group(2))
        year = int(dmy_match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            dt = datetime(year, month, day, 0, 0, 0, tzinfo=WARSAW_TZ)
            return (dt.isoformat(), "exact")

    return (None, "unknown")
