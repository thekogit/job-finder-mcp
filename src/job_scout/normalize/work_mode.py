from job_scout.models import WorkMode


def normalize_work_mode(raw: str | list[str] | None) -> tuple[list[WorkMode] | None, str | None]:
    if not raw:
        return (None, None)

    if isinstance(raw, list):
        raw_str = ", ".join(str(item) for item in raw if item)
    else:
        raw_str = str(raw).strip()

    if not raw_str:
        return (None, None)

    lower = raw_str.lower()
    modes: set[WorkMode] = set()

    # Remote checks
    if any(
        term in lower
        for term in (
            "remote",
            "zdalna",
            "zdalnie",
            "fully remote",
            "home office",
            "telecommute",
            "100% remote",
            "praca zdalna",
        )
    ):
        modes.add(WorkMode.REMOTE)

    # Hybrid checks
    if any(
        term in lower
        for term in (
            "hybrid",
            "hybrydowa",
            "hybrydowo",
            "praca hybrydowa",
            "częściowo zdalna",
            "czescowo zdalna",
            "częściowo z biura",
        )
    ):
        modes.add(WorkMode.HYBRID)

    # Onsite checks
    if any(
        term in lower
        for term in (
            "onsite",
            "on-site",
            "stacjonarna",
            "stacjonarnie",
            "praca stacjonarna",
            "office",
            "biuro",
            "biurze",
            "w biurze",
            "z biura",
            "in office",
            "in-office",
            "praca mobilna",
            "mobilna",
        )
    ):
        modes.add(WorkMode.ONSITE)

    # Order priority for predictable output: onsite, hybrid, remote
    order = [WorkMode.ONSITE, WorkMode.HYBRID, WorkMode.REMOTE]
    result_list = [m for m in order if m in modes]

    if not result_list:
        return (None, raw_str)

    return (result_list, raw_str)
