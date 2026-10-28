import re
from typing import Literal

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from job_scout.normalize.text import html_to_plain_text

REQ_HEADINGS = [
    r"nasze\s+wymagania",
    r"wymagania",
    r"opis\s+wymagan",
    r"opis\s+wymagań",
    r"obowiazkowe",
    r"obowiązkowe",
    r"nasze\s+oczekiwania",
    r"oczekiwania",
    r"czego\s+oczekujemy",
    r"czego\s+potrzebujesz",
    r"kogo\s+szukamy",
    r"oczekujemy",
    r"requirements",
    r"what\s+we\s+expect",
    r"must\s+have",
    r"your\s+profile",
    r"profil\s+kandydata",
    r"twoj\s+profil",
    r"twój\s+profil",
]

NICE_HEADINGS = [
    r"mile\s+widziane",
    r"dodatkowym\s+atutem",
    r"dodatkowe\s+atuty",
    r"nice\s+to\s+have",
    r"what\s+would\s+be\s+nice",
    r"good\s+to\s+have",
    r"mile\s+widziana",
    r"mile\s+widziany",
    r"dodatkowy\s+atut",
    r"plusy",
]


def _clean_item(text: str) -> str:
    cleaned = re.sub(r"^[\s•\-\*\d\.\)\:]+", "", text).strip()
    return cleaned


def extract_requirements_from_html(
    html_content: str,
) -> tuple[list[str], list[str], Literal["structured", "section", "not_found"]]:
    tree = HTMLParser(html_content)

    reqs: list[str] = []
    nice: list[str] = []

    # First attempt: search in HTML elements (h2, h3, h4, strong, b, div, p) followed by ul/ol or li
    all_elements = tree.css("h1, h2, h3, h4, h5, h6, strong, b, p, div")

    for elem in all_elements:
        text = elem.text(strip=True).lower()
        if not text:
            continue

        is_req = any(re.search(rf"\b{h}\b", text) for h in REQ_HEADINGS)
        is_nice = any(re.search(rf"\b{h}\b", text) for h in NICE_HEADINGS)

        if is_nice:
            parent = elem.parent
            if parent:
                ul = parent.css_first("ul, ol")
                if ul:
                    for li in ul.css("li"):
                        item = _clean_item(li.text(strip=True))
                        if item and item not in nice and len(nice) < 40:
                            nice.append(item)
            continue

        if is_req:
            parent = elem.parent
            if parent:
                ul = parent.css_first("ul, ol")
                if ul:
                    for li in ul.css("li"):
                        item = _clean_item(li.text(strip=True))
                        if item and item not in reqs and len(reqs) < 40:
                            reqs.append(item)
            continue

    if reqs:
        return (reqs[:40], nice[:40], "section")

    # Fallback to plain-text section extraction
    plain = html_to_plain_text(html_content)
    return extract_requirements_from_text(plain)


def extract_requirements_from_text(
    text_content: str,
) -> tuple[list[str], list[str], Literal["structured", "section", "not_found"]]:
    lines = [line.strip() for line in text_content.splitlines()]
    reqs: list[str] = []
    nice: list[str] = []

    current_section: Literal["req", "nice", "none"] = "none"

    for line in lines:
        if not line:
            continue

        lower = line.lower()
        is_nice = any(re.search(rf"\b{h}\b", lower) for h in NICE_HEADINGS)
        is_req = any(re.search(rf"\b{h}\b", lower) for h in REQ_HEADINGS)

        if is_nice:
            current_section = "nice"
            continue
        if is_req:
            current_section = "req"
            continue

        # Check if line indicates start of another unrelated section
        other_section = any(
            re.search(rf"\b{h}\b", lower)
            for h in [
                r"oferujemy",
                r"to\s+oferujemy",
                r"benefity",
                r"korzysci",
                r"o\s+firmie",
                r"o\s+nas",
                r"zakres\s+obowiazkow",
                r"obowiazki",
                r"twoje\s+zadania",
                r"zadania",
                r"responsibilities",
                r"what\s+we\s+offer",
                r"benefits",
                r"about\s+us",
            ]
        )
        if other_section and not line.startswith(("-", "•", "*")):
            current_section = "none"
            continue

        if current_section == "req":
            item = _clean_item(line)
            if item and len(item) > 2 and item not in reqs and len(reqs) < 40:
                reqs.append(item)
        elif current_section == "nice":
            item = _clean_item(line)
            if item and len(item) > 2 and item not in nice and len(nice) < 40:
                nice.append(item)

    if reqs:
        return (reqs[:40], nice[:40], "section")

    return ([], [], "not_found")


def normalize_requirements(
    structured_reqs: list[str] | None = None,
    structured_nice: list[str] | None = None,
    html_or_text: str | None = None,
) -> tuple[list[str], list[str], Literal["structured", "section", "not_found"]]:
    if structured_reqs and len(structured_reqs) > 0:
        cleaned_reqs = [_clean_item(r) for r in structured_reqs if _clean_item(r)]
        cleaned_nice = [_clean_item(n) for n in (structured_nice or []) if _clean_item(n)]
        return (cleaned_reqs[:40], cleaned_nice[:40], "structured")

    if html_or_text:
        if "<" in html_or_text and ">" in html_or_text:
            return extract_requirements_from_html(html_or_text)
        return extract_requirements_from_text(html_or_text)

    return ([], [], "not_found")
