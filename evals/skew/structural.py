"""Structural skew: detect board schema breakage before the adapters silently degrade.

A *fingerprint* is the set of key paths in a JSON payload (JSON-LD JobPosting,
``__NEXT_DATA__``, a JSON API body) with the JSON type seen at each path. Lists collapse to
``[]`` and id-like keys collapse to ``<id>``, so the same page with different data gives the
same fingerprint. HTML-only boards are probed by counting offer links with the same URL
pattern the adapter uses.

Alerts, compared with the committed baseline of that board and payload kind:

* ``missing_path``    a path present in every baseline sample is gone;
* ``renamed_key``     ...and its parent gained a key the baseline never had;
* ``casing_change``   ...and a path differing only in letter case appeared;
* ``container_change`` a path changed between list and dict;
* ``type_change``     any other type change (e.g. number -> string);
* ``link_drop``       an HTML listing yields under half the baseline's minimum offer links.
"""

import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from job_scout.extract.jsonld import extract_job_posting_jsonld
from job_scout.extract.nextdata import extract_next_data

JSONType = str  # "dict" | "list" | "str" | "int" | "float" | "bool" | "null"

_ID_KEY = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|\$?[A-Za-z]*\d{4,}\w*)$",
    re.IGNORECASE,
)

# Offer-link patterns, mirroring each adapter's listing parser (see tests/adapters).
LINK_PATTERNS: dict[str, tuple[str, ...]] = {
    "justjoin": ("/job-offer/",),
    "rocketjobs": ("/oferta-pracy/",),
    "nofluffjobs": ("/job/",),
    "bulldogjob": ("/companies/jobs/",),
    "theprotocol": ("/szczegoly/praca/",),
    "pracuj": (",oferta,",),
    "linkedin": ("/jobs/view/",),
    "olx": ("/oferta/praca/", "/d/oferta/"),
    "aplikuj": ("/oferta/", "/praca/"),
}


# Apollo cache entries ("Job:256082-some-slug") and parameterised root queries
# ('jobs({"page":1})') carry data in the key; keep the type name, drop the data.
_APOLLO_KEY = re.compile(r"^([A-Z]\w*):.+$")
_QUERY_KEY = re.compile(r"^(\w+)\(.*\)$", re.DOTALL)
# Translation tables are UI copy, not data schema: skip them entirely.
_SKIPPED_SUBTREES = frozenset({"__namespaces", "_nextI18Next", "messages", "translations"})


def _normalise_key(key: str) -> str:
    if _ID_KEY.match(key):
        return "<id>"
    apollo = _APOLLO_KEY.match(key)
    if apollo:
        return f"{apollo.group(1)}:<id>"
    query = _QUERY_KEY.match(key)
    if query:
        return f"{query.group(1)}(<args>)"
    return key


def _json_type(value: Any) -> JSONType:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _walk(value: Any, path: str) -> Iterator[tuple[str, JSONType]]:
    yield path, _json_type(value)
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _SKIPPED_SUBTREES:
                continue
            name = _normalise_key(str(key))
            yield from _walk(child, f"{path}.{name}" if path else name)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, f"{path}[]")


def fingerprint(payload: Any) -> dict[str, set[JSONType]]:
    """Map every key path in ``payload`` to the set of JSON types seen there."""
    paths: dict[str, set[JSONType]] = {}
    for path, kind in _walk(payload, "$"):
        paths.setdefault(path, set()).add(kind)
    return paths


@dataclass(frozen=True)
class Payload:
    board: str
    kind: str  # e.g. "jsonld:detail", "next_data:listing", "api:listing", "html:listing"
    origin: str
    data: Any = None
    link_count: int | None = None


def _count_links(board: str, html: str) -> int | None:
    patterns = LINK_PATTERNS.get(board)
    if not patterns:
        return None
    hrefs = [str(a.attributes.get("href") or "") for a in HTMLParser(html).css("a")]
    return len({h for h in hrefs if any(p in h for p in patterns)})


def payloads_from_page(board: str, origin: str, body: str, page: str) -> list[Payload]:
    """Extract every structured payload from one response body.

    ``page`` is "listing" or "detail" (from the fixture name or the request order).
    """
    stripped = body.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return [Payload(board, f"api:{page}", origin, data=json.loads(body))]
        except json.JSONDecodeError:
            return []
    found: list[Payload] = []
    jsonld = extract_job_posting_jsonld(body)
    if jsonld is not None:
        found.append(Payload(board, f"jsonld:{page}", origin, data=jsonld))
    next_data = extract_next_data(body)
    if next_data is not None:
        found.append(Payload(board, f"next_data:{page}", origin, data=next_data))
    if page == "listing":
        count = _count_links(board, body)
        if count is not None:
            found.append(Payload(board, "html:listing", origin, link_count=count))
    return found


def fixture_payloads(fixtures_dir: Path) -> list[Payload]:
    """Payloads from the recorded fixtures (listing_* and detail_* files; expired pages skipped)."""
    payloads: list[Payload] = []
    for path in sorted(fixtures_dir.glob("*/*")):
        page = path.stem.split("_")[0]
        if page not in ("listing", "detail"):
            continue
        body = path.read_text(encoding="utf-8")
        origin = path.relative_to(fixtures_dir).as_posix()
        payloads.extend(payloads_from_page(path.parent.name, origin, body, page))
    return payloads


# --- baselines ----------------------------------------------------------------------------


