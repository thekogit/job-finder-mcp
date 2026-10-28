import re

from job_scout.models import SalaryContract, SalaryGrossNet, SalaryPeriod, SalaryRange


def _clean_number(num_str: str) -> float | int:
    # Replace non-breaking spaces and other whitespace
    cleaned = (
        num_str.replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("k", "000")
        .replace("K", "000")
    )
    # Handle thousands dots vs decimal comma/dot
    # In PL: 10.000 or 10 000 is 10000; 10,50 is 10.5
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "." in cleaned and len(cleaned.split(".")[-1]) == 3:
        cleaned = cleaned.replace(".", "")
    elif "," in cleaned and len(cleaned.split(",")[-1]) == 3:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    val = float(cleaned)
    if val.is_integer():
        return int(val)
    return val


def parse_single_salary_clause(raw_text: str) -> SalaryRange | None:
    text = raw_text.strip()
    if not text:
        return None

    lower = text.lower()
    # Normalize dashes
    normalized = re.sub(r"[–—−]", "-", text)

    # Determine period
    period = SalaryPeriod.MONTH
    if any(h in lower for h in ("/ godz", "/godz", "/ h", "/h", "godzinowo", "za godzinę", "per hour")):
        period = SalaryPeriod.HOUR
    elif any(d in lower for d in ("/ dzień", "/dzień", "/ d", "dziennie", "per day")):
        period = SalaryPeriod.DAY
    elif any(y in lower for y in ("/ rok", "/rok", "/ yr", "rocznie", "per year", "annually")):
        period = SalaryPeriod.YEAR
    elif any(m in lower for m in ("/ mies", "/mies", "/ msc", "/msc", "miesięcznie", "per month")):
        period = SalaryPeriod.MONTH

    # Determine gross / net
    gross_net = SalaryGrossNet.UNKNOWN
    if "brutto" in lower or "gross" in lower:
        gross_net = SalaryGrossNet.GROSS
    elif "netto" in lower or "net" in lower or "+ vat" in lower:
        gross_net = SalaryGrossNet.NET

    # Determine contract
    contract = SalaryContract.UNKNOWN
    if "b2b" in lower or "+ vat" in lower:
        contract = SalaryContract.B2B
    elif "uop" in lower or "umowa o pracę" in lower:
        contract = SalaryContract.UOP
    elif "uz" in lower or "umowa zlecenie" in lower:
        contract = SalaryContract.UZ
    elif "uod" in lower or "umowa o dzieło" in lower:
        contract = SalaryContract.UOD

    # Currency
    currency = "PLN"
    if "eur" in lower or "€" in lower:
        currency = "EUR"
    elif "usd" in lower or "$" in lower:
        currency = "USD"
    elif "gbp" in lower or "£" in lower:
        currency = "GBP"
    elif "chf" in lower:
        currency = "CHF"
    elif "zł" in lower or "pln" in lower:
        currency = "PLN"

    # Number patterns
    # Match patterns like:
    # 10 000 - 15 000
    # 15k - 20k
    # od 8 000
    # do 12 000
    # 120 - 150
    range_match = re.search(
        r"([\d\s\xa0\u202f]+(?:[.,]\d+)?\s*[kK]?)\s*-\s*([\d\s\xa0\u202f]+(?:[.,]\d+)?\s*[kK]?)",
        normalized,
    )
    od_match = re.search(
        r"(?:od|from|\>)\s*([\d\s\xa0\u202f]+(?:[.,]\d+)?\s*[kK]?)",
        normalized,
        re.IGNORECASE,
    )
    do_match = re.search(
        r"(?:do|to|\<|up to)\s*([\d\s\xa0\u202f]+(?:[.,]\d+)?\s*[kK]?)",
        normalized,
        re.IGNORECASE,
    )

    min_val: float | int | None = None
    max_val: float | int | None = None

    if range_match:
        try:
            min_val = _clean_number(range_match.group(1))
            max_val = _clean_number(range_match.group(2))
        except ValueError:
            return None
    elif od_match:
        try:
            min_val = _clean_number(od_match.group(1))
        except ValueError:
            return None
    elif do_match:
        try:
            max_val = _clean_number(do_match.group(1))
        except ValueError:
            return None
    else:
        # Single number
        single_match = re.search(r"([\d\s\xa0\u202f]{2,}(?:[.,]\d+)?\s*[kK]?)", normalized)
        if single_match:
            try:
                val = _clean_number(single_match.group(1))
                min_val = val
                max_val = val
            except ValueError:
                return None
        else:
            return None

    return SalaryRange(
        min=min_val,
        max=max_val,
        currency=currency,
        period=period,
        gross_net=gross_net,
        contract=contract,
        raw=text,
    )


def parse_salary(raw_text: str | None) -> list[SalaryRange] | None:
    if not raw_text:
        return None
    text = raw_text.strip()
    if not text:
        return None

    # Check if there are multiple contracts or lines, e.g. UoP and B2B
    # Split by newlines, semicolons, or distinct contract types
    parts = re.split(r"[\r\n;]+|\s*\|\s*", text)
    if len(parts) == 1:
        # Check if text contains both uop and b2b or both brutto and netto
        uop_b2b_split = re.split(r"(?<=\))\s*(?=\d|od|do|b2b|uop)", text, flags=re.IGNORECASE)
        if len(uop_b2b_split) > 1:
            parts = uop_b2b_split

    results: list[SalaryRange] = []
    for part in parts:
        cleaned_part = part.strip()
        if not cleaned_part:
            continue
        parsed = parse_single_salary_clause(cleaned_part)
        if parsed:
            results.append(parsed)

    if not results:
        # Fallback to entire string
        single = parse_single_salary_clause(text)
        if single:
            results.append(single)

    return results if results else None
