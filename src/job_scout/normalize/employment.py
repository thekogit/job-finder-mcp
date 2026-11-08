def normalize_employment_types(raw: object) -> list[str]:
    """Contract/employment types from a board value that may be a string or a list.

    schema.org ``employmentType`` is Text or a list of Text, and boards switch between the
    two (justjoin and rocketjobs did by 2026-11-08). Blank entries and duplicates are
    dropped; order is kept; anything that is not text yields nothing rather than a repr.
    """
    items = raw if isinstance(raw, list) else [raw]
    seen: dict[str, None] = {}
    for item in items:
        if isinstance(item, str) and item.strip():
            seen.setdefault(item.strip(), None)
    return list(seen)
