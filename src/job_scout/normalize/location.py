import re

from job_scout.models import WorkMode
from job_scout.store import remove_diacritics

WARSAW_NAMES = {"warszawa", "warsaw"}

WARSAW_DISTRICTS = {
    "bemowo",
    "bialoleka",
    "bielany",
    "mokotow",
    "ochota",
    "praga-poludnie",
    "praga poludnie",
    "praga-polnoc",
    "praga polnoc",
    "rembertow",
    "srodmiescie",
    "targowek",
    "ursus",
    "ursynow",
    "wawer",
    "wesola",
    "wilanow",
    "wlochy",
    "wola",
    "zoliborz",
}

WARSAW_METRO = {
    "piaseczno",
    "pruszkow",
    "konstancin-jeziorna",
    "konstancin jeziorna",
    "zabki",
    "marki",
    "lomianki",
    "ozarow mazowiecki",
    "legionowo",
    "sulejowek",
    "kobylka",
    "zielonka",
    "grodzisk mazowiecki",
    "raszyn",
    "izabelin",
    "nadarzyn",
    "nowy dwor mazowiecki",
}

ALLOWED_REMOTE_SCOPES = {
    "poland",
    "polska",
    "pl",
    "warszawa",
    "warsaw",
    "eu",
    "europe",
    "unrestricted",
    "worldwide",
    "global",
    "anywhere",
}

EXCLUDED_REMOTE_COUNTRIES = {
    "united states",
    "usa",
    "us only",
    "uk only",
    "united kingdom",
    "germany only",
    "deutschland only",
    "france only",
    "canada only",
    "australia only",
}


def is_warsaw_location(
    raw_location: str | None,
    work_modes: list[WorkMode] | None = None,
    include_metro: bool = False,
) -> bool:
    if not raw_location:
        # If no location given, but it is explicitly remote, check if remote is allowed
        if work_modes and WorkMode.REMOTE in work_modes:
            return True
        return False

    norm = remove_diacritics(raw_location.lower())

    # Check excluded remote countries first
    for excl in EXCLUDED_REMOTE_COUNTRIES:
        if excl in norm:
            # If specifically marked for another country, reject unless Poland also explicitly included
            if "poland" not in norm and "polska" not in norm and "warsaw" not in norm and "warszawa" not in norm:
                return False

    # Check Warsaw names
    for name in WARSAW_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", norm):
            return True

    # Check districts
    for dist in WARSAW_DISTRICTS:
        if dist in norm:
            return True

    # Check metro if requested
    if include_metro:
        for metro in WARSAW_METRO:
            if metro in norm:
                return True

    # If offer is remote, check if remote scope is Poland/EU or general
    if work_modes and WorkMode.REMOTE in work_modes:
        # If it says remote or zdalna
        if "zdaln" in norm or "remote" in norm:
            # Check if it specifies another country
            other_countries = ["us", "usa", "uk", "germany", "deutschland", "france", "canada", "spain", "italy"]
            has_other = any(re.search(rf"\b{re.escape(c)}\b", norm) for c in other_countries)
            has_pl = any(re.search(rf"\b{re.escape(c)}\b", norm) for c in ["pl", "poland", "polska", "warszawa", "warsaw", "eu", "europe"])
            if has_other and not has_pl:
                return False
            return True

        # Check if country is Poland or PL
        if any(re.search(rf"\b{re.escape(c)}\b", norm) for c in ["polska", "poland", "pl", "eu", "europe", "cala polska", "cała polska"]):
            return True

    return False
