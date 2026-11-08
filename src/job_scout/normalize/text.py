import html
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser


def html_to_plain_text(html_content: str | None) -> str:
    if not html_content:
        return ""

    # If it is not HTML (no tags), unescape and normalize whitespace
    if "<" not in html_content and ">" not in html_content:
        unescaped = html.unescape(html_content)
        return "\n".join(
            line.strip() for line in unescaped.splitlines() if line.strip()
        )

    tree = HTMLParser(html_content)

    # Remove script and style elements
    for tag in tree.css("script, style, noscript, svg"):
        tag.decompose()

    # Replace block level elements with newlines
    text = tree.text(separator="\n", strip=True)
    text = html.unescape(text)

    # Normalize multiple blank lines to at most two
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines: list[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
        else:
            blank_count = 0
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def truncate_description(
    text: str, max_chars: int = 4000
) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return (text, False)

    # Cut at last whitespace or newline before max_chars if possible
    cut = text[:max_chars]
    last_space = max(cut.rfind(" "), cut.rfind("\n"))
    if last_space > max_chars * 0.8:
        cut = cut[:last_space]

    cut = cut.rstrip() + "\u2026"
    return (cut, True)


_QUOTE_WHITESPACE = re.compile(r"\s+")


def normalize_for_quote(text: str) -> str:
    """Normalise text before a verbatim-quote substring check.

    Only whitespace is touched: NBSP / narrow NBSP become plain spaces and every run of
    whitespace collapses to one space. Case, diacritics and punctuation are kept, so a
    quote must still be a real substring of the listing (no translation, no case folding).
    """
    replaced = text.replace("\xa0", " ").replace("\u202f", " ")
    return _QUOTE_WHITESPACE.sub(" ", replaced).strip()


def is_verbatim_quote(quote: str, source_text: str) -> bool:
    normalized_quote = normalize_for_quote(quote)
    if not normalized_quote:
        return False
    return normalized_quote in normalize_for_quote(source_text)