def build_baseline(board: str, payloads: list[Payload], source_note: str) -> dict[str, Any]:
    kinds: dict[str, Any] = {}
    for kind in sorted({p.kind for p in payloads if p.board == board}):
        samples = [p for p in payloads if p.board == board and p.kind == kind]
        if kind == "html:listing":
            counts = [p.link_count or 0 for p in samples]
            kinds[kind] = {"samples": len(samples), "min_links": min(counts), "max_links": max(counts)}
            continue
        presence: Counter[str] = Counter()
        types: dict[str, set[str]] = {}
        for sample in samples:
            for path, seen in fingerprint(sample.data).items():
                presence[path] += 1
                types.setdefault(path, set()).update(seen)
        kinds[kind] = {
            "samples": len(samples),
            "paths": {
                path: {"types": sorted(types[path]), "presence": presence[path]}
                for path in sorted(types)
            },
        }
    return {"board": board, "source": source_note, "kinds": kinds}


@dataclass(frozen=True)
class Alert:
    board: str
    kind: str
    alert: str
    path: str
    detail: str
    origin: str


def _parent(path: str) -> str:
    if path.endswith("[]"):
        return path[:-2]
    return path.rsplit(".", 1)[0] if "." in path else "$"


def _type_alert(expected: set[str], seen: set[str]) -> str:
    flipped = ("list" in expected and "dict" in seen) or ("dict" in expected and "list" in seen)
    return "container_change" if flipped else "type_change"


def compare(payload: Payload, baseline: dict[str, Any]) -> list[Alert]:
    entry = baseline.get("kinds", {}).get(payload.kind)
    if entry is None:
        return []  # a payload kind the baseline never saw: nothing to compare
    alerts: list[Alert] = []

    def alert(name: str, path: str, detail: str) -> None:
        alerts.append(Alert(payload.board, payload.kind, name, path, detail, payload.origin))

    if payload.kind == "html:listing":
        floor = entry["min_links"] / 2
        if (payload.link_count or 0) < floor:
            alert("link_drop", "<a href>", f"{payload.link_count} offer links, baseline min {entry['min_links']}")
        return alerts

    live = fingerprint(payload.data)
    base_paths: dict[str, Any] = entry["paths"]
    required = {p for p, info in base_paths.items() if info["presence"] == entry["samples"]}
    new_paths = set(live) - set(base_paths)
    live_lower = {p.lower(): p for p in new_paths}

    # 1. type changes on paths that still exist
    changed: list[str] = []
    for path, seen in sorted(live.items()):
        if path not in base_paths:
            continue
        expected = set(base_paths[path]["types"])
        if seen <= expected:
            continue
        if expected == {"null"}:
            # Only ever seen empty: the baseline says nothing about its real type, so a
            # value appearing is an optional field being filled, not schema breakage.
            continue
        alert(_type_alert(expected, seen), path, f"baseline {sorted(expected)}, now {sorted(seen)}")
        changed.append(path)

    # 2. required paths that disappeared, reported once at the highest missing ancestor
    missing = sorted(required - set(live))
    reported: list[str] = []
    for path in missing:
        if any(
            path.startswith((prefix + ".", prefix + "[]")) for prefix in (*changed, *reported)
        ):
            continue
        reported.append(path)
        if path.lower() in live_lower:
            alert("casing_change", path, f"now {live_lower[path.lower()]!r}")
            continue
        siblings = sorted(p for p in new_paths if _parent(p) == _parent(path))
        if siblings:
            alert("renamed_key", path, f"missing; new sibling(s) {siblings[:3]}")
        else:
            alert("missing_path", path, "present in every baseline sample, absent now")
    return alerts


def load_baselines(directory: Path) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "board" in data:
            baselines[data["board"]] = data
    return baselines


def write_baselines(directory: Path, payloads: list[Payload], source_note: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for board in sorted({p.board for p in payloads}):
        path = directory / f"{board}.json"
        path.write_text(
            json.dumps(build_baseline(board, payloads, source_note), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


# --- synthetic mutations (self-test: every one must raise an alert) ----------------------

MUTATIONS = ("renamed_key", "list_to_dict", "casing_change")


def _first_dict_with_scalar(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if any(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in value.values()):
            return value
        for child in value.values():
            found = _first_dict_with_scalar(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_dict_with_scalar(child)
            if found is not None:
                return found
    return None


def _first_dict_with_list(value: Any) -> tuple[dict[str, Any], str] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, list) and child:
                return value, key
        for child in value.values():
            found = _first_dict_with_list(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_dict_with_list(child)
            if found is not None:
                return found
    return None


def mutate(data: Any, mutation: str) -> Any | None:
    """Return a mutated deep copy of ``data``, or None if the payload has no such spot."""
    clone = json.loads(json.dumps(data))
    if mutation in ("renamed_key", "casing_change"):
        target = _first_dict_with_scalar(clone)
        if target is None:
            return None
        key = next(k for k, v in target.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool))
        new_key = f"{key}_v2" if mutation == "renamed_key" else key.swapcase()
        if new_key == key:
            return None
        target[new_key] = target.pop(key)
        return clone
    if mutation == "list_to_dict":
        found = _first_dict_with_list(clone)
        if found is None:
            return None
        parent, key = found
        parent[key] = {str(i): item for i, item in enumerate(parent[key])}
        return clone
    raise ValueError(f"unknown mutation {mutation!r}")
